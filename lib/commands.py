"""User-facing prism commands: init, config, log, status, learn, forget, correct, maintain, procedures."""

import json
import os
import shutil
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from .config import PRISM_HOME, get_config, get_engrams_dir, ensure_dirs
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
from .project import detect_project_id, detect_project_name


def cmd_init() -> None:
    """Initialize prism for the current project.

    Creates ~/.prism/ structure, configures hooks in settings.local.json and MCP in ~/.claude.json,
    symlinks skills, updates .gitignore, generates initial .claude/prism.md.
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
        cache_path = Path.cwd() / ".claude" / ".prism_project_id"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(project_id + "\n")

    if project_id != "global":
        ensure_dirs(project_id)
        # Write project.json if not exists
        project_dir = PRISM_HOME / "projects" / project_id
        project_json = project_dir / "project.json"
        if not project_json.exists():
            info = {
                "name": project_name,
                "root": os.getcwd(),
                "remote": detect_project_remote(),
                "project_id": project_id,
                "last_seen": date.today().isoformat(),
            }
            project_json.write_text(json.dumps(info, indent=2) + "\n")

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
    print(f"  Hooks:   .claude/settings.local.json (PreToolUse only)")
    print(f"  MCP:     prism knowledge server registered")
    print(f"  Context: .claude/prism.md generated")
    if skills_count > 0:
        print(f"  Skills:  {skills_count} slash commands linked")
    print()
    print("Start coding -- observations accumulate automatically.")
    print("Run \033[1mprism extract\033[0m after ~15 observations to generate engrams.")


def _setup_hooks_and_mcp(project_id: str) -> None:
    """Configure Claude Code hooks and MCP server.

    Hooks → .claude/settings.local.json (machine-specific, gitignored).
    MCP server → ~/.claude.json (projects[cwd].mcpServers) — where Claude Code reads it.
    Carefully merges with existing config -- never clobbers other tools' entries (D-05).
    """
    claude_dir = Path.cwd() / ".claude"
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
    capture_cmd = str(PRISM_HOME / "hooks" / "capture.sh")

    for event, phase_arg in [("PreToolUse", "pre")]:
        hook_entry = {
            "matcher": "*",
            "hooks": [{"type": "command", "command": "{} {}".format(capture_cmd, phase_arg)}],
        }
        if event not in hooks:
            hooks[event] = [hook_entry]
        else:
            existing_cmds = {h.get("command", "") for g in hooks[event] for h in g.get("hooks", [])}
            if hook_entry["hooks"][0]["command"] not in existing_cmds:
                hooks[event].append(hook_entry)

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


def _write_mcp_to_claude_json(project_id: str) -> None:
    """Write prism MCP server entry into ~/.claude.json under projects[cwd].mcpServers."""
    claude_json_path = Path.home() / ".claude.json"
    data = {}
    if claude_json_path.exists():
        try:
            data = json.loads(claude_json_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    project_key = str(Path.cwd())
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

    project_key = str(Path.cwd())
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
    """Symlink Prism skills to .claude/skills/. Returns count installed."""
    skills_src = PRISM_HOME / "skills"
    if not skills_src.exists() or not any(skills_src.iterdir()):
        return 0

    skills_dest = Path.cwd() / ".claude" / "skills"
    skills_dest.mkdir(parents=True, exist_ok=True)

    installed = 0
    for skill_dir in skills_src.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            dest = skills_dest / skill_dir.name
            if dest.is_symlink() or dest.exists():
                if dest.is_symlink():
                    dest.unlink()
                else:
                    shutil.rmtree(str(dest))
            dest.symlink_to(skill_dir)
            installed += 1
    return installed


def _update_gitignore() -> None:
    """Add Prism-generated files to .gitignore (T-01-10: duplicate check + comment block)."""
    gitignore_path = Path.cwd() / ".gitignore"
    entries = [
        ".claude/settings.local.json",
        ".claude/prism.md",
        ".claude/skills/",
        ".claude/.prism_project_id",
    ]

    existing_content = ""
    if gitignore_path.exists():
        existing_content = gitignore_path.read_text()
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
    claude_ctx = Path.cwd() / ".claude" / "prism.md"

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
    obs_path = PRISM_HOME / "projects" / project_id / "observations.jsonl"
    if obs_path.exists():
        with open(obs_path) as f:
            obs_count = sum(1 for _ in f)
        config = get_config()
        threshold = config.get("extract_threshold", 15)
        print(f"  Observations: {obs_count} pending (extract at {threshold})")
    else:
        print("  Observations: 0 pending")

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


def cmd_learn(text: str, project_id: Optional[str] = None, scope: str = "project") -> None:
    """Manually teach a fact or preference. Creates with confidence 0.9."""
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
confidence: 0.9
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

    # Add to index
    rel_path = str(filepath.relative_to(PRISM_HOME))
    entry = build_index_entry(
        entry_id=entry_id,
        kind="preference",
        trigger=text[:80],
        confidence=0.9,
        domain="general",
        scope=scope,
        project_id=project_id,
        path=rel_path,
        evidence_count=1,
        tags=["manual"],
    )
    add_entry(entry)

    print(f"Learned: {entry_id} (confidence: 0.9)")
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

    # Move file to archive (validate path is non-empty and points to a file)
    source_path = PRISM_HOME / entry.get("path", "")
    if entry.get("path") and source_path.is_file():
        archive_dir = PRISM_HOME / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / source_path.name
        shutil.move(str(source_path), str(dest))
        print(f"Archived: {source_path.name} -> archive/")

    # Remove from index
    remove_entry(entry_id)

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
confidence: 0.9
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

    rel_path = str(filepath.relative_to(PRISM_HOME))
    entry = build_index_entry(
        entry_id=new_id,
        kind="correction",
        trigger=correction_text[:80],
        confidence=0.9,
        domain=domain,
        scope=scope,
        project_id=project_id,
        path=rel_path,
        evidence_count=1,
        tags=["manual", "correction"],
    )
    add_entry(entry)

    # Auto-sync .claude/prism.md (CTX-04, D-07: synchronous)
    from .sync import sync_claude_code
    sync_claude_code(project_id)

    print(f"Corrected: {entry_id} -> {new_id} (confidence: 0.9)")


def _update_frontmatter_confidence(path: Path, new_conf: float) -> None:
    """Rewrite the confidence: line in a markdown file's YAML frontmatter."""
    try:
        text = path.read_text()
        lines = text.splitlines(keepends=True)
        in_frontmatter = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter and stripped.startswith("confidence:"):
                lines[i] = f"confidence: {round(new_conf, 3)}\n"
                break
        path.write_text("".join(lines))
    except OSError:
        pass


def cmd_maintain(quiet: bool = False) -> None:
    """Run confidence decay, archive low-confidence entries, delete zeroed archive entries."""
    def log(msg: str) -> None:
        if not quiet:
            print(msg)

    config = get_config()
    decay_rate = config.get("decay_rate_per_week", 0.05)
    archive_threshold = config.get("archive_threshold", 0.2)
    delete_threshold = config.get("delete_threshold", 0.0)

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
    decayed = 0
    archived = 0
    to_archive_ids = set()

    for entry in index["engrams"]:
        if entry.get("pinned"):
            continue

        last_obs = entry.get("last_observed", "")
        if not last_obs:
            continue

        try:
            last_date = date.fromisoformat(last_obs)
        except ValueError:
            continue

        weeks_since = (today - last_date).days / 7.0
        if weeks_since <= 0:
            continue

        old_conf = entry.get("confidence", 0.5)
        new_conf = max(0.0, old_conf - (decay_rate * weeks_since))

        if new_conf < archive_threshold:
            source_path = PRISM_HOME / entry.get("path", "")
            if entry.get("path") and source_path.is_file():
                archive_dir.mkdir(parents=True, exist_ok=True)
                _update_frontmatter_confidence(source_path, new_conf)
                shutil.move(str(source_path), str(archive_dir / source_path.name))
            to_archive_ids.add(entry["id"])
            archived += 1
            log(f"  Archived: {entry['id']} (confidence: {old_conf:.2f} -> {new_conf:.2f})")
        elif new_conf < old_conf:
            entry["confidence"] = round(new_conf, 3)
            decayed += 1

    if to_archive_ids or decayed > 0:
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
    settings_path = Path.cwd() / ".claude" / "settings.local.json"
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

    settings_path = Path.cwd() / ".claude" / "settings.local.json"
    prism_md = Path.cwd() / ".claude" / "prism.md"
    project_id_cache = Path.cwd() / ".claude" / ".prism_project_id"
    skills_dest = Path.cwd() / ".claude" / "skills"
    project_dir = PRISM_HOME / "projects" / project_id

    print(f"This will remove all Prism integration from {project_name} ({project_id}):")
    print(f"  Hook in .claude/settings.local.json")
    print(f"  MCP entry in ~/.claude.json")
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

    # Clear extraction lock if it belongs to this project
    lock = PRISM_HOME / ".extracting"
    lock.unlink(missing_ok=True)

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
    gitignore_path = Path.cwd() / ".gitignore"
    if not gitignore_path.exists():
        return

    content = gitignore_path.read_text()
    lines = content.splitlines(keepends=True)

    prism_entries = {
        ".claude/settings.local.json",
        ".claude/prism.md",
        ".claude/skills/",
        ".claude/.prism_project_id",
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
    prism_md = Path.cwd() / ".claude" / "prism.md"

    print(f"This will delete all Prism data for {project_name} ({project_id}):")
    print(f"  {project_dir}/  (engrams, observations, candidates, archive)")
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
            json_output: bool = False) -> None:
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

    project_id = detect_project_id()
    obs_path = PRISM_HOME / "projects" / project_id / "observations.jsonl"
    if not obs_path.exists():
        if json_output:
            return  # No output in JSON mode
        print("No observations yet. Start using Claude Code tools -- they'll be captured automatically.")
        return

    content = obs_path.read_text().strip()
    if not content:
        if not json_output:
            print("No observations yet. Start using Claude Code tools -- they'll be captured automatically.")
        return

    lines = content.split("\n")
    recent = lines[-last_n:]

    if json_output:
        # Raw JSONL output (D-12 --json flag)
        for line in recent:
            print(line)
        return

    # Human-readable formatted table (D-12 default)
    print("\033[1mRecent observations\033[0m (last {} of {})".format(
        min(last_n, len(recent)), len(lines)))
    print()
    print("  {:<20} {:<12} {:<15} Summary".format("Timestamp", "Event", "Tool"))
    print("  {} {} {} {}".format(
        "\u2500" * 20, "\u2500" * 12, "\u2500" * 15, "\u2500" * 40))

    for line in recent:
        try:
            entry = json.loads(line)
            ts = entry.get("timestamp", "?")[:19]
            event = entry.get("event", "?")
            tool = entry.get("tool", "?")
            summary = entry.get("input_summary", "")[:50]
            print("  {:<20} {:<12} {:<15} {}".format(ts, event, tool, summary))
        except json.JSONDecodeError:
            continue

    print()
    print("  Use --json for raw JSONL output, --insights for session review findings.")


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
    obs_path = PRISM_HOME / "projects" / project_id / "observations.jsonl"
    archive_dir = PRISM_HOME / "projects" / project_id / "observations.archive"
    all_insights = []
    for path in _collect_observation_files(obs_path, archive_dir):
        try:
            with open(path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("event") == "session_insight":
                            all_insights.append(entry)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    if not all_insights:
        print("No session insights found. Run 'prism review --session <id>' to generate.")
        return
    print("Session insights ({} total):\n".format(len(all_insights)))
    for entry in all_insights[-last_n:]:
        ts = entry.get("timestamp", "?")[:10]
        kind = entry.get("insight_type", "unknown")
        summary = entry.get("input_summary", "")
        evidence = entry.get("evidence", "")
        print("  [{}] {}".format(kind, summary))
        if evidence:
            print("    evidence: {}".format(evidence[:120]))
        print()


def _collect_observation_files(current: Path, archive_dir: Path) -> list:
    """Collect current + archived observation files, oldest first."""
    files = []
    if archive_dir.exists():
        files.extend(sorted(archive_dir.glob("observations_*.jsonl")))
    if current.exists():
        files.append(current)
    return files


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
