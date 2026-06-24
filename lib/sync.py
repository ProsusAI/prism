# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

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

from .config import PRISM_HOME, PUSH_KINDS, get_config, get_engrams_dir
from .index import list_entries, load_index
from .project import get_project_root

_CURSOR_FRONTMATTER = (
    "---\n"
    "description: Prism active knowledge — project-specific engrams and team patterns\n"
    "alwaysApply: true\n"
    "---\n\n"
)


def sync_context(project_id: str, output_dir: Optional[str] = None) -> str:
    """Generate IDE context files with hybrid push/pull approach.

    PUSH (in this file): corrections, pinned, top preferences, session-validated patterns.
    PULL (via MCP): full knowledge base searchable on demand.

    Returns the path to the generated file.
    """
    config = get_config()
    max_lines = config.get("max_context_lines", 100)

    # Collect all entries for selection
    all_entries = _collect_entries(project_id)
    if not all_entries:
        root = Path(output_dir) if output_dir else get_project_root()
        for stale in [
            root / ".claude" / "prism.md",
            root / ".cursor" / "rules" / "prism.mdc",
        ]:
            if stale.exists():
                stale.unlink()
        return ""

    # Select what goes into the system prompt (the PUSH layer).
    # NOTE: selection is READ-ONLY. It must never write confidence -- placement is a
    # consequence of kind, never an input to the score (confidence_plan.md principle #1).
    # The old reinforce_entries() call here was the circular "rich-get-richer" loop.
    prompt_entries = _select_prompt_entries(all_entries)
    publish_ready = _find_publish_ready(all_entries)

    # Log the surfacing event so `prism stats` can distinguish engrams *pushed* into
    # context from engrams Claude actively *pulled* via MCP. This is logging only -- it
    # records WHICH engrams were surfaced, and deliberately does NOT reinforce them
    # (selection stays read-only on confidence, per confidence_plan.md principle #1).
    # Never fatal.
    try:
        from .storage import insert_retrieval, SYNC_PUSH_TOOL
        insert_retrieval(
            project_id=project_id,
            source="sync",
            tool=SYNC_PUSH_TOOL,
            query="",
            engram_ids=[e["id"] for e in prompt_entries],
        )
    except Exception:
        pass

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

    # Write to Claude Code path
    root = Path(output_dir) if output_dir else get_project_root()
    claude_path = root / ".claude" / "prism.md"
    claude_path.parent.mkdir(parents=True, exist_ok=True)
    claude_path.write_text(content)
    print(f"Generated {claude_path} ({len(lines)} lines, {len(prompt_entries)} pushed, {mcp_only_count} via MCP)")

    # Write to Cursor path (.mdc with alwaysApply frontmatter)
    cursor_rules_dir = root / ".cursor" / "rules"
    cursor_rules_dir.mkdir(parents=True, exist_ok=True)
    legacy_md = cursor_rules_dir / "prism.md"
    if legacy_md.exists():
        legacy_md.unlink()
    cursor_path = cursor_rules_dir / "prism.mdc"
    cursor_path.write_text(_CURSOR_FRONTMATTER + content)
    print(f"Generated {cursor_path}")

    return str(claude_path)


# Backward-compat alias
sync_claude_code = sync_context


def _select_prompt_entries(entries: list, max_items: int = 10) -> list:
    """Select which entries get pushed into the system prompt (the PUSH lane).

    Routing is by KIND, not by confidence (confidence_plan.md §5). The push lane is the
    small, reserved channel for knowledge whose value exists only if present *before*
    Claude acts -- corrections and preferences (PUSH_KINDS) -- plus anything manually
    pinned. Everything else lives in the MCP pull lane and is reached on demand; a high
    confidence score no longer buys a prompt spot, and a low one no longer loses it.

    Read-only: this function must never mutate confidence (principle #1).

    Priority when capped at max_items: pinned, then corrections (never dropped before
    preferences -- you can't search for past mistakes), then preferences. Within each
    tier, higher confidence first as a tiebreak only.
    """
    def by_conf(es):
        return sorted(es, key=lambda e: -e.get("confidence", 0))

    pinned = by_conf([e for e in entries if e.get("pinned")])
    corrections = by_conf([e for e in entries
                           if e.get("kind") == "correction" and not e.get("pinned")])
    preferences = by_conf([e for e in entries
                           if e.get("kind") == "preference" and not e.get("pinned")])

    selected = []
    for e in pinned + corrections + preferences:
        if e not in selected:
            selected.append(e)

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
