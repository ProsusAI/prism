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


def _write_index_file(index: dict, path: Path, tmp_path: Path, bak_path: Path) -> None:
    """Write index to disk. Caller must hold the lock."""
    with open(tmp_path, "w") as f:
        json.dump(index, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    if path.exists():
        shutil.copy2(str(path), str(bak_path))
    os.rename(str(tmp_path), str(path))


def _update_index(fn) -> None:
    """Acquire lock, load index, apply fn(index), write back atomically.

    fn receives the mutable index dict. Any mutations are persisted.
    Use a closure to capture return values from fn.
    """
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    bak_path = path.with_suffix(".bak")
    lock_path = path.with_suffix(".lock")

    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if path.exists():
            try:
                with open(path) as f:
                    index = json.load(f)
            except (json.JSONDecodeError, OSError):
                index = {"engrams": []}
        else:
            index = {"engrams": []}
        fn(index)
        _write_index_file(index, path, tmp_path, bak_path)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


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

    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        _write_index_file(index, path, tmp_path, bak_path)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def add_entry(entry: dict) -> None:
    """Add or update a knowledge entry in the index."""
    def _fn(index):
        index["engrams"] = [e for e in index["engrams"] if e["id"] != entry["id"]]
        index["engrams"].append(entry)
    _update_index(_fn)


def merge_file_entry_with_index(file_entry: dict, existing: dict) -> dict:
    """Merge parsed engram file metadata with an existing index row.

    Structural fields (kind, trigger, tags, path, ...) come from the file.
    Reinforcement metrics use the higher confidence, higher evidence_count,
    and later last_observed. Index-only keys (e.g. source, published) are kept.
    """
    merged = dict(file_entry)
    merged["confidence"] = round(
        max(float(existing.get("confidence", 0)), float(file_entry.get("confidence", 0))),
        3,
    )
    merged["evidence_count"] = max(
        int(existing.get("evidence_count", 0)),
        int(file_entry.get("evidence_count", 0)),
    )
    merged["last_observed"] = max(
        existing.get("last_observed") or "",
        file_entry.get("last_observed") or "",
    )
    merged["success_count"] = max(
        int(existing.get("success_count", 0)),
        int(file_entry.get("success_count", 0)),
    )
    merged["failure_count"] = max(
        int(existing.get("failure_count", 0)),
        int(file_entry.get("failure_count", 0)),
    )
    if existing.get("pinned") or file_entry.get("pinned"):
        merged["pinned"] = True
    for key in ("source", "published"):
        if key in existing:
            merged[key] = existing[key]
    return merged


def remove_entry(entry_id: str) -> Optional[dict]:
    """Remove an entry from the index. Returns the removed entry or None."""
    result: list[Optional[dict]] = [None]

    def _fn(index):
        kept, removed = [], None
        for e in index["engrams"]:
            if e["id"] == entry_id:
                removed = e
            else:
                kept.append(e)
        if removed:
            index["engrams"] = kept
            result[0] = removed

    _update_index(_fn)
    return result[0]


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
    result = [False]

    def _fn(index):
        for e in index["engrams"]:
            if e["id"] == entry_id:
                e["confidence"] = round(new_confidence, 3)
                result[0] = True
                break

    _update_index(_fn)
    return result[0]


def update_last_observed(entry_id: str, observed_date: Optional[str] = None) -> bool:
    """Update the last_observed date of an entry."""
    obs_date = observed_date or date.today().isoformat()
    result = [False]

    def _fn(index):
        for e in index["engrams"]:
            if e["id"] == entry_id:
                e["last_observed"] = obs_date
                result[0] = True
                break

    _update_index(_fn)
    return result[0]


def reinforce_entries(entry_ids: list[str]) -> int:
    """Increment evidence_count, refresh last_observed, and boost confidence for a set of entries.

    Loads the index once under lock, updates all matching entries, saves once. Used by
    sync to credit engrams that were selected for the prism.md push layer --
    otherwise context-injected engrams decay even while actively in use.

    Confidence is boosted by +0.02 (capped at 0.95), matching mcp_server.py so
    push-layer engrams stay at parity with MCP-queried ones.

    Returns the number of entries actually updated.
    """
    if not entry_ids:
        return 0
    id_set = set(entry_ids)
    today = date.today().isoformat()
    result = [0]
    synced: list[dict] = []

    def _fn(index):
        updated = 0
        for e in index["engrams"]:
            if e["id"] in id_set:
                e["evidence_count"] = e.get("evidence_count", 0) + 1
                e["last_observed"] = today
                e["confidence"] = round(min(0.95, e.get("confidence", 0.5) + 0.02), 3)
                synced.append(dict(e))
                updated += 1
        result[0] = updated

    _update_index(_fn)
    if synced:
        from .frontmatter import sync_entries_to_files
        sync_entries_to_files(synced)
    return result[0]


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
