# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Update engram markdown YAML frontmatter to match index.json."""

from pathlib import Path

from . import config

_FRONTMATTER_KEYS = frozenset({"confidence", "evidence_count", "last_observed"})


def _format_frontmatter_line(key: str, value: object) -> str:
    if key == "confidence":
        return f"confidence: {round(float(value), 3)}\n"
    if key == "evidence_count":
        return f"evidence_count: {int(value)}\n"
    if key == "last_observed":
        return f"last_observed: {value}\n"
    return f"{key}: {value}\n"


def update_frontmatter(path: Path, updates: dict[str, object]) -> bool:
    """Rewrite frontmatter fields in an engram .md file. Returns True if written."""
    filtered = {k: v for k, v in updates.items() if k in _FRONTMATTER_KEYS}
    if not filtered or not path.is_file():
        return False
    try:
        text = path.read_text()
    except OSError:
        return False

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return False

    in_frontmatter = False
    pending = dict(filtered)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        if not in_frontmatter:
            continue
        for key in list(pending):
            if stripped.startswith(f"{key}:"):
                lines[i] = _format_frontmatter_line(key, pending.pop(key))
                break

    if pending:
        # Insert missing keys before the closing --- of frontmatter.
        close_idx = None
        in_fm = False
        for i, line in enumerate(lines):
            if line.strip() == "---":
                if not in_fm:
                    in_fm = True
                elif in_fm:
                    close_idx = i
                    break
        if close_idx is not None:
            insert = [_format_frontmatter_line(k, v) for k, v in pending.items()]
            lines[close_idx:close_idx] = insert

    try:
        path.write_text("".join(lines))
    except OSError:
        return False
    return True


def sync_entry_to_file(entry: dict) -> bool:
    """Write index confidence, evidence_count, and last_observed to the engram file."""
    path_str = entry.get("path", "")
    if not path_str:
        return False
    prism_home = config.PRISM_HOME
    full_path = (prism_home / path_str).resolve()
    if not str(full_path).startswith(str(prism_home.resolve())):
        return False
    if not full_path.is_file():
        return False
    updates = {
        k: entry[k]
        for k in _FRONTMATTER_KEYS
        if k in entry
    }
    return update_frontmatter(full_path, updates)


def sync_entries_to_files(entries: list[dict]) -> int:
    """Sync multiple index entries to disk. Returns count of files updated."""
    return sum(1 for e in entries if sync_entry_to_file(e))
