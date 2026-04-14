"""User-facing prism commands: init, config, log, status, learn, forget, correct, maintain, procedures."""

import json
import os
import shutil
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
    update_confidence,
)
from .project import detect_project_id, detect_project_name


def cmd_init() -> None:
    """Initialize prism for the current project.

    Creates ~/.prism/ structure, configures hooks + MCP in settings.local.json,
    symlinks skills, updates .gitignore, generates initial .claude/prism.md.
    Idempotent -- safe to re-run.
    """
    from .config import init_prism_home
    from .project import detect_project_remote
    from .sync import sync_claude_code

    init_prism_home()
    project_id = detect_project_id()
    project_name = detect_project_name()

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

    # Configure hooks and MCP server in .claude/settings.local.json
    _setup_hooks_and_mcp(project_id)

    # Symlink slash commands from ~/.prism/skills/ to .claude/skills/
    skills_count = _setup_slash_commands()

    # Update .gitignore with Prism-generated entries
    _update_gitignore()

    # Generate initial .claude/prism.md context file
    sync_claude_code(project_id)

    # Print concise summary (D-06, D-11)
    print(f"\n\033[32mPrism initialized for {project_name} ({project_id})\033[0m")
    print()
    print(f"  Hooks:   .claude/settings.local.json (PreToolUse + PostToolUse)")
    print(f"  MCP:     prism knowledge server registered")
    print(f"  Context: .claude/prism.md generated")
    if skills_count > 0:
        print(f"  Skills:  {skills_count} slash commands linked")
    print()
    print("Start coding -- observations accumulate automatically.")
    print("Run \033[1mprism extract\033[0m after ~15 observations to generate engrams.")


def _setup_hooks_and_mcp(project_id: str) -> None:
    """Configure Claude Code hooks and MCP server in .claude/settings.local.json.

    Carefully merges with existing config -- never clobbers other tools' entries (D-05).
    """
    settings_path = Path.cwd() / ".claude" / "settings.local.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing settings (T-01-07: handle corrupt JSON gracefully)
    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # --- Hooks ---
    hooks = existing.get("hooks", {})
    capture_cmd = str(PRISM_HOME / "hooks" / "capture.sh")

    for event, phase_arg, is_async in [
        ("PreToolUse", "pre", False),
        ("PostToolUse", "post", True),
    ]:
        hook_entry = {
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": "{} {}".format(capture_cmd, phase_arg),
            }],
        }
        if is_async:
            hook_entry["hooks"][0]["async"] = True

        if event not in hooks:
            hooks[event] = [hook_entry]
        else:
            # Check for existing Prism hook -- don't duplicate
            existing_cmds = set()
            for matcher_group in hooks[event]:
                for h in matcher_group.get("hooks", []):
                    existing_cmds.add(h.get("command", ""))
            if hook_entry["hooks"][0]["command"] not in existing_cmds:
                hooks[event].append(hook_entry)

    existing["hooks"] = hooks

    # --- MCP Server ---
    mcp_servers = existing.get("mcpServers", {})
    mcp_servers["prism"] = {
        "command": "python3",
        "args": [str(PRISM_HOME / "lib" / "mcp_server.py")],
        "env": {"PRISM_PROJECT": project_id},
    }
    existing["mcpServers"] = mcp_servers

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")


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
    ]

    existing_lines = set()
    if gitignore_path.exists():
        existing_lines = set(gitignore_path.read_text().splitlines())

    to_add = [e for e in entries if e not in existing_lines]
    if to_add:
        with open(gitignore_path, "a") as f:
            if existing_lines and gitignore_path.read_text() and not gitignore_path.read_text().endswith("\n"):
                f.write("\n")
            f.write("# Prism (auto-generated, machine-specific)\n")
            for entry in to_add:
                f.write(entry + "\n")


def cmd_status(project_id: Optional[str] = None) -> None:
    """Show active knowledge entries and project info."""
    if not project_id:
        project_id = detect_project_id()

    project_name = detect_project_name()
    entries = list_entries(project_id=project_id)

    global_entries = [e for e in entries if e.get("scope") == "global"]
    project_entries = [e for e in entries if e.get("scope") == "project"]

    # Check context file
    claude_ctx = Path.cwd() / ".claude" / "prism.md"

    print(f"Project: {project_name} ({project_id})")
    print()

    if claude_ctx.exists():
        line_count = len(claude_ctx.read_text().split("\n"))
        print(f"Claude Code context: .claude/prism.md ({line_count} lines)")
    else:
        print("Claude Code context: not generated (run 'prism sync --claude')")

    print()

    if global_entries:
        print(f"Always ({len(global_entries)} global):")
        for e in sorted(global_entries, key=lambda x: -x.get("confidence", 0)):
            source = ""
            if "team" in e.get("tags", []):
                source = ", from: team"
            print(f"  {e['id']} ({e['confidence']:.2f}) - {e.get('domain', 'general')}{source}")
    else:
        print("Always: (no global entries)")

    print()

    if project_entries:
        print(f"Project ({len(project_entries)}):")
        for e in sorted(project_entries, key=lambda x: -x.get("confidence", 0)):
            kind_note = ""
            if e.get("kind") == "procedure":
                sc = e.get("success_count", 0)
                fc = e.get("failure_count", 0)
                kind_note = f", procedure, {sc} successes, {fc} failures"
            elif e.get("kind") != "preference":
                kind_note = f", {e.get('kind', '')}"
            print(f"  {e['id']} ({e['confidence']:.2f}) - {e.get('domain', 'general')}{kind_note}")
    else:
        print("Project: (no project entries)")

    # Check observations
    obs_path = PRISM_HOME / "projects" / project_id / "observations.jsonl"
    if obs_path.exists():
        obs_count = sum(1 for _ in open(obs_path))
        print(f"\nPending observations: {obs_count}")
    else:
        print("\nPending observations: 0")

    # Archived
    archive_dir = PRISM_HOME / "archive"
    if archive_dir.exists():
        archived = list(archive_dir.glob("*.md"))
        if archived:
            print(f"Archived: {len(archived)} entries")


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

    # Auto-sync .claude/prism.md (CTX-04, D-07: synchronous)
    from .sync import sync_claude_code
    sync_claude_code(project_id)

    print(f"Learned: {entry_id} (confidence: 0.9)")
    print(f"File: {filepath}")


def cmd_forget(entry_id: str) -> None:
    """Archive an entry (remove from active context)."""
    entry = get_entry(entry_id)
    if not entry:
        print(f"Entry not found: {entry_id}")
        return

    # Move file to archive
    source_path = PRISM_HOME / entry.get("path", "")
    if source_path.exists():
        archive_dir = PRISM_HOME / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / source_path.name
        shutil.move(str(source_path), str(dest))
        print(f"Archived: {source_path.name} -> archive/")

    # Remove from index
    remove_entry(entry_id)
    # Auto-sync .claude/prism.md (CTX-04, D-07: synchronous)
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

    # Archive old entry
    cmd_forget(entry_id)

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


def cmd_maintain() -> None:
    """Run confidence decay and archive expired entries."""
    config = get_config()
    decay_rate = config.get("decay_rate_per_week", 0.02)
    archive_threshold = config.get("archive_threshold", 0.2)

    index = load_index()
    today = date.today()
    decayed = 0
    archived = 0

    for entry in list(index["engrams"]):
        # Skip pinned entries
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
            # Archive the entry
            source_path = PRISM_HOME / entry.get("path", "")
            if source_path.exists():
                archive_dir = PRISM_HOME / "archive"
                archive_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source_path), str(archive_dir / source_path.name))
            remove_entry(entry["id"])
            archived += 1
            print(f"  Archived: {entry['id']} (confidence: {old_conf:.2f} -> {new_conf:.2f})")
        elif new_conf < old_conf:
            update_confidence(entry["id"], new_conf)
            decayed += 1

    print(f"Maintenance complete: {decayed} decayed, {archived} archived")

    # Auto-sync .claude/prism.md if anything changed (CTX-04, D-07)
    if decayed > 0 or archived > 0:
        from .project import detect_project_id
        from .sync import sync_claude_code
        project_id = detect_project_id()
        sync_claude_code(project_id)


def cmd_procedures(project_id: Optional[str] = None) -> None:
    """List all procedures with success/failure counts."""
    if not project_id:
        project_id = detect_project_id()

    procedures = list_entries(project_id=project_id, kind="procedure")

    if not procedures:
        print("No procedures found.")
        return

    print(f"Procedures ({len(procedures)}):")
    print()
    for p in sorted(procedures, key=lambda x: -x.get("confidence", 0)):
        trigger = p.get("trigger", "").strip('"')
        sc = p.get("success_count", 0)
        fc = p.get("failure_count", 0)
        conf = p.get("confidence", 0)
        scope = p.get("scope", "project")
        print(f"  [{conf:.2f}] {trigger}")
        print(f"         {sc} successes, {fc} failures | scope: {scope} | id: {p['id']}")
        print()


def cmd_config(key=None, value=None) -> None:
    """Get or set configuration values.

    No args: show all config as formatted output (D-11).
    One arg: show value for that key.
    Two args: set key to value (auto-parses numbers and bools).

    Supports dotted keys for nested access: extraction.threshold -> extract_threshold (D-10).
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

    # Normalize dotted key: extraction.threshold -> extract_threshold
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

    lines = obs_path.read_text().strip().split("\n")
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
