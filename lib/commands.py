"""User-facing prism commands: learn, forget, correct, status, maintain, procedures."""

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

    Creates ~/.prism/ structure, then writes project-scoped hook configs:
      - .claude/settings.local.json (Claude Code hooks)
    """
    from .config import init_prism_home
    init_prism_home()
    project_id = detect_project_id()
    if project_id != "global":
        ensure_dirs(project_id)
        # Write project.json
        project_dir = PRISM_HOME / "projects" / project_id
        project_json = project_dir / "project.json"
        if not project_json.exists():
            from .project import detect_project_remote
            info = {
                "name": detect_project_name(),
                "root": os.getcwd(),
                "remote": detect_project_remote(),
                "project_id": project_id,
                "last_seen": date.today().isoformat(),
            }
            project_json.write_text(json.dumps(info, indent=2) + "\n")

    # Write hook configs and register MCP server
    _setup_claude_code_hooks()
    _setup_mcp_server(project_id)

    print(f"\nPrism initialized at {PRISM_HOME}")
    print(f"Project: {detect_project_name()} ({project_id})")
    print(f"Hooks:  project ({Path.cwd().name})")
    print(f"MCP:    knowledge server registered")
    print()

    print("You're set. Start coding - observations will accumulate automatically.")
    print("Then run:")
    print("  prism extract    # analyze observations into knowledge")
    print("  prism sync       # generate IDE context files")


CLAUDE_CODE_HOOKS = {
    "PreToolUse": [
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": str(PRISM_HOME / "hooks" / "capture.sh") + " pre",
                }
            ],
        }
    ],
    "PostToolUse": [
        {
            "matcher": "*",
            "hooks": [
                {
                    "type": "command",
                    "command": str(PRISM_HOME / "hooks" / "capture.sh") + " post",
                    "async": True,
                }
            ],
        }
    ],
}


def _setup_claude_code_hooks() -> None:
    """Write Claude Code hook config to project settings.local.json."""
    settings_path = Path.cwd() / ".claude" / "settings.local.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Merge with existing settings (don't clobber other config)
    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    existing_hooks = existing.get("hooks", {})

    # Merge our hooks with existing ones (don't duplicate)
    for event, hook_list in CLAUDE_CODE_HOOKS.items():
        if event not in existing_hooks:
            existing_hooks[event] = hook_list
        else:
            # Check if our hook is already there
            existing_commands = set()
            for matcher_group in existing_hooks[event]:
                for h in matcher_group.get("hooks", []):
                    existing_commands.add(h.get("command", ""))
            our_command = hook_list[0]["hooks"][0]["command"]
            if our_command not in existing_commands:
                existing_hooks[event].extend(hook_list)

    existing["hooks"] = existing_hooks
    settings_path.write_text(json.dumps(existing, indent=2) + "\n")
    print(f"  Claude Code hooks: {settings_path}")


def _setup_mcp_server(project_id: str) -> None:
    """Register the prism MCP server in Claude Code settings."""
    import sys

    settings_path = Path.cwd() / ".claude" / "settings.local.json"

    # The settings file should already exist from hook setup
    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    mcp_servers = existing.get("mcpServers", {})

    # Find the MCP server script
    mcp_script = PRISM_HOME / "lib" / "mcp_server.py"
    if not mcp_script.exists():
        # Fallback to repo location
        mcp_script = Path(__file__).parent / "mcp_server.py"

    # Build env for MCP server
    mcp_env = {"PRISM_PROJECT": project_id}

    mcp_servers["prism"] = {
        "command": sys.executable,
        "args": [str(mcp_script)],
        "env": mcp_env,
    }

    existing["mcpServers"] = mcp_servers

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")
    print(f"  MCP server:       {settings_path}")


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

    print(f"Learned: {entry_id} (confidence: 0.9)")
    print(f"File: {filepath}")
    print("Run 'prism sync' to update IDE context files.")


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
    print(f"Forgot: {entry_id}")
    print("Run 'prism sync' to update IDE context files.")


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

    print(f"Corrected: {entry_id} -> {new_id} (confidence: 0.9)")
    print("Run 'prism sync' to update IDE context files.")


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


def cmd_log(last_n: int = 20, extractions: bool = False, insights: bool = False) -> None:
    """Show recent observations, extraction history, or session insights."""
    if extractions:
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
                print(f"  [{ts}] {decision}: {candidate}")
            except json.JSONDecodeError:
                continue
    elif insights:
        project_id = detect_project_id()
        obs_path = PRISM_HOME / "projects" / project_id / "observations.jsonl"
        # Also check archived observations
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
        print(f"Session insights ({len(all_insights)} total):\n")
        for entry in all_insights[-last_n:]:
            ts = entry.get("timestamp", "?")[:10]
            kind = entry.get("insight_type", "unknown")
            summary = entry.get("input_summary", "")
            evidence = entry.get("evidence", "")
            print(f"  [{kind}] {summary}")
            if evidence:
                print(f"    evidence: {evidence[:120]}")
            print()
    else:
        project_id = detect_project_id()
        obs_path = PRISM_HOME / "projects" / project_id / "observations.jsonl"
        if not obs_path.exists():
            print("No observations found.")
            return
        print(f"Recent observations (last {last_n}):")
        lines = obs_path.read_text().strip().split("\n")
        for line in lines[-last_n:]:
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "?")[:19]
                tool = entry.get("tool", "?")
                event = entry.get("event", "?")
                summary = entry.get("input_summary", "")[:60]
                print(f"  [{ts}] {event}: {tool} - {summary}")
            except json.JSONDecodeError:
                continue


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
