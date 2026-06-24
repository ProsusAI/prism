# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""SQLite storage layer for Prism observations."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import PRISM_HOME
from .schema import SCHEMA_SQL, MIGRATION_V2, MIGRATION_V3

DB_PATH = PRISM_HOME / "prism.db"

# Events that do not count toward review/extract auto-triggers (still extracted).
_TRIGGER_EXCLUDED_EVENTS = ("session_insight",)

# Retrieval analytics: which `retrievals.tool` values represent active pulls by
# Claude/Cursor (vs sync_push, which is context injection, not active retrieval).
_MCP_RETRIEVAL_TOOLS = ("prism_search", "prism_get", "prism_relevant")
# Searches that can "miss" -- used for hit-rate. prism_get is a direct fetch, excluded.
_HIT_RATE_TOOLS = ("prism_search", "prism_relevant")
SYNC_PUSH_TOOL = "sync_push"


def parse_observation_timestamp(raw: str) -> int | None:
    """Parse ISO-8601 or Unix string timestamps from session imports."""
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


def observation_ts(obs: dict, *, fallback: int, index: int = 0) -> int:
    """Resolve Unix ``ts`` for an observation dict (import or live capture)."""
    if obs.get("ts") is not None:
        return int(obs["ts"])
    parsed = parse_observation_timestamp(obs.get("timestamp", ""))
    if parsed is not None:
        return parsed
    return fallback + index


def _active_count_sql(*, for_triggers: bool) -> tuple[str, tuple]:
    """WHERE fragment and trailing params for active-observation counts."""
    if for_triggers:
        placeholders = ",".join("?" * len(_TRIGGER_EXCLUDED_EVENTS))
        extra = f" AND event NOT IN ({placeholders})"
        return (
            "project_id = ? AND extracted_at IS NULL" + extra,
            _TRIGGER_EXCLUDED_EVENTS,
        )
    return ("project_id = ? AND extracted_at IS NULL", ())


def _migrate_db(conn: sqlite3.Connection) -> None:
    """Apply any pending schema migrations. Called once per connection."""
    try:
        version = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return  # fresh DB; schema_version does not exist yet — init_db will create it
    if version < 2:
        conn.executescript(MIGRATION_V2)
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (2)")
        conn.commit()
    if version < 3:
        conn.executescript(MIGRATION_V3)
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (3)")
        conn.commit()


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    _migrate_db(conn)
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Create schema if not present. Safe to call multiple times."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(path)
    try:
        conn.executescript(SCHEMA_SQL)
    finally:
        conn.close()


def insert_observation(
    session_id: str,
    project_id: str,
    event: str,
    tool: str,
    source: str,
    input_summary: str,
    insight_type: str | None = None,
    evidence: str | None = None,
    db_path: Path | None = None,
    intensity: str = "lite",
) -> tuple[int, int, int]:
    """Insert one observation (input_summary should already be scrubbed/compressed).

    Returns (row_id, backlog_count, trigger_count) from a single transaction.
    ``trigger_count`` excludes ``session_insight`` rows (for hook thresholds).
    """
    path = db_path or DB_PATH
    conn = _connect(path)
    try:
        ts = int(time.time())
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions(id, started_at) VALUES (?, ?)",
                (session_id or "unknown", ts),
            )
            cur = conn.execute(
                """INSERT INTO observations
                   (session_id, project_id, event, tool, source,
                    input_summary, compressed, intensity,
                    insight_type, evidence, ts)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
                (
                    session_id or "unknown",
                    project_id,
                    event,
                    tool,
                    source,
                    input_summary,
                    intensity,
                    insight_type,
                    evidence,
                    ts,
                ),
            )
            row_id = cur.lastrowid
            backlog_count = _count_active_conn(conn, project_id, for_triggers=False)
            trigger_count = _count_active_conn(conn, project_id, for_triggers=True)
        return row_id, backlog_count, trigger_count
    finally:
        conn.close()


def _count_active_conn(
    conn: sqlite3.Connection, project_id: str, *, for_triggers: bool,
) -> int:
    where_sql, extra_params = _active_count_sql(for_triggers=for_triggers)
    return conn.execute(
        f"SELECT COUNT(*) FROM observations WHERE {where_sql}",
        (project_id, *extra_params),
    ).fetchone()[0]


def insert_observations_batch(
    observations: list[dict],
    db_path: Path | None = None,
) -> int:
    """Insert multiple observations in a single transaction. Returns inserted count.

    Each dict must have: session_id, project_id, event, tool, source, input_summary.
    Optional: ts, timestamp (ISO-8601), intensity, insight_type, evidence.
    """
    if not observations:
        return 0
    path = db_path or DB_PATH
    conn = _connect(path)
    try:
        base_ts = int(time.time())
        session_starts: dict[str, int] = {}
        rows: list[tuple] = []
        for index, obs in enumerate(observations):
            row_ts = observation_ts(obs, fallback=base_ts, index=index)
            sid = obs.get("session_id") or obs.get("session") or "unknown"
            session_starts[sid] = min(session_starts.get(sid, row_ts), row_ts)
            rows.append(
                (
                    sid,
                    obs["project_id"],
                    obs["event"],
                    obs.get("tool", ""),
                    obs.get("source", "unknown"),
                    obs.get("input_summary", ""),
                    obs.get("intensity", "lite"),
                    obs.get("insight_type"),
                    obs.get("evidence"),
                    row_ts,
                )
            )
        with conn:
            for sid, started_at in session_starts.items():
                conn.execute(
                    "INSERT OR IGNORE INTO sessions(id, started_at) VALUES (?, ?)",
                    (sid, started_at),
                )
            conn.executemany(
                """INSERT INTO observations
                   (session_id, project_id, event, tool, source,
                    input_summary, compressed, intensity,
                    insight_type, evidence, ts)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
                rows,
            )
        return len(observations)
    finally:
        conn.close()


def count_active(
    project_id: str,
    db_path: Path | None = None,
    *,
    for_triggers: bool = False,
) -> int:
    """Count unextracted observations (optionally excluding insight rows)."""
    path = db_path or DB_PATH
    if not path.exists():
        return 0
    conn = _connect(path)
    try:
        return _count_active_conn(conn, project_id, for_triggers=for_triggers)
    finally:
        conn.close()


def count_active_insights(project_id: str, db_path: Path | None = None) -> int:
    """Unextracted session_insight rows for a project."""
    path = db_path or DB_PATH
    if not path.exists():
        return 0
    conn = _connect(path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM observations"
            " WHERE project_id = ? AND extracted_at IS NULL"
            " AND event = 'session_insight'",
            (project_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def get_active(
    project_id: str,
    last_n: int | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """Return active (unextracted) observations, oldest first.

    With last_n, returns the N most recent unextracted observations.
    """
    path = db_path or DB_PATH
    if not path.exists():
        return []
    conn = _connect(path)
    try:
        if last_n:
            rows = conn.execute(
                "SELECT * FROM observations"
                " WHERE project_id = ? AND extracted_at IS NULL"
                " ORDER BY ts DESC LIMIT ?",
                (project_id, last_n),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]
        rows = conn.execute(
            "SELECT * FROM observations"
            " WHERE project_id = ? AND extracted_at IS NULL"
            " ORDER BY ts",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_extracted(
    project_id: str,
    observation_ids: list[int] | None = None,
    db_path: Path | None = None,
) -> int:
    """Stamp extracted_at on observations for this extraction batch.

    When ``observation_ids`` is provided, only those rows (still active) are
    marked — observations captured mid-extraction stay pending. When omitted,
    marks every active row for the project (legacy callers).
    """
    path = db_path or DB_PATH
    conn = _connect(path)
    try:
        now = int(time.time())
        with conn:
            if observation_ids is not None:
                if not observation_ids:
                    marked = 0
                else:
                    placeholders = ",".join("?" * len(observation_ids))
                    cur = conn.execute(
                        f"UPDATE observations SET extracted_at = ?"
                        f" WHERE project_id = ? AND extracted_at IS NULL"
                        f" AND id IN ({placeholders})",
                        (now, project_id, *observation_ids),
                    )
                    marked = cur.rowcount
            else:
                cur = conn.execute(
                    "UPDATE observations SET extracted_at = ?"
                    " WHERE project_id = ? AND extracted_at IS NULL",
                    (now, project_id),
                )
                marked = cur.rowcount
        return marked
    finally:
        conn.close()


def delete_observations_for_project(
    project_id: str, db_path: Path | None = None,
) -> int:
    """Delete all observations for a project (FTS rows removed via triggers)."""
    path = db_path or DB_PATH
    if not path.exists():
        return 0
    conn = _connect(path)
    try:
        with conn:
            cur = conn.execute(
                "DELETE FROM observations WHERE project_id = ?",
                (project_id,),
            )
        return cur.rowcount
    finally:
        conn.close()


def delete_orphan_sessions(db_path: Path | None = None) -> int:
    """Delete session rows that have no remaining observations.

    Sessions aren't project-scoped (only id + started_at; see schema), so a single
    session can own observations across multiple projects. Deleting sessions by project
    would cascade-delete other projects' observations. This reaps only sessions whose
    observation children are all gone -- safe to call after a project delete.
    """
    path = db_path or DB_PATH
    if not path.exists():
        return 0
    conn = _connect(path)
    try:
        with conn:
            cur = conn.execute(
                "DELETE FROM sessions WHERE id NOT IN "
                "(SELECT DISTINCT session_id FROM observations)"
            )
        return cur.rowcount
    finally:
        conn.close()


def delete_by_session_ids(session_ids: list[str], db_path: Path | None = None) -> int:
    """Delete all observations for the given session IDs. Returns deleted count."""
    if not session_ids:
        return 0
    path = db_path or DB_PATH
    if not path.exists():
        return 0
    conn = _connect(path)
    try:
        placeholders = ",".join("?" * len(session_ids))
        with conn:
            cur = conn.execute(
                f"DELETE FROM observations WHERE session_id IN ({placeholders})",
                session_ids,
            )
        return cur.rowcount
    finally:
        conn.close()


def get_recent(
    project_id: str,
    last_n: int = 20,
    db_path: Path | None = None,
) -> list[dict]:
    """Return up to last_n most-recent observations for a project, newest first."""
    path = db_path or DB_PATH
    if not path.exists():
        return []
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM observations WHERE project_id = ? ORDER BY ts DESC LIMIT ?",
            (project_id, last_n),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_insights(
    project_id: str,
    last_n: int = 20,
    db_path: Path | None = None,
) -> list[dict]:
    """Return up to last_n session_insight observations for a project, oldest first."""
    path = db_path or DB_PATH
    if not path.exists():
        return []
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM observations"
            " WHERE project_id = ? AND event = 'session_insight'"
            " ORDER BY ts DESC LIMIT ?",
            (project_id, last_n),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def get_session_observations(
    session_id: str,
    limit: int = 50,
    db_path: Path | None = None,
) -> list[dict]:
    """Return up to `limit` most-recent observations for a session, oldest-first."""
    path = db_path or DB_PATH
    if not path.exists():
        return []
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM observations"
            " WHERE session_id = ? ORDER BY ts DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def search_observations_fts(
    query: str,
    project_id: str | None = None,
    limit: int = 10,
    ts_from: int | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """FTS5 search over observations. Returns [{id, session_id, ts, snippet}]."""
    import sqlite3 as _sqlite3
    path = db_path or DB_PATH
    if not path.exists():
        return []
    conn = _connect(path)
    try:
        clauses = []
        params: list = [query]
        if project_id:
            clauses.append("AND o.project_id = ?")
            params.append(project_id)
        if ts_from is not None:
            clauses.append("AND o.ts >= ?")
            params.append(ts_from)
        params.append(limit)
        extra = "\n                  ".join(clauses)
        rows = conn.execute(
            f"""SELECT o.id, o.session_id, o.ts,
                       snippet(observations_fts, 0, '', '', '...', 20) AS snippet
                FROM observations_fts f
                JOIN observations o ON f.rowid = o.id
                WHERE observations_fts MATCH ?
                  {extra}
                ORDER BY rank
                LIMIT ?""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    except _sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def insert_retrieval(
    project_id: str,
    source: str,
    tool: str,
    query: str,
    engram_ids: list[str],
    db_path: Path | None = None,
) -> int:
    """Log one retrieval event (MCP pull or sync push) plus its returned engrams.

    `query` must already be scrubbed by the caller. Writes the event row and one
    `retrieval_engrams` row per returned/surfaced engram in a single transaction.
    Returns the new `retrievals.id`. Counts are derived from these events at read
    time -- this never touches the engram index or frontmatter.
    """
    path = db_path or DB_PATH
    conn = _connect(path)
    try:
        ts = int(time.time())
        with conn:
            cur = conn.execute(
                """INSERT INTO retrievals
                   (project_id, source, tool, query, result_count, ts)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project_id, source, tool, query or "", len(engram_ids), ts),
            )
            rid = cur.lastrowid
            if engram_ids:
                conn.executemany(
                    "INSERT INTO retrieval_engrams(retrieval_id, engram_id, ts)"
                    " VALUES (?, ?, ?)",
                    [(rid, eid, ts) for eid in engram_ids],
                )
        return rid
    finally:
        conn.close()


def retrieval_stats(
    project_id: str,
    window_seconds: int,
    db_path: Path | None = None,
) -> dict:
    """Aggregate retrieval metrics for a project over the trailing `window_seconds`.

    Returns MCP-retrieval counts for the window and the prior equal-length window
    (for trend), the per-source split, search hit-rate components, and totals for
    engrams surfaced via sync push. All values are derived from logged events.
    """
    empty = {
        "window_retrievals": 0, "prior_retrievals": 0, "by_source": {},
        "hit_searches": 0, "total_searches": 0,
        "surfaced_pushes": 0, "surfaced_engrams": 0,
    }
    path = db_path or DB_PATH
    if not path.exists():
        return empty
    now = int(time.time())
    since = now - window_seconds
    prior_since = since - window_seconds
    mcp_ph = ",".join("?" * len(_MCP_RETRIEVAL_TOOLS))
    hit_ph = ",".join("?" * len(_HIT_RATE_TOOLS))
    conn = _connect(path)
    try:
        def _count(where: str, params: tuple) -> int:
            return conn.execute(
                f"SELECT COUNT(*) FROM retrievals WHERE {where}", params
            ).fetchone()[0]

        by_source = {
            r["source"]: r["n"]
            for r in conn.execute(
                f"""SELECT source, COUNT(*) AS n FROM retrievals
                    WHERE project_id = ? AND tool IN ({mcp_ph}) AND ts >= ?
                    GROUP BY source""",
                (project_id, *_MCP_RETRIEVAL_TOOLS, since),
            ).fetchall()
        }
        surfaced_engrams = conn.execute(
            """SELECT COUNT(*) FROM retrieval_engrams re
               JOIN retrievals r ON re.retrieval_id = r.id
               WHERE r.project_id = ? AND r.tool = ? AND re.ts >= ?""",
            (project_id, SYNC_PUSH_TOOL, since),
        ).fetchone()[0]
        return {
            "window_retrievals": _count(
                f"project_id = ? AND tool IN ({mcp_ph}) AND ts >= ?",
                (project_id, *_MCP_RETRIEVAL_TOOLS, since),
            ),
            "prior_retrievals": _count(
                f"project_id = ? AND tool IN ({mcp_ph}) AND ts >= ? AND ts < ?",
                (project_id, *_MCP_RETRIEVAL_TOOLS, prior_since, since),
            ),
            "by_source": by_source,
            "hit_searches": _count(
                f"project_id = ? AND tool IN ({hit_ph}) AND ts >= ? AND result_count > 0",
                (project_id, *_HIT_RATE_TOOLS, since),
            ),
            "total_searches": _count(
                f"project_id = ? AND tool IN ({hit_ph}) AND ts >= ?",
                (project_id, *_HIT_RATE_TOOLS, since),
            ),
            "surfaced_pushes": _count(
                "project_id = ? AND tool = ? AND ts >= ?",
                (project_id, SYNC_PUSH_TOOL, since),
            ),
            "surfaced_engrams": surfaced_engrams,
        }
    finally:
        conn.close()


def top_engrams(
    project_id: str,
    since_ts: int,
    limit: int = 10,
    db_path: Path | None = None,
) -> list[dict]:
    """Most-retrieved engrams via MCP since `since_ts`. Returns [{id, count, last_ts}]."""
    path = db_path or DB_PATH
    if not path.exists():
        return []
    mcp_ph = ",".join("?" * len(_MCP_RETRIEVAL_TOOLS))
    conn = _connect(path)
    try:
        rows = conn.execute(
            f"""SELECT re.engram_id AS id, COUNT(*) AS count, MAX(re.ts) AS last_ts
                FROM retrieval_engrams re
                JOIN retrievals r ON re.retrieval_id = r.id
                WHERE r.project_id = ? AND r.tool IN ({mcp_ph}) AND re.ts >= ?
                GROUP BY re.engram_id
                ORDER BY count DESC, last_ts DESC
                LIMIT ?""",
            (project_id, *_MCP_RETRIEVAL_TOOLS, since_ts, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def retrieved_engram_ids(
    project_id: str,
    since_ts: int,
    db_path: Path | None = None,
) -> set[str]:
    """Set of engram IDs retrieved via MCP since `since_ts` (for dead-engram detection)."""
    path = db_path or DB_PATH
    if not path.exists():
        return set()
    mcp_ph = ",".join("?" * len(_MCP_RETRIEVAL_TOOLS))
    conn = _connect(path)
    try:
        rows = conn.execute(
            f"""SELECT DISTINCT re.engram_id
                FROM retrieval_engrams re
                JOIN retrievals r ON re.retrieval_id = r.id
                WHERE r.project_id = ? AND r.tool IN ({mcp_ph}) AND re.ts >= ?""",
            (project_id, *_MCP_RETRIEVAL_TOOLS, since_ts),
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


_MONTH_SECONDS = 30 * 24 * 60 * 60  # 2_592_000


def purge_old(
    project_id: str,
    retain_seconds: int = _MONTH_SECONDS,
    db_path: Path | None = None,
) -> int:
    """Delete extracted observations older than retain_seconds. Returns deleted count."""
    path = db_path or DB_PATH
    conn = _connect(path)
    try:
        cutoff = int(time.time()) - retain_seconds
        with conn:
            cur = conn.execute(
                "DELETE FROM observations"
                " WHERE project_id = ? AND extracted_at IS NOT NULL AND extracted_at < ?",
                (project_id, cutoff),
            )
        return cur.rowcount
    finally:
        conn.close()
