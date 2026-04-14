"""Context sync - generates IDE-specific context files from the knowledge index.

Hybrid push/pull approach:
- PUSH (system prompt): corrections, pinned, top preferences, session-validated imports
- PULL (MCP server): full knowledge base searchable on demand
"""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import PRISM_HOME, get_config, get_engrams_dir
from .index import list_entries, load_index


def sync_claude_code(project_id: str, output_dir: Optional[str] = None) -> str:
    """Generate .claude/prism.md with hybrid push/pull approach.

    PUSH (in this file): corrections, pinned, top preferences, session-validated patterns.
    PULL (via MCP): full knowledge base searchable on demand.

    Returns the path to the generated file.
    """
    config = get_config()
    max_lines = config.get("max_context_lines", 100)

    # Collect all entries for selection
    all_entries = _collect_entries(project_id)
    if not all_entries:
        return ""

    # Select what goes into the system prompt (the PUSH layer)
    prompt_entries = _select_prompt_entries(all_entries)
    publish_ready = _find_publish_ready(all_entries)

    # Categorize selected entries
    corrections = [e for e in prompt_entries if e.get("kind") == "correction"]
    pinned = [e for e in prompt_entries if e.get("pinned") and e.get("kind") != "correction"]
    validated = [e for e in prompt_entries
                 if e.get("source") == "lens" and e.get("confidence", 0) > 0.80]
    preferences = [e for e in prompt_entries
                   if e not in corrections and e not in pinned and e not in validated]

    # Count what's NOT in the prompt (available via MCP only)
    mcp_only_count = len(all_entries) - len(prompt_entries)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Learned Knowledge (Prism)",
        f"<!-- Updated: {timestamp} | {len(prompt_entries)} pushed, {mcp_only_count} via MCP -->",
        "",
    ]

    # Corrections - MUST be pushed (Claude can't be relied on to search for past mistakes)
    if corrections:
        lines.append("## Corrections -- do NOT repeat these")
        lines.append("")
        for e in corrections:
            content = _read_entry_summary(e)
            if content:
                lines.append(f"- {content}")
        lines.append("")

    # Pinned entries
    if pinned:
        lines.append("## Pinned")
        lines.append("")
        for e in pinned:
            content = _read_entry_summary(e)
            if content:
                lines.append(f"- {content} ({e['confidence']:.2f})")
        lines.append("")

    # Top preferences and patterns (session-learned)
    if preferences:
        lines.append("## Key Preferences")
        lines.append("")
        for e in preferences:
            content = _read_entry_summary(e)
            if content:
                kind_tag = f" [{e['kind']}]" if e.get("kind") not in ("preference",) else ""
                lines.append(f"- {content} ({e['confidence']:.2f}{kind_tag})")
        lines.append("")

    # Session-validated codebase patterns (imports reinforced past 0.80)
    if validated:
        lines.append("## Session-Validated Codebase Patterns")
        lines.append("")
        for e in validated:
            content = _read_entry_summary(e)
            if content:
                lines.append(f"- {content} (reinforced to {e['confidence']:.2f})")
        lines.append("")

    # Publish-ready notifications
    if publish_ready:
        lines.append("## Publish-Ready")
        lines.append("")
        for e in publish_ready:
            ev = e.get("evidence_count", 0)
            lines.append(
                f"- {e['id']} ({e['confidence']:.2f}, {ev} evidence)"
                f" -- `prism promote {e['id']}`"
            )
        lines.append("")

    # MCP footer
    lines.append("---")
    if mcp_only_count > 0:
        lines.append(f"Full knowledge base ({mcp_only_count} more entries) available via prism MCP tools.")
    else:
        lines.append("Full knowledge base available via prism MCP tools.")
    lines.append("")
    lines.append("**Search** (`prism_search`): when encountering errors, starting tasks, or making design decisions.")
    lines.append("")
    lines.append("**Record** (`prism_record`): proactively record knowledge when you discover it:")
    lines.append("- Design decisions with rationale (\"chose X because Y\")")
    lines.append("- Project conventions and coding standards")
    lines.append("- Domain facts (API limits, service ownership, deployment rules)")
    lines.append("- Non-obvious error resolutions that required trial-and-error")
    lines.append("- User corrections or preference signals (\"actually, use X instead\")")
    lines.append("")
    lines.append("**When to record** (evaluate after completing non-trivial tasks):")
    lines.append("- Did you try an approach that failed before finding what works?")
    lines.append("- Did the user correct you or express a preference?")
    lines.append("- Was the solution non-obvious or project-specific?")
    lines.append("- Would this knowledge help in a future session?")
    lines.append("")
    lines.append("Don't record one-off task instructions, exploratory discussion, or obvious patterns.")

    # Trim to max lines
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1]
        lines.append(f"\n# ... truncated to {max_lines} lines. Run `prism status` for full list.")

    content = "\n".join(lines) + "\n"

    # Write to output directory
    if output_dir:
        out_path = Path(output_dir) / ".claude" / "prism.md"
    else:
        out_path = Path.cwd() / ".claude" / "prism.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content)
    print(f"Generated {out_path} ({len(lines)} lines, {len(prompt_entries)} pushed, {mcp_only_count} via MCP)")
    return str(out_path)


def _select_prompt_entries(entries: list, max_items: int = 10) -> list:
    """Select which entries get pushed into the system prompt.

    Priority order:
    1. Pinned entries (always included)
    2. Corrections with conf >= 0.8 (must be pushed -- Claude can't search for past mistakes)
    3. Top N by confidence -- but imports only if session-reinforced (conf > 0.80)
    """
    selected = []

    # 1. Pinned
    for e in entries:
        if e.get("pinned") and e not in selected:
            selected.append(e)

    # 2. Corrections
    for e in entries:
        if (e.get("kind") == "correction"
                and e.get("confidence", 0) >= 0.8
                and e not in selected):
            selected.append(e)

    # 3. Top by confidence (imports only if reinforced past 0.80)
    remaining = []
    for e in entries:
        if e in selected:
            continue
        # Imports must be reinforced past their starting confidence to earn a prompt spot
        if e.get("source") == "lens" and e.get("confidence", 0) <= 0.80:
            continue
        remaining.append(e)

    remaining.sort(key=lambda e: -e.get("confidence", 0))
    selected += remaining[:max_items - len(selected)]

    return selected[:max_items]


def _find_publish_ready(entries: list) -> list:
    """Find session-learned entries mature enough to promote.

    Gates: confidence >= 0.7, evidence >= 3, not imported, not already published.
    """
    ready = []
    for e in entries:
        if (e.get("confidence", 0) >= 0.7
                and e.get("evidence_count", 0) >= 3
                and e.get("source") != "lens"
                and not e.get("published")
                and e.get("scope") == "global"):
            ready.append(e)
    return ready


def _collect_entries(project_id: str) -> list:
    """Collect and sort relevant entries for context generation."""
    config = get_config()
    entries = list_entries(project_id=project_id, min_confidence=0.0)

    # Filter out archived (below threshold)
    threshold = config.get("archive_threshold", 0.2)
    entries = [e for e in entries if e.get("confidence", 0) >= threshold]

    # Pinned entries first, then sort by confidence desc, then recency
    entries.sort(key=lambda e: (
        -int(e.get("pinned", False)),
        -e.get("confidence", 0),
        e.get("last_observed", ""),
    ), reverse=False)

    # Re-sort: pinned first, then confidence descending
    entries.sort(key=lambda e: (
        not e.get("pinned", False),
        -e.get("confidence", 0),
    ))

    return entries


def _read_entry_summary(entry: dict) -> str:
    """Read the first non-header line of an entry's body as summary."""
    path = entry.get("path", "")
    if not path:
        return entry.get("trigger", "").strip('"')

    full_path = PRISM_HOME / path
    if not full_path.exists():
        return entry.get("trigger", "").strip('"')

    try:
        content = full_path.read_text()
        # Skip frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].strip()
            else:
                body = content
        else:
            body = content

        # Return first non-empty, non-header line
        for line in body.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                return line
    except OSError:
        pass

    return entry.get("trigger", "").strip('"')


def _read_entry_steps(entry: dict) -> list:
    """Read the ## Steps section from a procedure entry."""
    path = entry.get("path", "")
    if not path:
        return []

    full_path = PRISM_HOME / path
    if not full_path.exists():
        return []

    try:
        content = full_path.read_text()
        # Find ## Steps section
        in_steps = False
        steps = []
        for line in content.split("\n"):
            if line.strip().startswith("## Steps"):
                in_steps = True
                continue
            if in_steps:
                if line.strip().startswith("## "):
                    break
                if line.strip():
                    steps.append(line)
        return steps
    except OSError:
        return []
