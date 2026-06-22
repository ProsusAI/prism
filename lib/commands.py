"""User-facing prism commands: init, config, log, status, learn, forget, correct, maintain, procedures."""

import json
import os
import shutil
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from .config import PRISM_HOME, PUSH_KINDS, get_config, get_engrams_dir, ensure_dirs
from .confidence import decay
from .storage import (
    count_active,
    count_active_insights,
    delete_observations_for_project,
    delete_orphan_sessions,
    get_recent,
    get_insights,
    retrieval_stats,
    retrieved_engram_ids,
    top_engrams,
)
from .index import (
    add_entry,
    build_index_entry,
    get_entry,
    list_entries,
    load_index,
    remove_entry,
    save_index,
    update_confidence,
)
from .frontmatter import update_frontmatter
from .scrub import scrub_text, is_blocked_text
from .project import (
    cached_project_id_path,
    capture_hook_command,
    detect_project_id,
    detect_project_name,
    get_project_root,
    register_cursor_project,
)


def _find_agent_cli() -> str:
    """Resolve Cursor agent CLI binary (not the `cursor` editor launcher)."""
    from .agent_runner import _find_agent_cli as find_cli
    return find_cli()


def _print_agent_cli_preflight() -> None:
    """Warn when neither Claude nor Cursor agent CLIs are available for extraction."""
    has_claude = bool(shutil.which("claude"))
    has_agent = bool(_find_agent_cli())
    if has_claude or has_agent:
        if not has_claude:
            print()
            print("\033[33mNOTE: `claude` CLI not on PATH — Claude Code extraction will not run.\033[0m")
            print("  Cursor users: use the `agent` CLI (see below). Claude Code: https://claude.com/claude-code")
        if not has_agent:
            print()
            print("\033[33mNOTE: `agent` CLI not on PATH — Cursor extraction will not run.\033[0m")
            print("  Install: curl https://cursor.com/install -fsS | bash")
            print("  Then authenticate: agent login")
        return

    print()
    print("\033[33mWARNING: no agent CLI found for extraction (need `claude` or `agent`).\033[0m")
    print("  Observations will still be captured, but \033[1mno engrams will be generated\033[0m until you install one:")
    print("  Claude Code: https://claude.com/claude-code  (`claude login`)")
    print("  Cursor:      curl https://cursor.com/install -fsS | bash  (`agent login`)")


def cmd_init() -> None:
    """Initialize prism for the current project.

    Creates ~/.prism/ structure, configures hooks and MCP for Claude Code/Cursor,
    symlinks skills, updates .gitignore, generates IDE context files.
    Idempotent -- safe to re-run.
    """
    from .config import init_prism_home
    from .project import detect_project_remote
    from .sync import sync_claude_code

    init_prism_home()
    project_id = detect_project_id()
    project_name = detect_project_name()

    # Write project ID cache for hook performance (OBS-05)
    if project_id != "global":
        cache_path = cached_project_id_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(project_id + "\n")

    if project_id != "global":
        ensure_dirs(project_id)
        # Write project.json if not exists
        project_dir = PRISM_HOME / "projects" / project_id
        project_json = project_dir / "project.json"
        repo_root = str(get_project_root())
        if not project_json.exists():
            info = {
                "name": project_name,
                "root": repo_root,
                "remote": detect_project_remote(),
                "project_id": project_id,
                "last_seen": date.today().isoformat(),
            }
            project_json.write_text(json.dumps(info, indent=2) + "\n")
        register_cursor_project(project_id, repo_root)

    # Configure hooks (settings.local.json) and MCP server (~/.claude.json)
    _setup_hooks_and_mcp(project_id)

    # Symlink slash commands from ~/.prism/skills/ to .claude/skills/
    skills_count = _setup_slash_commands()

    # Update .gitignore with Prism-generated entries
    _update_gitignore()

    # Generate initial .claude/prism.md context file
    sync_claude_code(project_id)

    # Warn if project could not be identified via git
    if project_id == "global":
        print("\n\033[33mWarning: not a git repo -- observations will go into the global bucket.\033[0m")
        print("  Run 'prism init' from inside a git repo for project-scoped knowledge.")

    # Print concise summary (D-06, D-11)
    print(f"\n\033[32mPrism initialized for {project_name} ({project_id})\033[0m")
    print()
    print("  Hooks:   .claude/settings.local.json (Claude Code) + .cursor/hooks.json (Cursor)")
    print("  MCP:     prism knowledge server registered (Claude Code + Cursor)")
    print("  Context: .claude/prism.md + .cursor/rules/prism.mdc generated")
    if skills_count > 0:
        print(f"  Skills:  {skills_count} slash commands linked (.claude/skills/ + .cursor/rules/)")
    print()
    print("Start coding -- observations accumulate automatically.")
    print("Run \033[1mprism extract\033[0m after ~15 observations to generate engrams.")

    # Preflight: extraction/review shell out to an IDE agent CLI. Capture works
    # without it, but no engrams will ever be produced — warn here rather than
    # failing silently in the background.
    _print_agent_cli_preflight()


def _setup_hooks_and_mcp(project_id: str) -> None:
    """Configure Claude Code hooks and MCP server.

    Hooks → .claude/settings.local.json (machine-specific, gitignored).
    MCP server → ~/.claude.json (projects[cwd].mcpServers) — where Claude Code reads it.
    Carefully merges with existing config -- never clobbers other tools' entries (D-05).
    """
    claude_dir = get_project_root() / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    # --- Hooks → settings.local.json ---
    local_path = claude_dir / "settings.local.json"
    local = {}
    if local_path.exists():
        try:
            local = json.loads(local_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    hooks = local.get("hooks", {})
    capture_script = str(PRISM_HOME / "hooks" / "capture.sh")
    pre_command = capture_hook_command(
        capture_script,
        "pre",
        project_id,
        extra_env={"PRISM_SOURCE": "claude_code"},
    )

    for event in ("PreToolUse",):
        hook_groups = hooks.get(event, [])
        hook_groups = [
            g for g in hook_groups
            if not any(capture_script in h.get("command", "") for h in g.get("hooks", []))
        ]
        hook_groups.append({
            "matcher": "*",
            "hooks": [{"type": "command", "command": pre_command}],
        })
        hooks[event] = hook_groups

    # SessionStart: run decay maintenance once per session
    maintain_cmd = str(PRISM_HOME / "prism") + " maintain --quiet"
    session_start_entry = {"hooks": [{"type": "command", "command": maintain_cmd}]}
    existing_session_cmds = {
        h.get("command", "")
        for g in hooks.get("SessionStart", [])
        for h in g.get("hooks", [])
    }
    if maintain_cmd not in existing_session_cmds:
        hooks.setdefault("SessionStart", []).append(session_start_entry)

    local["hooks"] = hooks
    local_path.write_text(json.dumps(local, indent=2) + "\n")

    # --- MCP Server → ~/.claude.json (projects[cwd].mcpServers) ---
    _write_mcp_to_claude_json(project_id)

    # --- Cursor hooks + MCP ---
    _setup_cursor_hooks_and_mcp(project_id)


def _setup_cursor_hooks_and_mcp(project_id: str) -> None:
    """Configure Cursor project hooks and user-level MCP server.

    Hooks → .cursor/hooks.json (project-level). Cursor reads hooks ONLY from
    this file with a {"version": 1, "hooks": {...}} shape — it does NOT read
    hooks from settings.json (that is the Claude Code convention).
    MCP server → ~/.cursor/mcp.json (mcpServers.prism).
    """
    cursor_dir = get_project_root() / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)

    capture_script = str(PRISM_HOME / "hooks" / "capture_cursor.sh")
    pre_command = capture_hook_command(
        capture_script,
        "pre",
        project_id,
        extra_env={"PRISM_SOURCE": "cursor"},
    )

    hooks_path = cursor_dir / "hooks.json"
    config = {}
    if hooks_path.exists():
        try:
            config = json.loads(hooks_path.read_text())
        except (json.JSONDecodeError, OSError):
            config = {}

    config["version"] = 1
    hooks = config.get("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}

    # One observation per tool call → preToolUse only (mirrors Claude Code
    # PreToolUse). Drop any stale prism entries before re-adding.
    pre_entries = [
        e for e in hooks.get("preToolUse", [])
        if not (isinstance(e, dict) and capture_script in e.get("command", ""))
    ]
    pre_entries.append({"command": pre_command})
    hooks["preToolUse"] = pre_entries

    post_entries = [
        e for e in hooks.get("postToolUse", [])
        if not (isinstance(e, dict) and capture_script in e.get("command", ""))
    ]
    if post_entries:
        hooks["postToolUse"] = post_entries
    else:
        hooks.pop("postToolUse", None)

    config["hooks"] = hooks
    hooks_path.write_text(json.dumps(config, indent=2) + "\n")

    # Migration: earlier prism versions wrote hooks to settings.json, which
    # Cursor never reads. Strip those dead prism entries so they don't linger.
    _strip_legacy_cursor_settings_hooks(cursor_dir / "settings.json", capture_script)

    # Remove legacy prism.md from cursor rules (migrated to prism.mdc)
    legacy = cursor_dir / "rules" / "prism.md"
    if legacy.exists():
        legacy.unlink()

    cursor_mcp_path = Path.home() / ".cursor" / "mcp.json"
    cursor_mcp_path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if cursor_mcp_path.exists():
        try:
            data = json.loads(cursor_mcp_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    mcp_servers = data.get("mcpServers", {})
    mcp_servers["prism"] = {
        "command": sys.executable,
        "args": [str(PRISM_HOME / "lib" / "mcp_server.py")],
        "env": {"PRISM_PROJECT_ID": project_id},
    }
    data["mcpServers"] = mcp_servers

    tmp = cursor_mcp_path.parent / (cursor_mcp_path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.rename(str(tmp), str(cursor_mcp_path))


def _strip_legacy_cursor_settings_hooks(settings_path: Path, capture_script: str) -> None:
    """Remove dead prism hook entries from a legacy .cursor/settings.json.

    Cursor never read hooks from settings.json; older prism installs wrote them
    there anyway. Strip only prism's own entries; leave any user config intact.
    Delete the file if it ends up empty.
    """
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in ("preToolUse", "postToolUse"):
        entries = [
            e for e in hooks.get(event, [])
            if not (isinstance(e, dict) and capture_script in e.get("command", ""))
        ]
        if entries:
            hooks[event] = entries
        else:
            hooks.pop(event, None)
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    try:
        if settings:
            settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        else:
            settings_path.unlink()
    except OSError:
        pass


def _uninstall_cursor_integration() -> None:
    """Remove prism's Cursor hooks and MCP entry. Mirrors the Claude Code cleanup."""
    cursor_dir = get_project_root() / ".cursor"
    capture_script = str(PRISM_HOME / "hooks" / "capture_cursor.sh")

    # Remove prism's preToolUse entry from .cursor/hooks.json.
    hooks_path = cursor_dir / "hooks.json"
    if hooks_path.exists():
        try:
            config = json.loads(hooks_path.read_text())
        except (json.JSONDecodeError, OSError):
            config = None
        if isinstance(config, dict):
            hooks = config.get("hooks", {})
            if isinstance(hooks, dict):
                for event in ("preToolUse", "postToolUse"):
                    entries = [
                        e for e in hooks.get(event, [])
                        if not (isinstance(e, dict) and capture_script in e.get("command", ""))
                    ]
                    if entries:
                        hooks[event] = entries
                    else:
                        hooks.pop(event, None)
                # If only the version sentinel remains, drop the file entirely.
                if hooks:
                    config["hooks"] = hooks
                    hooks_path.write_text(json.dumps(config, indent=2) + "\n")
                else:
                    hooks_path.unlink()
                print("  Removed hook from .cursor/hooks.json")

    # Strip any dead entries a legacy install left in settings.json.
    _strip_legacy_cursor_settings_hooks(cursor_dir / "settings.json", capture_script)

    # Remove the prism MCP server from ~/.cursor/mcp.json.
    cursor_mcp_path = Path.home() / ".cursor" / "mcp.json"
    if cursor_mcp_path.exists():
        try:
            data = json.loads(cursor_mcp_path.read_text())
        except (json.JSONDecodeError, OSError):
            data = None
        if isinstance(data, dict):
            servers = data.get("mcpServers", {})
            if isinstance(servers, dict) and "prism" in servers:
                servers.pop("prism")
                data["mcpServers"] = servers
                cursor_mcp_path.write_text(json.dumps(data, indent=2) + "\n")
                print("  Removed prism MCP server from ~/.cursor/mcp.json")


def _write_mcp_to_claude_json(project_id: str) -> None:
    """Write prism MCP server entry into ~/.claude.json under projects[cwd].mcpServers."""
    claude_json_path = Path.home() / ".claude.json"
    data = {}
    if claude_json_path.exists():
        try:
            data = json.loads(claude_json_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    project_key = str(get_project_root())
    projects = data.get("projects", {})
    project_entry = projects.get(project_key, {})
    mcp_servers = project_entry.get("mcpServers", {})
    mcp_servers["prism"] = {
        "command": sys.executable,
        "args": [str(PRISM_HOME / "lib" / "mcp_server.py")],
        "env": {"PRISM_PROJECT_ID": project_id},
    }
    project_entry["mcpServers"] = mcp_servers
    projects[project_key] = project_entry
    data["projects"] = projects

    tmp = claude_json_path.parent / (claude_json_path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.rename(str(tmp), str(claude_json_path))


def _remove_mcp_from_claude_json() -> None:
    """Remove prism MCP server entry from ~/.claude.json for the current project."""
    claude_json_path = Path.home() / ".claude.json"
    if not claude_json_path.exists():
        return
    try:
        data = json.loads(claude_json_path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    project_key = str(get_project_root())
    project_entry = data.get("projects", {}).get(project_key)
    if not project_entry:
        return

    mcp = project_entry.get("mcpServers", {})
    if "prism" not in mcp:
        return
    mcp.pop("prism")
    if not mcp:
        project_entry.pop("mcpServers", None)
    else:
        project_entry["mcpServers"] = mcp

    tmp = claude_json_path.parent / (claude_json_path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.rename(str(tmp), str(claude_json_path))
    print("  Removed MCP server from ~/.claude.json")


def _setup_slash_commands() -> int:
    """Symlink Prism skills to Claude Code skills and Cursor rules. Returns count installed."""
    skills_src = PRISM_HOME / "skills"
    if not skills_src.exists() or not any(skills_src.iterdir()):
        return 0

    claude_dest = get_project_root() / ".claude" / "skills"
    claude_dest.mkdir(parents=True, exist_ok=True)
    cursor_rules_dest = get_project_root() / ".cursor" / "rules"
    cursor_rules_dest.mkdir(parents=True, exist_ok=True)

    installed = 0
    for skill_dir in skills_src.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            claude_skill_dest = claude_dest / skill_dir.name
            if claude_skill_dest.is_symlink() or claude_skill_dest.exists():
                if claude_skill_dest.is_symlink():
                    claude_skill_dest.unlink()
                else:
                    shutil.rmtree(str(claude_skill_dest))
            claude_skill_dest.symlink_to(skill_dir)

            # Remove legacy .md symlink if it exists (migration from pre-.mdc format)
            legacy_md = cursor_rules_dest / f"{skill_dir.name}.md"
            if legacy_md.is_symlink() or legacy_md.is_file():
                legacy_md.unlink()

            cursor_skill_dest = cursor_rules_dest / f"{skill_dir.name}.mdc"
            if cursor_skill_dest.is_symlink() or cursor_skill_dest.exists():
                if cursor_skill_dest.is_symlink() or cursor_skill_dest.is_file():
                    cursor_skill_dest.unlink()
                else:
                    shutil.rmtree(str(cursor_skill_dest))
            cursor_skill_dest.symlink_to(skill_dir / "SKILL.md")

            installed += 1
    return installed


def _update_gitignore() -> None:
    """Add Prism-generated files to .gitignore (T-01-10: duplicate check + comment block)."""
    gitignore_path = get_project_root() / ".gitignore"
    entries = [
        ".claude/settings.local.json",
        ".claude/prism.md",
        ".claude/skills/",
        ".claude/.prism_project_id",
        ".cursor/hooks.json",
        ".cursor/rules/*.mdc",
    ]

    existing_content = ""
    if gitignore_path.exists():
        existing_content = gitignore_path.read_text()

    # Migrate legacy .md glob to .mdc in-place
    migrated_content = existing_content.replace(".cursor/rules/*.md\n", ".cursor/rules/*.mdc\n")
    if migrated_content != existing_content:
        gitignore_path.write_text(migrated_content)
        existing_content = migrated_content

    existing_lines = set(existing_content.splitlines())
    to_add = [e for e in entries if e not in existing_lines]
    if to_add:
        with open(gitignore_path, "a") as f:
            if existing_content and not existing_content.endswith("\n"):
                f.write("\n")
            if "# Prism (auto-generated, machine-specific)" not in existing_lines:
                f.write("# Prism (auto-generated, machine-specific)\n")
            for entry in to_add:
                f.write(entry + "\n")


def cmd_status(project_id: Optional[str] = None) -> None:
    """Show active knowledge entries and project info.

    Per D-06: Global and project engrams merge into one list, each tagged [global] or [project].
    """
    if not project_id:
        project_id = detect_project_id()

    project_name = detect_project_name()
    entries = list_entries(project_id=project_id)

    # Check context file
    claude_ctx = get_project_root() / ".claude" / "prism.md"

    print(f"\033[1mPrism Status: {project_name}\033[0m ({project_id})")
    print()

    if claude_ctx.exists():
        line_count = len(claude_ctx.read_text().split("\n"))
        print(f"  Context: .claude/prism.md ({line_count} lines)")
    else:
        print("  Context: not generated (run 'prism extract' or 'prism learn' to generate)")

    # Unified display with scope tags (D-06)
    print()
    if entries:
        print(f"\033[1mKnowledge\033[0m ({len(entries)} entries):")
        print()
        for e in sorted(entries, key=lambda x: -x.get("confidence", 0)):
            scope_tag = "[global]" if e.get("scope") == "global" else "[project]"
            kind = e.get("kind", "preference")
            conf = e.get("confidence", 0)
            trigger = e.get("trigger", "").strip('"')
            domain = e.get("domain", "general")

            # Build detail parts
            details = []
            if kind == "procedure":
                sc = e.get("success_count", 0)
                fc = e.get("failure_count", 0)
                details.append(f"{sc}ok/{fc}fail")
            if e.get("pinned"):
                details.append("pinned")

            detail_str = f" ({', '.join(details)})" if details else ""
            print(f"  {scope_tag} [{kind}] {conf:.2f} {trigger[:60]}{detail_str}")
            print(f"           {domain} | {e['id']}")
    else:
        print("  No knowledge entries yet.")
        print("  Run 'prism learn \"<fact>\"' or let extraction discover patterns.")

    # Observations count
    print()
    backlog = count_active(project_id)
    toward_extract = count_active(project_id, for_triggers=True)
    insights = count_active_insights(project_id)
    config = get_config()
    threshold = config.get("extract_threshold", 15)
    line = f"  Observations: {backlog} pending ({toward_extract} toward extract at {threshold})"
    if insights:
        line += f", {insights} insight(s)"
    print(line)

    from .agent_runner import classify_pending_sources, pending_source_counts

    pending_kind = classify_pending_sources(project_id)
    if pending_kind == "mixed":
        counts = pending_source_counts(project_id)
        print(
            f"  Pending sources: mixed ({counts['cursor']} cursor, "
            f"{counts['claude']} claude_code)"
        )
        pref = config.get("mixed_backend_preference", "cursor")
        print(
            f"  Extraction: hook uses calling IDE; manual runs prefer "
            f"{pref} when both CLIs are installed"
        )

    # Archived count
    archive_dir = PRISM_HOME / "archive"
    if archive_dir.exists():
        archived = list(archive_dir.glob("*.md"))
        if archived:
            print(f"  Archived: {len(archived)} entries (recoverable)")

    # Recent extraction errors
    errors_path = PRISM_HOME / "extract_errors.jsonl"
    if errors_path.exists():
        try:
            lines = errors_path.read_text().strip().splitlines()
            recent = []
            for line in lines[-5:]:
                try:
                    recent.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    pass
            if recent:
                print()
                print(f"  \033[33mExtraction errors ({len(lines)} total, showing last {len(recent)}):\033[0m")
                for err in recent:
                    ts = err.get("timestamp", "")[:19].replace("T", " ")
                    stage = err.get("stage", "unknown")
                    reason = err.get("reason", "")
                    print(f"    {ts}  [{stage}]  {reason}")
                print(f"  Full log: {errors_path}")
        except OSError:
            pass


def _fmt_ago(ts: Optional[int]) -> str:
    """Human 'time since' for a Unix timestamp (e.g. 'today', '3d ago')."""
    if not ts:
        return "never"
    secs = max(0, int(time.time()) - int(ts))
    days = secs // 86400
    if days == 0:
        return "today"
    if days == 1:
        return "1d ago"
    if days < 30:
        return f"{days}d ago"
    return f"{days // 30}mo ago"


def cmd_stats(
    project_id: Optional[str] = None,
    days: int = 30,
    json_output: bool = False,
    limit: int = 10,
) -> None:
    """Show retrieval analytics: how often Claude/Cursor actually pull engrams via MCP.

    Counts are derived from logged retrieval events (SQLite), not from engram fields,
    so they reflect *active* retrieval -- distinct from engrams merely surfaced into
    prism.md by sync.
    """
    if not project_id:
        project_id = detect_project_id()
    window = max(1, days) * 86400
    now = int(time.time())
    since = now - window

    stats = retrieval_stats(project_id, window)
    tops = top_engrams(project_id, since, limit=limit)
    pulled_ids = retrieved_engram_ids(project_id, since)

    # Active engrams that were never pulled in the window -> forget candidates.
    entries = list_entries(project_id=project_id)
    dead = [e for e in entries if e["id"] not in pulled_ids]

    window_n = stats["window_retrievals"]
    prior_n = stats["prior_retrievals"]
    if prior_n:
        trend_pct = round((window_n - prior_n) / prior_n * 100)
    else:
        trend_pct = None
    total_searches = stats["total_searches"]
    hit_rate = (stats["hit_searches"] / total_searches) if total_searches else None

    if json_output:
        payload = {
            "project_id": project_id,
            "window_days": days,
            "retrievals": window_n,
            "prior_retrievals": prior_n,
            "trend_pct": trend_pct,
            "hit_rate": round(hit_rate, 3) if hit_rate is not None else None,
            "searches": total_searches,
            "by_source": stats["by_source"],
            "surfaced_pushes": stats["surfaced_pushes"],
            "surfaced_engrams": stats["surfaced_engrams"],
            "top": [
                {"id": t["id"], "count": t["count"],
                 "last": datetime.fromtimestamp(t["last_ts"], timezone.utc).date().isoformat()}
                for t in tops
            ],
            "dead": [e["id"] for e in dead],
            "active_engrams": len(entries),
        }
        print(json.dumps(payload, indent=2))
        return

    project_name = detect_project_name()
    print(f"\033[1mPrism -- retrieval insights: {project_name}\033[0m (last {days}d)")
    print()

    if window_n == 0 and stats["surfaced_pushes"] == 0:
        print("  No retrievals recorded yet.")
        print("  Engrams are pulled when Claude/Cursor call prism_search, prism_get,")
        print("  or prism_relevant via MCP. Stats will populate as you code.")
        return

    trend = ""
    if trend_pct is not None:
        arrow = "\033[32m^\033[0m" if trend_pct >= 0 else "\033[31mv\033[0m"
        trend = f"   {arrow} {abs(trend_pct)}% vs prior {days}d"
    print(f"  Retrievals    {window_n}{trend}")
    if hit_rate is not None:
        print(f"  Hit rate      {round(hit_rate * 100)}%   "
              f"({stats['hit_searches']}/{total_searches} searches returned an engram)")
    if stats["by_source"]:
        src = "  ".join(f"{k} {v}" for k, v in sorted(stats["by_source"].items()))
        print(f"  Source        {src}")
    print()

    if tops:
        print("  \033[1mMost retrieved\033[0m")
        for t in tops:
            print(f"    {t['count']:>3}x  {t['id'][:44]:<44} last: {_fmt_ago(t['last_ts'])}")
        print()

    # Honesty line: surfaced into context vs actually pulled.
    if stats["surfaced_engrams"]:
        print(f"  Surfaced into context {stats['surfaced_engrams']} engram-pushes "
              f"vs {window_n} active pulls")
        print()

    if dead:
        shown = ", ".join(e["id"] for e in dead[:8])
        more = f" (+{len(dead) - 8} more)" if len(dead) > 8 else ""
        print(f"  \033[33mNever pulled in {days}d\033[0m ({len(dead)}/{len(entries)}) "
              f"-> review with 'prism forget':")
        print(f"    {shown}{more}")


def cmd_learn(text: str, project_id: Optional[str] = None, scope: str = "project") -> None:
    """Manually teach a fact or preference. Creates with confidence 0.8."""
    text = scrub_text(text)
    if is_blocked_text(text):
        print("Error: input matched a block pattern and was not saved.")
        return

    if not project_id:
        project_id = detect_project_id()
    ensure_dirs(project_id)

    # Generate ID from text
    entry_id = _text_to_id(text)

    # Determine scope and directory
    if scope == "global":
        engrams_dir = PRISM_HOME / "global" / "engrams"
    else:
        engrams_dir = get_engrams_dir(project_id)
    engrams_dir.mkdir(parents=True, exist_ok=True)

    filepath = engrams_dir / f"{entry_id}.md"

    # Write knowledge entry file
    content = f"""---
id: {entry_id}
kind: preference
trigger: "{text[:80]}"
confidence: 0.8
domain: general
scope: {scope}
project_id: {project_id}
evidence_count: 1
last_observed: {date.today().isoformat()}
tags: [manual]
---

{text}

## Evidence
- Directly taught by user via prism learn on {date.today().isoformat()}
"""
    filepath.write_text(content)

    # Add to index; roll back file if index update fails to avoid orphaned files
    rel_path = str(filepath.relative_to(PRISM_HOME))
    entry = build_index_entry(
        entry_id=entry_id,
        kind="preference",
        trigger=text[:80],
        confidence=0.8,
        domain="general",
        scope=scope,
        project_id=project_id,
        path=rel_path,
        evidence_count=1,
        tags=["manual"],
    )
    try:
        add_entry(entry)
    except Exception as e:
        filepath.unlink(missing_ok=True)
        print(f"Error: could not update index, rolled back file: {e}")
        return

    print(f"Learned: {entry_id} (confidence: 0.8)")
    print(f"File: {filepath}")

    # Auto-sync .claude/prism.md (CTX-04, D-07: synchronous)
    from .sync import sync_claude_code
    sync_claude_code(project_id)


def cmd_forget(entry_id: str, _skip_sync: bool = False) -> None:
    """Archive an entry (remove from active context)."""
    entry = get_entry(entry_id)
    if not entry:
        print(f"Entry not found: {entry_id}")
        return

    # Remove from index first so a failed file move doesn't leave a dangling pointer
    remove_entry(entry_id)

    # Move file to archive (validate path is non-empty and points to a file)
    source_path = PRISM_HOME / entry.get("path", "")
    if entry.get("path") and source_path.is_file():
        archive_dir = PRISM_HOME / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / source_path.name
        shutil.move(str(source_path), str(dest))
        print(f"Archived: {source_path.name} -> archive/")

    if not _skip_sync:
        from .project import detect_project_id as _detect_pid
        from .sync import sync_claude_code
        pid = entry.get("project_id", _detect_pid())
        sync_claude_code(pid)

    print(f"Forgot: {entry_id}")


def cmd_correct(entry_id: str, correction_text: str) -> None:
    """Supersede an entry with corrected version."""
    old_entry = get_entry(entry_id)
    if not old_entry:
        print(f"Entry not found: {entry_id}")
        return

    project_id = old_entry.get("project_id", detect_project_id())
    scope = old_entry.get("scope", "project")
    domain = old_entry.get("domain", "general")

    # Archive old entry without triggering an intermediate sync
    cmd_forget(entry_id, _skip_sync=True)

    # Create new entry with correction
    new_id = _text_to_id(correction_text)

    if scope == "global":
        engrams_dir = PRISM_HOME / "global" / "engrams"
    else:
        engrams_dir = get_engrams_dir(project_id)
    engrams_dir.mkdir(parents=True, exist_ok=True)

    filepath = engrams_dir / f"{new_id}.md"

    content = f"""---
id: {new_id}
kind: correction
trigger: "{correction_text[:80]}"
confidence: 0.8
domain: {domain}
scope: {scope}
project_id: {project_id}
evidence_count: 1
last_observed: {date.today().isoformat()}
tags: [manual, correction]
---

{correction_text}

## Evidence
- User correction of '{entry_id}' on {date.today().isoformat()}
- Supersedes: {entry_id}
"""
    filepath.write_text(content)

    # Add to index; roll back file if index update fails to avoid orphaned files
    rel_path = str(filepath.relative_to(PRISM_HOME))
    entry = build_index_entry(
        entry_id=new_id,
        kind="correction",
        trigger=correction_text[:80],
        confidence=0.8,
        domain=domain,
        scope=scope,
        project_id=project_id,
        path=rel_path,
        evidence_count=1,
        tags=["manual", "correction"],
    )
    try:
        add_entry(entry)
    except Exception as e:
        filepath.unlink(missing_ok=True)
        print(f"Error: could not update index, rolled back file: {e}")
        return

    # Auto-sync .claude/prism.md (CTX-04, D-07: synchronous)
    from .sync import sync_claude_code
    sync_claude_code(project_id)

    print(f"Corrected: {entry_id} -> {new_id} (confidence: 0.8)")


def cmd_maintain(quiet: bool = False) -> None:
    """Run confidence decay, archive low-confidence entries, delete zeroed archive entries."""
    def log(msg: str) -> None:
        if not quiet:
            print(msg)

    config = get_config()
    archive_threshold = config.get("archive_threshold", 0.2)
    delete_threshold = config.get("delete_threshold", 0.0)
    floor = config.get("decay_floor", 0.1)
    half_life_days = config.get("decay_half_life_weeks", 4) * 7
    grace = config.get("decay_grace_days", 3)

    # Pass 1: delete archive files whose confidence has reached the delete threshold
    archive_dir = PRISM_HOME / "archive"
    deleted = 0
    if archive_dir.is_dir():
        for archive_file in archive_dir.glob("*.md"):
            try:
                text = archive_file.read_text()
            except OSError:
                continue
            conf = None
            in_fm = False
            for line in text.splitlines():
                if line.strip() == "---":
                    in_fm = not in_fm
                    continue
                if in_fm and line.strip().startswith("confidence:"):
                    try:
                        conf = float(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
                    break
            if conf is not None and conf <= delete_threshold:
                archive_file.unlink()
                deleted += 1
                log(f"  Deleted: {archive_file.stem} (confidence: {conf:.2f})")

    # Pass 2: decay active engrams, archive those that cross archive_threshold
    index = load_index()
    today = date.today()

    if index.get("last_maintained") == today.isoformat():
        log("Maintenance already ran today — skipping decay pass.")
        return

    decayed = 0
    archived = 0
    to_archive_ids = set()

    for entry in index["engrams"]:
        if entry.get("pinned"):
            continue

        # Decay is recomputed from confidence_base over idle days since last_used --
        # a pure function of timestamps, so it never compounds across runs (confidence.py).
        last_used = entry.get("last_used") or entry.get("last_observed", "")
        if not last_used:
            continue

        try:
            last_date = date.fromisoformat(last_used)
        except ValueError:
            continue

        idle_days = (today - last_date).days
        if idle_days <= grace:
            continue

        old_conf = entry.get("confidence", 0.5)
        base = entry.get("confidence_base", old_conf)
        new_conf = decay(base, idle_days, floor, half_life_days, grace)

        # PUSH_KINDS (corrections/preferences) decay for bookkeeping but are never
        # auto-archived -- placement is by kind, not score (confidence_plan.md §5).
        archivable = entry.get("kind") not in PUSH_KINDS

        if archivable and new_conf < archive_threshold:
            source_path = PRISM_HOME / entry.get("path", "")
            if entry.get("path") and source_path.is_file():
                archive_dir.mkdir(parents=True, exist_ok=True)
                update_frontmatter(source_path, {"confidence": new_conf})
                shutil.move(str(source_path), str(archive_dir / source_path.name))
            to_archive_ids.add(entry["id"])
            archived += 1
            log(f"  Archived: {entry['id']} (confidence: {old_conf:.2f} -> {new_conf:.2f})")
        elif new_conf != old_conf:
            entry["confidence"] = round(new_conf, 3)
            source_path = PRISM_HOME / entry.get("path", "")
            if entry.get("path") and source_path.is_file():
                update_frontmatter(source_path, {"confidence": new_conf})
            decayed += 1

    index["last_maintained"] = today.isoformat()
    index["engrams"] = [e for e in index["engrams"] if e["id"] not in to_archive_ids]
    save_index(index)

    log(f"Maintenance complete: {decayed} decayed, {archived} archived, {deleted} deleted")

    if decayed > 0 or archived > 0 or deleted > 0:
        from .project import detect_project_id
        from .sync import sync_claude_code
        project_id = detect_project_id()
        sync_claude_code(project_id)



def cmd_disable_hook() -> None:
    """Remove the Prism PreToolUse capture hook from .claude/settings.local.json.

    Stops automatic background observation capture and the AI extraction/review
    calls it triggers. MCP server, skills, engrams, and all CLI commands remain
    fully functional. Users can still run 'prism analyze-sessions --extract'
    manually after a session to get the same learning at their own pace.
    """
    settings_path = get_project_root() / ".claude" / "settings.local.json"
    if not settings_path.exists():
        print("No .claude/settings.local.json found -- hook was not installed for this project.")
        return

    try:
        existing = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"Could not read settings.local.json: {e}")
        return

    hooks = existing.get("hooks", {})
    pre = hooks.get("PreToolUse", [])
    capture_cmd = str(PRISM_HOME / "hooks" / "capture.sh")

    # Filter out any matcher group whose hooks list contains the prism capture command.
    # Leave all other hooks (e.g. from GSD or other tools) untouched.
    filtered = [
        group for group in pre
        if not any(capture_cmd in h.get("command", "") for h in group.get("hooks", []))
    ]

    if len(filtered) == len(pre):
        print("Prism capture hook not found in .claude/settings.local.json -- nothing to remove.")
        return

    if filtered:
        hooks["PreToolUse"] = filtered
    else:
        hooks.pop("PreToolUse", None)

    if hooks:
        existing["hooks"] = hooks
    else:
        existing.pop("hooks", None)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")
    print("Prism capture hook disabled.")
    print()
    print("  MCP server, skills, and engrams are unchanged.")
    print("  To capture knowledge manually: prism analyze-sessions --extract")
    print("  To re-enable:                  prism enable hook")


def cmd_enable_hook() -> None:
    """Re-add the Prism PreToolUse capture hook to .claude/settings.local.json."""
    project_id = detect_project_id()
    _setup_hooks_and_mcp(project_id)
    print("Prism capture hook enabled.")
    print()
    print("  Observations will be captured automatically on every tool use.")
    print("  Background extraction triggers at {} observations (configurable).".format(
        __import__("json").loads((PRISM_HOME / "config.json").read_text()).get("extract_threshold", 15)
        if (PRISM_HOME / "config.json").exists() else 15
    ))
    print("  To disable: prism disable hook")


def cmd_unlock() -> None:
    """Force-clear a stuck extraction lock."""
    lock = PRISM_HOME / ".extracting"
    if not lock.exists():
        print("No extraction lock found — nothing to clear.")
        return
    age = int(time.time() - lock.stat().st_mtime)
    lock.unlink(missing_ok=True)
    print(f"Lock cleared (was {age}s old). You can now run 'prism extract'.")


def cmd_uninstall(project_id: Optional[str] = None, yes: bool = False) -> None:
    """Remove all Prism integration from the current project. Undoes prism init.

    Removes: PreToolUse hook, MCP server entry, .claude/prism.md,
    .claude/.prism_project_id, .claude/skills/ Prism symlinks,
    ~/.prism/projects/<id>/, index entries, session tracker entries,
    and the Prism block in .gitignore.

    ~/.prism/ global install is untouched. Other projects are unaffected.
    Run 'prism init' to re-initialize.
    """
    if not project_id:
        project_id = detect_project_id()
    project_name = detect_project_name()

    root = get_project_root()
    settings_path = root / ".claude" / "settings.local.json"
    prism_md = root / ".claude" / "prism.md"
    project_id_cache = root / ".claude" / ".prism_project_id"
    skills_dest = root / ".claude" / "skills"
    project_dir = PRISM_HOME / "projects" / project_id

    print(f"This will remove all Prism integration from {project_name} ({project_id}):")
    print(f"  Hook in .claude/settings.local.json")
    print(f"  MCP entry in ~/.claude.json")
    print(f"  Hook in .cursor/hooks.json + MCP entry in ~/.cursor/mcp.json")
    print(f"  {prism_md}")
    print(f"  {project_id_cache}")
    print(f"  Prism skill symlinks in .claude/skills/")
    print(f"  {project_dir}/")
    print(f"  Prism block in .gitignore")
    print()
    print("  ~/.prism/ global install is untouched.")

    if not yes:
        confirm = input("\nType 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

    capture_cmd = str(PRISM_HOME / "hooks" / "capture.sh")

    # Remove hook from settings.local.json
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

        hooks = existing.get("hooks", {})
        pre = hooks.get("PreToolUse", [])
        filtered = [
            g for g in pre
            if not any(capture_cmd in h.get("command", "") for h in g.get("hooks", []))
        ]
        if filtered:
            hooks["PreToolUse"] = filtered
        else:
            hooks.pop("PreToolUse", None)
        if hooks:
            existing["hooks"] = hooks
        else:
            existing.pop("hooks", None)

        if existing:
            settings_path.write_text(json.dumps(existing, indent=2) + "\n")
        else:
            settings_path.unlink()
        print("  Removed hook from settings.local.json")

    _remove_mcp_from_claude_json()
    _uninstall_cursor_integration()

    # Delete context file
    if prism_md.exists():
        prism_md.unlink()
        print(f"  Deleted {prism_md.name}")

    # Delete project ID cache
    if project_id_cache.exists():
        project_id_cache.unlink()
        print(f"  Deleted {project_id_cache.name}")

    # Remove Prism skill symlinks (only links pointing into ~/.prism/skills/)
    prism_skills_src = str(PRISM_HOME / "skills")
    if skills_dest.exists():
        removed_skills = 0
        for entry in skills_dest.iterdir():
            if entry.is_symlink() and str(entry.resolve()).startswith(prism_skills_src):
                entry.unlink()
                removed_skills += 1
        if removed_skills:
            print(f"  Removed {removed_skills} Prism skill symlink(s) from .claude/skills/")

    # Delete project data directory
    if project_dir.exists():
        shutil.rmtree(project_dir)
        print(f"  Deleted ~/.prism/projects/{project_id}/")

    deleted_obs = delete_observations_for_project(project_id)
    if deleted_obs:
        print(f"  Deleted {deleted_obs} observation(s) from prism.db")
    orphans = delete_orphan_sessions()
    if orphans:
        print(f"  Reaped {orphans} orphaned session row(s) from prism.db")

    # Clear extraction lock if it belongs to this project
    lock = PRISM_HOME / ".extracting"
    lock.unlink(missing_ok=True)

    try:
        from .trigger import clear_extract_pending
        clear_extract_pending(project_id)
    except Exception:
        pass

    # Remove index entries for this project
    index = load_index()
    before = len(index["engrams"])
    index["engrams"] = [e for e in index["engrams"] if e.get("project_id") != project_id]
    if len(index["engrams"]) < before:
        save_index(index)
        print(f"  Cleared {before - len(index['engrams'])} index entries")

    # Remove session tracker entries for this project
    tracker_path = PRISM_HOME / "analyzed-sessions.json"
    if tracker_path.exists():
        try:
            with open(tracker_path) as f:
                tracker = json.load(f)
            before_sessions = len(tracker.get("sessions", {}))
            tracker["sessions"] = {
                sid: entry for sid, entry in tracker.get("sessions", {}).items()
                if entry.get("project_id") != project_id
            }
            if len(tracker["sessions"]) < before_sessions:
                with open(tracker_path, "w") as f:
                    json.dump(tracker, f, indent=2)
                    f.write("\n")
                print(f"  Cleared {before_sessions - len(tracker['sessions'])} session tracker entries")
        except (json.JSONDecodeError, OSError):
            pass

    # Remove Prism block from .gitignore
    _remove_gitignore_entries()

    print(f"\nPrism uninstalled from {project_name}.")
    print("Run 'prism init' to re-initialize.")


def _remove_gitignore_entries() -> None:
    """Remove the Prism-managed block from .gitignore."""
    gitignore_path = get_project_root() / ".gitignore"
    if not gitignore_path.exists():
        return

    content = gitignore_path.read_text()
    lines = content.splitlines(keepends=True)

    prism_entries = {
        ".claude/settings.local.json",
        ".claude/prism.md",
        ".claude/skills/",
        ".claude/.prism_project_id",
        ".cursor/hooks.json",
        ".cursor/settings.json",
        ".cursor/rules/*.mdc",
        "# Prism (auto-generated, machine-specific)",
    }

    filtered = [l for l in lines if l.rstrip("\n") not in prism_entries]
    if len(filtered) < len(lines):
        gitignore_path.write_text("".join(filtered))
        print("  Cleaned .gitignore")


def cmd_reset(project_id: Optional[str] = None, yes: bool = False) -> None:
    """Delete all prism data for the current project and start fresh."""
    if not project_id:
        project_id = detect_project_id()
    project_name = detect_project_name()

    project_dir = PRISM_HOME / "projects" / project_id
    prism_md = get_project_root() / ".claude" / "prism.md"

    print(f"This will delete all Prism data for {project_name} ({project_id}):")
    print(f"  {project_dir}/  (engrams, observations, candidates, archive)")
    print(f"  Observations in ~/.prism/prism.db for this project")
    print(f"  {prism_md}  (context file)")
    print(f"  Session tracker entries for this project")

    if not yes:
        confirm = input("\nType 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

    # Clear extraction lock if held (reset makes it stale)
    lock = PRISM_HOME / ".extracting"
    lock.unlink(missing_ok=True)

    # Remove project data dir
    if project_dir.exists():
        shutil.rmtree(project_dir)

    deleted_obs = delete_observations_for_project(project_id)
    if deleted_obs:
        print(f"  Deleted {deleted_obs} observation(s) from prism.db")
    orphans = delete_orphan_sessions()
    if orphans:
        print(f"  Reaped {orphans} orphaned session row(s) from prism.db")

    # Remove context file
    if prism_md.exists():
        prism_md.unlink()

    # Remove from index
    index = load_index()
    index["engrams"] = [e for e in index["engrams"] if e.get("project_id") != project_id]
    save_index(index)

    # Remove from session tracker
    tracker_path = PRISM_HOME / "analyzed-sessions.json"
    if tracker_path.exists():
        try:
            with open(tracker_path) as f:
                tracker = json.load(f)
            tracker["sessions"] = {
                sid: entry for sid, entry in tracker.get("sessions", {}).items()
                if entry.get("project_id") != project_id
            }
            with open(tracker_path, "w") as f:
                json.dump(tracker, f, indent=2)
                f.write("\n")
        except (json.JSONDecodeError, OSError):
            pass

    try:
        from .trigger import clear_extract_pending
        clear_extract_pending(project_id)
    except Exception:
        pass

    print(f"\nReset complete. Run 'prism init' then 'prism analyze-sessions' to start fresh.")


def cmd_config(key=None, value=None) -> None:
    """Get or set configuration values.

    No args: show all config as formatted output (D-11).
    One arg: show value for that key.
    Two args: set key to value (auto-parses numbers and bools).

    Supports dotted keys: extract.threshold -> extract_threshold (D-10).
    """
    from .config import get_config, save_config

    config = get_config()

    if key is None:
        # Show all config with friendly formatting (D-11)
        print("\033[1mPrism Configuration\033[0m")
        print()
        for k, v in sorted(config.items()):
            if isinstance(v, list):
                print("  {}: [{} patterns]".format(k, len(v)))
            else:
                print("  {}: {}".format(k, v))
        print()
        print("Set a value: prism config <key> <value>")
        return

    # Normalize dotted key: extract.threshold -> extract_threshold
    normalized_key = key.replace(".", "_")
    if normalized_key not in config and key in config:
        normalized_key = key

    if value is None:
        # Get single key
        if normalized_key in config:
            print("{}: {}".format(normalized_key, config[normalized_key]))
        else:
            print("\033[33mUnknown config key: {}\033[0m".format(key))
            print("Available keys: {}".format(", ".join(sorted(config.keys()))))
        return

    # Set value (try to parse as number/bool)
    if value.lower() in ("true", "false"):
        config[normalized_key] = value.lower() == "true"
    else:
        try:
            config[normalized_key] = float(value)
            if config[normalized_key] == int(config[normalized_key]):
                config[normalized_key] = int(config[normalized_key])
        except ValueError:
            config[normalized_key] = value

    save_config(config)
    print("\033[32mSet {} = {}\033[0m".format(normalized_key, config[normalized_key]))


def cmd_log(last_n: int = 20, extractions: bool = False, insights: bool = False,
            rejected: bool = False, json_output: bool = False) -> None:
    """Show recent observations, extraction history, or session insights.

    Default: human-readable table with timestamp, event, tool, summary (D-12).
    --json: raw JSONL output for piping/scripting.
    """
    if extractions:
        _log_extractions(last_n)
        return
    if insights:
        _log_insights(last_n)
        return
    if rejected:
        _log_rejected(last_n, json_output)
        return

    project_id = detect_project_id()
    rows = get_recent(project_id, last_n=last_n)

    if not rows:
        if not json_output:
            print("No observations yet. Start using Claude Code tools -- they'll be captured automatically.")
        return

    if json_output:
        for row in rows:
            print(json.dumps(row))
        return

    # Human-readable formatted table (D-12 default)
    print("\033[1mRecent observations\033[0m (last {})".format(len(rows)))
    print()
    print("  {:<20} {:<12} {:<15} Summary".format("Timestamp", "Event", "Tool"))
    print("  {} {} {} {}".format(
        "\u2500" * 20, "\u2500" * 12, "\u2500" * 15, "\u2500" * 40))

    for row in rows:
        ts = datetime.fromtimestamp(row["ts"]).strftime("%Y-%m-%dT%H:%M:%S")
        print("  {:<20} {:<12} {:<15} {}".format(
            ts, row.get("event", "?"), row.get("tool", "?"),
            (row.get("input_summary") or "")[:50]))

    print()
    print("  Use --json for raw output, --insights for session review findings, --rejected for rejections.")


def _log_rejected(last_n: int, json_output: bool = False) -> None:
    """Show the most recent rejected candidates with their failing gate reasons."""
    log_path = PRISM_HOME / "validation-log.jsonl"
    if not log_path.exists():
        print("No validation log found. Run 'prism extract' first.")
        return

    lines = log_path.read_text().strip().split("\n")
    rejected = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("decision", "").upper() == "REJECTED":
                rejected.append(entry)
        except json.JSONDecodeError:
            continue

    if not rejected:
        print("No rejected candidates in the validation log.")
        return

    recent = rejected[-last_n:]

    if json_output:
        for entry in recent:
            print(json.dumps(entry))
        return

    print("\033[1mRejected candidates\033[0m (last {} of {})".format(
        len(recent), len(rejected)))
    print()

    gate_order = ["constitution", "evidence", "contradiction", "safety", "novelty"]

    for entry in recent:
        ts = entry.get("timestamp", "?")[:19]
        candidate = entry.get("candidate", "unknown")
        gates = entry.get("gates", {})

        # gates is {gate_name: "reason"} — keys are failed gates only
        failed = [(g, gates[g]) for g in gate_order if g in gates]

        print("  \033[33m{}\033[0m  [{}]".format(candidate, ts))
        if failed:
            for gate_name, reason in failed:
                print("    \033[31m✗ {}\033[0m: {}".format(gate_name, reason))
        else:
            print("    (no gate failure details recorded)")
        print()


def _log_extractions(last_n: int) -> None:
    """Show recent extraction history."""
    log_path = PRISM_HOME / "validation-log.jsonl"
    if not log_path.exists():
        print("No extraction history found.")
        return
    print("Recent extractions:")
    lines = log_path.read_text().strip().split("\n")
    for line in lines[-last_n:]:
        try:
            entry = json.loads(line)
            ts = entry.get("timestamp", "?")[:19]
            candidate = entry.get("candidate", "?")
            decision = entry.get("decision", "?")
            print("  [{}] {}: {}".format(ts, decision, candidate))
        except json.JSONDecodeError:
            continue


def _log_insights(last_n: int) -> None:
    """Show session review insights."""
    project_id = detect_project_id()
    rows = get_insights(project_id, last_n=last_n)
    if not rows:
        print("No session insights found. Run 'prism review --session <id>' to generate.")
        return
    print("Session insights ({}):\n".format(len(rows)))
    for row in rows:
        ts = datetime.fromtimestamp(row["ts"]).strftime("%Y-%m-%d")
        kind = row.get("insight_type") or "unknown"
        summary = row.get("input_summary") or ""
        evidence = row.get("evidence") or ""
        print("  [{}] {}  {}".format(kind, ts, summary))
        if evidence:
            print("    evidence: {}".format(evidence[:120]))
        print()


def cmd_registry(args) -> None:
    """Dispatch registry subcommands: add, remove, list, default, create, token."""
    from .registry import (
        add_registry, remove_registry, list_registries,
        set_default_registry, get_registry, generate_token,
    )

    subcmd = getattr(args, "registry_command", None)

    if subcmd is None:
        # No subcommand -- print help
        print("Usage: prism registry {create|add|remove|list|default|token}")
        print()
        print("Commands:")
        print("  create    Create a new registry (guided wizard)")
        print("  add       Add a registry")
        print("  remove    Remove a registry")
        print("  list      Show configured registries")
        print("  default   Set default write target")
        print("  token     Manage API tokens")
        return

    if subcmd == "create":
        from .registry import cmd_registry_create
        cmd_registry_create()
        return

    if subcmd == "add":
        try:
            add_registry(args.name, args.url, args.token, writable=not args.read_only)
            print("\033[32mRegistry '{}' added ({})\033[0m".format(args.name, args.url))
        except ValueError as e:
            print("\033[31mError: {}\033[0m".format(e))
        return

    if subcmd == "remove":
        try:
            remove_registry(args.name)
            print("\033[32mRegistry '{}' removed.\033[0m".format(args.name))
        except ValueError as e:
            print("\033[31mError: {}\033[0m".format(e))
        return

    if subcmd == "list":
        entries = list_registries()
        if not entries:
            print("No registries configured. Use \033[1mprism registry add\033[0m to get started.")
            return
        # Formatted table
        print()
        print("  {:<12} {:<40} {:<10} {}".format("Name", "URL", "Writable", "Default"))
        print("  {} {} {} {}".format("-" * 12, "-" * 40, "-" * 10, "-" * 7))
        for entry in entries:
            default_marker = "*" if entry["is_default"] else ""
            writable_str = "yes" if entry["writable"] else "no"
            print("  {:<12} {:<40} {:<10} {}".format(
                entry["name"], entry["url"][:40], writable_str, default_marker))
        print()
        return

    if subcmd == "default":
        try:
            set_default_registry(args.name)
            print("\033[32mDefault registry set to '{}'\033[0m".format(args.name))
        except ValueError as e:
            print("\033[31mError: {}\033[0m".format(e))
        return

    if subcmd == "token":
        token_cmd = getattr(args, "token_command", None)

        if token_cmd is None:
            print("Usage: prism registry token {create|revoke} NAME")
            return

        if token_cmd == "create":
            try:
                reg = get_registry(args.name)
            except ValueError as e:
                print("\033[31mError: {}\033[0m".format(e))
                return

            new_token = generate_token()
            print()
            print("Generated token for registry '{}':\n".format(args.name))
            print("  \033[1m{}\033[0m".format(new_token))
            print()
            print("Add this token to your Worker:")
            print("  wrangler secret put REGISTRY_TOKENS")
            print("  Then paste: <existing_tokens>,{}".format(new_token))
            print()
            print("To save locally:")
            print("  prism registry add {} --url {} --token {}".format(
                args.name, reg.get("url", ""), new_token))
            return

        if token_cmd == "revoke":
            token_value = args.token_value
            print()
            print("To revoke token for registry '{}':".format(args.name))
            print()
            print("Remove '{}' from your Worker's REGISTRY_TOKENS:".format(token_value))
            print("  wrangler secret put REGISTRY_TOKENS")
            print("  Paste the updated comma-separated list without the revoked token.")
            return


def _text_to_id(text: str) -> str:
    """Convert a text string to a kebab-case ID."""
    import re
    # Lowercase, replace non-alphanumeric with hyphens, collapse
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    slug = slug.strip("-")
    # Truncate to reasonable length
    if len(slug) > 60:
        slug = slug[:60].rsplit("-", 1)[0]
    return slug
