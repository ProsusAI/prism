"""Prism index management - the master index of all knowledge entries."""

import fcntl
import json
import os
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

from .config import PRISM_HOME


def _index_path() -> Path:
    return PRISM_HOME / "index.json"


def load_index() -> dict:
    """Load the master index. Returns {"engrams": [...]}."""
    path = _index_path()
    if not path.exists():
        return {"engrams": []}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"engrams": []}


def save_index(index: dict) -> None:
    """Save the master index atomically with file locking.

    Uses fcntl.flock() + write to .tmp + os.rename() + backup to .bak
    to prevent corruption from concurrent writes.
    """
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(".tmp")
    bak_path = path.with_suffix(".bak")
    lock_path = path.with_suffix(".lock")

    # Acquire file lock
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        # Write to temp file first
        with open(tmp_path, "w") as f:
            json.dump(index, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        # Backup existing index
        if path.exists():
            shutil.copy2(str(path), str(bak_path))

        # Atomic rename
        os.rename(str(tmp_path), str(path))

    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def add_entry(entry: dict) -> None:
    """Add or update an knowledge entry in the index."""
    index = load_index()
    # Remove existing entry with same ID if present
    index["engrams"] = [e for e in index["engrams"] if e["id"] != entry["id"]]
    index["engrams"].append(entry)
    save_index(index)


def remove_entry(entry_id: str) -> Optional[dict]:
    """Remove an entry from the index. Returns the removed entry or None."""
    index = load_index()
    removed = None
    new_entries = []
    for e in index["engrams"]:
        if e["id"] == entry_id:
            removed = e
        else:
            new_entries.append(e)
    if removed:
        index["engrams"] = new_entries
        save_index(index)
    return removed


def get_entry(entry_id: str) -> Optional[dict]:
    """Look up an entry by ID."""
    index = load_index()
    for e in index["engrams"]:
        if e["id"] == entry_id:
            return e
    return None


def list_entries(
    project_id: Optional[str] = None,
    kind: Optional[str] = None,
    scope: Optional[str] = None,
    min_confidence: float = 0.0,
) -> list:
    """List entries with optional filters."""
    index = load_index()
    results = index["engrams"]

    if project_id:
        results = [e for e in results if e.get("project_id") == project_id or e.get("scope") == "global"]
    if kind:
        results = [e for e in results if e.get("kind") == kind]
    if scope:
        results = [e for e in results if e.get("scope") == scope]
    if min_confidence > 0:
        results = [e for e in results if e.get("confidence", 0) >= min_confidence]

    return results


def update_confidence(entry_id: str, new_confidence: float) -> bool:
    """Update the confidence score of an entry in the index."""
    index = load_index()
    for e in index["engrams"]:
        if e["id"] == entry_id:
            e["confidence"] = round(new_confidence, 3)
            save_index(index)
            return True
    return False


def update_last_observed(entry_id: str, observed_date: Optional[str] = None) -> bool:
    """Update the last_observed date of an entry."""
    index = load_index()
    obs_date = observed_date or date.today().isoformat()
    for e in index["engrams"]:
        if e["id"] == entry_id:
            e["last_observed"] = obs_date
            save_index(index)
            return True
    return False


def reinforce_entries(entry_ids: list[str]) -> int:
    """Increment evidence_count, refresh last_observed, and boost confidence for a set of entries.

    Loads the index once, updates all matching entries, saves once. Used by
    sync to credit engrams that were selected for the prism.md push layer --
    otherwise context-injected engrams decay even while actively in use.

    Confidence is boosted by +0.02 (capped at 0.95), matching `_reinforce_batch`
    in mcp_server.py so push-layer engrams stay at parity with MCP-queried ones.

    Returns the number of entries actually updated.
    """
    if not entry_ids:
        return 0
    id_set = set(entry_ids)
    today = date.today().isoformat()
    index = load_index()
    updated = 0
    for e in index["engrams"]:
        if e["id"] in id_set:
            e["evidence_count"] = e.get("evidence_count", 0) + 1
            e["last_observed"] = today
            old_conf = e.get("confidence", 0.5)
            # Cap at 0.95 -- mirrors _reinforce_batch in mcp_server.py so prism.md
            # push layer accrues confidence at the same rate as MCP queries
            e["confidence"] = round(min(0.95, old_conf + 0.02), 3)
            updated += 1
    if updated:
        save_index(index)
    return updated


def build_index_entry(
    entry_id: str,
    kind: str,
    trigger: str,
    confidence: float,
    domain: str,
    scope: str,
    project_id: str,
    path: str,
    evidence_count: int = 1,
    tags: Optional[list] = None,
    success_count: int = 0,
    failure_count: int = 0,
    pinned: bool = False,
) -> dict:
    """Build a standard index entry dict."""
    return {
        "id": entry_id,
        "kind": kind,
        "trigger": trigger,
        "confidence": round(confidence, 3),
        "domain": domain,
        "scope": scope,
        "project_id": project_id,
        "path": path,
        "last_observed": date.today().isoformat(),
        "evidence_count": evidence_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "pinned": pinned,
        "tags": tags or [],
    }
