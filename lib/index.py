"""Prism index management - the master index of all knowledge entries."""

import fcntl
import json
import os
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

from .config import PRISM_HOME, get_config
from .confidence import decay, reinforce


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
    # confidence_base + last_used are index-only (not stored in engram frontmatter),
    # so they survive a frontmatter resync only by being carried from the index row.
    merged["last_used"] = max(
        existing.get("last_used") or "",
        file_entry.get("last_used") or existing.get("last_observed") or "",
    )
    merged["confidence_base"] = round(
        max(
            float(existing.get("confidence_base", existing.get("confidence", 0))),
            merged["confidence"],
        ),
        3,
    )
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
    """Fire one use-event for a set of engrams: a daily-idempotent confidence impulse.

    A use-event is a *real* use -- an MCP retrieval, or an overlap-detected application
    of an injected (prism.md) engram. Both fire the identical impulse; they differ only
    in trigger (confidence_plan.md §5).

    Idempotent once per UTC-day per engram: if an engram was already used today this is a
    no-op for it. This is what kills multi-session inflation -- N parallel sessions (or N
    background reviews in one session) crediting the same engram count as one impulse.

    The impulse is diminishing-returns toward the ceiling (no hard 0.95 wall). It is
    applied to the *current* confidence, which is first recomputed from confidence_base
    by decaying over the idle interval -- so an engram that decayed since its last use
    builds its impulse on the decayed value, keeping confidence_base self-consistent.

    Returns the number of entries actually moved (already-used-today entries don't count).
    """
    if not entry_ids:
        return 0
    id_set = set(entry_ids)
    today = date.today()
    today_iso = today.isoformat()

    config = get_config()
    alpha = config.get("reinforce_alpha", 0.15)
    ceiling = config.get("confidence_ceiling", 1.0)
    floor = config.get("decay_floor", 0.1)
    half_life_days = config.get("decay_half_life_weeks", 4) * 7
    grace = config.get("decay_grace_days", 3)

    result = [0]
    synced: list[dict] = []

    def _fn(index):
        updated = 0
        for e in index["engrams"]:
            if e["id"] not in id_set:
                continue
            if e.get("last_used") == today_iso:
                continue  # already credited today -- kills multi-session inflation

            base = float(e.get("confidence_base", e.get("confidence", 0.5)))
            last_used = e.get("last_used") or e.get("last_observed")
            try:
                idle = (today - date.fromisoformat(last_used)).days if last_used else 0
            except ValueError:
                idle = 0
            current = decay(base, max(0, idle), floor, half_life_days, grace)
            new_base = reinforce(current, alpha, ceiling)

            e["confidence_base"] = new_base
            e["confidence"] = new_base
            e["last_used"] = today_iso
            e["last_observed"] = today_iso
            e["evidence_count"] = e.get("evidence_count", 0) + 1
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
    last_observed: Optional[str] = None,
    last_used: Optional[str] = None,
) -> dict:
    """Build a standard index entry dict."""
    today = date.today().isoformat()
    return {
        "id": entry_id,
        "kind": kind,
        "trigger": trigger,
        "confidence": round(confidence, 3),
        # confidence_base = the value at the last use-event; decay is recomputed from
        # this baseline so it never compounds across maintenance runs (see confidence.py).
        "confidence_base": round(confidence, 3),
        "domain": domain,
        "scope": scope,
        "project_id": project_id,
        "path": path,
        "last_observed": last_observed or today,
        # last_used = last real use-event (MCP retrieval or overlap-detected application).
        # Drives both reinforcement idempotency and decay. Distinct from last_observed.
        "last_used": last_used or today,
        "evidence_count": evidence_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "pinned": pinned,
        "tags": tags or [],
    }
