#!/usr/bin/env python3
"""
migrate_observations.py — migrate Prism JSONL observations to SQLite.

Run this once after upgrading to the SQLite-backed version of Prism.
Safe to re-run: projects already in SQLite are skipped, and JSONL files
are archived (renamed) only after a successful import.

Usage:
    python3 migrate_observations.py [options]

Options:
    --dry-run           Print what would be imported without writing anything
    --mark-pending      Leave migrated rows as unextracted so the extraction
                        pipeline re-processes them (default: mark as extracted)
    --no-archive        Keep .jsonl files in place after migration (do not rename)
    --prism-home PATH   Override PRISM_HOME (default: $PRISM_HOME or ~/.prism)
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Migrate Prism JSONL observations to SQLite.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--dry-run", action="store_true", help="Print plan, write nothing")
    p.add_argument(
        "--mark-pending",
        action="store_true",
        help="Keep rows unextracted so the pipeline re-processes them",
    )
    p.add_argument(
        "--no-archive",
        action="store_true",
        help="Keep .jsonl files in place after migration",
    )
    p.add_argument("--prism-home", metavar="PATH", help="Override PRISM_HOME")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resolve_prism_home(override: str | None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("PRISM_HOME", "")
    return Path(env).expanduser() if env else Path.home() / ".prism"


def find_jsonl_files(prism_home: Path) -> list[tuple[str, Path]]:
    """Return [(project_id, jsonl_path)] for every observations.jsonl found."""
    results = []
    projects_dir = prism_home / "projects"
    if not projects_dir.is_dir():
        return results
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        jsonl = project_dir / "observations.jsonl"
        if jsonl.is_file() and jsonl.stat().st_size > 0:
            results.append((project_dir.name, jsonl))
    return results


# ---------------------------------------------------------------------------
# Timestamp parsing (mirrors storage.parse_observation_timestamp)
# ---------------------------------------------------------------------------

def parse_ts(raw: str | None) -> int | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    try:
        iso = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, OSError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# SQLite helpers (inline — no imports from lib/)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  ide TEXT NOT NULL DEFAULT '',
  cwd TEXT,
  started_at INTEGER NOT NULL,
  ended_at INTEGER
);

CREATE TABLE IF NOT EXISTS observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  event TEXT NOT NULL,
  tool TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'claude_code',
  input_summary TEXT NOT NULL,
  compressed INTEGER NOT NULL DEFAULT 1,
  intensity TEXT DEFAULT 'lite',
  extracted_at INTEGER,
  insight_type TEXT,
  evidence TEXT,
  ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_observations_project ON observations(project_id, extracted_at, ts);
CREATE INDEX IF NOT EXISTS idx_observations_ts ON observations(ts);

CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
  input_summary,
  content='observations',
  content_rowid='id',
  tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN
  INSERT INTO observations_fts(rowid, input_summary) VALUES (new.id, new.input_summary);
END;
CREATE TRIGGER IF NOT EXISTS obs_ad AFTER DELETE ON observations BEGIN
  INSERT INTO observations_fts(observations_fts, rowid, input_summary)
  VALUES('delete', old.id, old.input_summary);
END;
DROP TRIGGER IF EXISTS obs_au;
CREATE TRIGGER obs_au AFTER UPDATE ON observations
WHEN old.input_summary != new.input_summary BEGIN
  INSERT INTO observations_fts(observations_fts, rowid, input_summary)
  VALUES('delete', old.id, old.input_summary);
  INSERT INTO observations_fts(rowid, input_summary) VALUES (new.id, new.input_summary);
END;

INSERT OR IGNORE INTO schema_version(version) VALUES (1);
INSERT OR IGNORE INTO schema_version(version) VALUES (2);
"""

MIGRATION_V2 = """
DROP TRIGGER IF EXISTS obs_au;
CREATE TRIGGER obs_au AFTER UPDATE ON observations
WHEN old.input_summary != new.input_summary BEGIN
  INSERT INTO observations_fts(observations_fts, rowid, input_summary)
  VALUES('delete', old.id, old.input_summary);
  INSERT INTO observations_fts(rowid, input_summary) VALUES (new.id, new.input_summary);
END;
"""


def open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.executescript(SCHEMA_SQL)
    # apply migration v2 if needed
    version = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_version"
    ).fetchone()[0]
    if version < 2:
        conn.executescript(MIGRATION_V2)
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (2)")
        conn.commit()
    return conn


def project_already_in_db(conn: sqlite3.Connection, project_id: str) -> int:
    """Return the number of SQLite rows already present for this project."""
    return conn.execute(
        "SELECT COUNT(*) FROM observations WHERE project_id = ?",
        (project_id,),
    ).fetchone()[0]


def import_batch(
    conn: sqlite3.Connection,
    rows: list[tuple],
    sessions: dict[str, int],
) -> None:
    """Insert sessions and observation rows in one transaction."""
    with conn:
        for sid, started_at in sessions.items():
            conn.execute(
                "INSERT OR IGNORE INTO sessions(id, started_at) VALUES (?, ?)",
                (sid, started_at),
            )
        conn.executemany(
            """INSERT INTO observations
               (session_id, project_id, event, tool, source,
                input_summary, compressed, intensity,
                insight_type, evidence, extracted_at, ts)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)""",
            rows,
        )


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------

def parse_jsonl(jsonl_path: Path) -> tuple[list[dict], list[str]]:
    """Read a JSONL file. Returns (valid_records, error_lines)."""
    records, errors = [], []
    with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                errors.append(f"  line {lineno}: {exc}")
    return records, errors


def build_rows(
    records: list[dict],
    *,
    mark_pending: bool,
) -> tuple[list[tuple], dict[str, int]]:
    """Convert JSONL records into (sqlite_rows, session_start_times)."""
    base_ts = int(time.time())
    sessions: dict[str, int] = {}
    rows: list[tuple] = []

    for index, rec in enumerate(records):
        # Resolve timestamp
        ts = None
        if rec.get("ts") is not None:
            try:
                ts = int(rec["ts"])
            except (TypeError, ValueError):
                pass
        if ts is None:
            ts = parse_ts(rec.get("timestamp"))
        if ts is None:
            ts = base_ts + index

        # Session ID — JSONL uses "session", SQLite uses "session_id"
        sid = rec.get("session_id") or rec.get("session") or "unknown"
        sessions[sid] = min(sessions.get(sid, ts), ts)

        extracted_at = None if mark_pending else ts

        rows.append((
            sid,
            rec.get("project_id", "unknown"),
            rec.get("event", "tool_start"),
            rec.get("tool") or "",
            rec.get("source") or "claude_code",
            rec.get("input_summary") or "",
            rec.get("intensity") or "lite",
            rec.get("insight_type"),
            rec.get("evidence"),
            extracted_at,
            ts,
        ))

    return rows, sessions


# ---------------------------------------------------------------------------
# Archive helper
# ---------------------------------------------------------------------------

def archive_jsonl(jsonl_path: Path) -> Path:
    """Rename observations.jsonl → observations.jsonl.migrated.<epoch>."""
    stamp = int(time.time())
    dest = jsonl_path.with_suffix(f".jsonl.migrated.{stamp}")
    jsonl_path.rename(dest)
    return dest


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()

    prism_home = resolve_prism_home(args.prism_home)
    if not prism_home.is_dir():
        print(f"ERROR: PRISM_HOME not found: {prism_home}", file=sys.stderr)
        return 1

    db_path = prism_home / "prism.db"
    jsonl_files = find_jsonl_files(prism_home)

    if not jsonl_files:
        print("No observations.jsonl files found — nothing to migrate.")
        return 0

    print(f"Prism home  : {prism_home}")
    print(f"Database    : {db_path}")
    print(f"Dry run     : {'yes' if args.dry_run else 'no'}")
    print(f"Mark pending: {'yes' if args.mark_pending else 'no (mark as extracted)'}")
    print(f"Archive JSONL: {'no' if args.no_archive else 'yes (rename after import)'}")
    print(f"Found {len(jsonl_files)} project(s) with observations.jsonl")
    print()

    if not args.dry_run:
        conn = open_db(db_path)
    else:
        conn = None  # type: ignore[assignment]

    total_imported = 0
    total_skipped = 0
    total_errors = 0

    for project_id, jsonl_path in jsonl_files:
        print(f"Project: {project_id}")
        print(f"  File : {jsonl_path}")

        # Check for existing data
        if conn is not None:
            existing = project_already_in_db(conn, project_id)
            if existing > 0:
                print(f"  SKIP : {existing} rows already in SQLite — skipping to avoid duplicates")
                print(f"         (delete them first if you want to re-import)")
                total_skipped += existing
                print()
                continue

        records, parse_errors = parse_jsonl(jsonl_path)
        if parse_errors:
            print(f"  WARN : {len(parse_errors)} unparseable line(s):")
            for e in parse_errors[:5]:
                print(f"    {e}")
            if len(parse_errors) > 5:
                print(f"    ... and {len(parse_errors) - 5} more")
            total_errors += len(parse_errors)

        if not records:
            print("  SKIP : file is empty or all lines unparseable")
            print()
            continue

        rows, sessions = build_rows(records, mark_pending=args.mark_pending)

        print(f"  Rows : {len(rows)} observations across {len(sessions)} session(s)")

        if args.dry_run:
            sample = records[0] if records else {}
            print(f"  Sample record: {json.dumps(sample, default=str)[:120]}")
            total_imported += len(rows)
            print("  (dry run — not written)")
        else:
            try:
                import_batch(conn, rows, sessions)
                total_imported += len(rows)
                print(f"  OK   : {len(rows)} rows imported")
                if not args.no_archive:
                    archived_path = archive_jsonl(jsonl_path)
                    print(f"  ARCH : {archived_path.name}")
            except Exception as exc:
                print(f"  ERROR: import failed: {exc}", file=sys.stderr)
                total_errors += 1

        print()

    if conn is not None:
        conn.close()

    print("─" * 50)
    print(f"Imported : {total_imported} rows")
    if total_skipped:
        print(f"Skipped  : {total_skipped} rows (already in SQLite)")
    if total_errors:
        print(f"Errors   : {total_errors}")
    if args.dry_run:
        print("(dry run — no changes written)")

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
