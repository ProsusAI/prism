"""SQLite FTS5 index for querying Claude Code session content.

Schema:
  sessions      -- metadata (session_id, project_id, date, cwd, file_path, file_size)
  sessions_fts  -- FTS5 virtual table (user_prompts, tools_used)

Cache logic:
  - Index is built incrementally: only sessions missing from DB or with a changed
    file_size are parsed and inserted.
  - prism analyze-sessions "query" --last N:
      first call  -> parse N sessions, build index, query
      same call   -> all N already cached (same file_size) -> query only (~5ms)
      --last N+5  -> parse 5 older sessions, add to index, query
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from .config import PRISM_HOME

SESSION_INDEX_PATH = PRISM_HOME / "session-index.db"

# JSONL message types that carry no useful searchable content
_SKIP_TYPES = frozenset({
    "permission-mode",
    "file-history-snapshot",
    "deferred_tools_delta",
    "skill_listing",
    "attachment",
    "summary",
})

# Prefixes that identify programmatic/injected content, not user-typed queries.
# Covers: Prism's reviewer/extractor/validator agents, Claude Code skill injection.
_INJECTED_PREFIXES = (
    "You are a session reviewer",
    "You are a knowledge",
    "Base directory for this skill:",
    "Read the validator instructions",
    "Read the constitution at",
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _open_db() -> sqlite3.Connection:
    SESSION_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SESSION_INDEX_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            project_id  TEXT NOT NULL,
            date        TEXT,
            cwd         TEXT,
            file_path   TEXT,
            file_size   INTEGER,
            indexed_at  TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
            session_id   UNINDEXED,
            user_prompts,
            tools_used
        );
    """)
    conn.commit()


def _get_indexed(conn: sqlite3.Connection, project_id: str) -> dict[str, int]:
    """Return {session_id: file_size} for all indexed sessions of this project."""
    rows = conn.execute(
        "SELECT session_id, file_size FROM sessions WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    return {row["session_id"]: row["file_size"] for row in rows}


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------

def _is_injected(text: str) -> bool:
    """Return True if text is a programmatic/injected prompt, not a user query."""
    return text.startswith("<") or any(text.startswith(p) for p in _INJECTED_PREFIXES)


def _parse_session(path: str) -> tuple[str, str]:
    """Extract (user_prompts_text, tools_used_text) from a session JSONL file.

    user_prompts: concatenated text of messages the user actually typed.
                  Skips tool_result arrays, IDE-injected system content, and
                  programmatic agent prompts (reviewer, extractor, skill injection).
    tools_used:   space-separated unique tool names the assistant invoked.
    """
    prompts: list[str] = []
    tools: list[str] = []
    seen_tools: set[str] = set()

    try:
        with open(path) as f:
            for line in f:
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")
                if not msg_type or msg_type in _SKIP_TYPES:
                    continue

                if msg_type == "user":
                    # Skip sub-agent/sidechain messages (extraction pipeline, tool agents)
                    if msg.get("isSidechain"):
                        continue
                    content = msg.get("message", {}).get("content", "")
                    if isinstance(content, str):
                        text = content.strip()
                        if text and len(text) > 3 and not _is_injected(text):
                            prompts.append(text[:500])
                    elif isinstance(content, list):
                        # Content array: Claude Code attaches IDE context as extra blocks.
                        # Extract text blocks that are NOT IDE-injected.
                        for block in content:
                            if not isinstance(block, dict) or block.get("type") != "text":
                                continue
                            text = block.get("text", "").strip()
                            if text and len(text) > 3 and not _is_injected(text):
                                prompts.append(text[:500])

                elif msg_type == "assistant":
                    content = msg.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                name = block.get("name", "")
                                if name and name not in seen_tools:
                                    tools.append(name)
                                    seen_tools.add(name)
    except OSError:
        pass

    return " ".join(prompts), " ".join(tools)


# ---------------------------------------------------------------------------
# Index write
# ---------------------------------------------------------------------------

def _index_session(conn: sqlite3.Connection, sess: dict) -> None:
    """Parse one session JSONL and upsert into the index."""
    user_prompts, tools_used = _parse_session(sess["path"])

    try:
        date = datetime.fromtimestamp(
            os.path.getmtime(sess["path"])
        ).strftime("%Y-%m-%d")
    except OSError:
        date = ""

    conn.execute(
        "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?)",
        (
            sess["session_id"],
            sess["project_id"],
            date,
            sess.get("cwd", ""),
            sess["path"],
            sess["size"],
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    # FTS5 has no UPDATE — must DELETE + INSERT
    conn.execute(
        "DELETE FROM sessions_fts WHERE session_id = ?",
        (sess["session_id"],),
    )
    conn.execute(
        "INSERT INTO sessions_fts(session_id, user_prompts, tools_used) VALUES (?,?,?)",
        (sess["session_id"], user_prompts, tools_used),
    )


# ---------------------------------------------------------------------------
# Snippet helper
# ---------------------------------------------------------------------------

def _make_snippet(text: str, query: str, width: int = 160) -> str:
    """Return a short excerpt centred on the first query-term hit."""
    lower = text.lower()
    best = len(text)
    for term in query.lower().split():
        pos = lower.find(term)
        if 0 <= pos < best:
            best = pos

    if best == len(text):
        return (text[:width] + "...") if len(text) > width else text

    start = max(0, best - 50)
    end = min(len(text), start + width)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end] + suffix


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_sessions(sessions: list[dict], query: str, project_id: str) -> list[dict]:
    """Update the index for missing/changed sessions, then run FTS5 query.

    Args:
        sessions:   Candidate sessions already filtered by --last N / project.
                    Each dict must have: session_id, project_id, path, size, cwd.
        query:      Plain keywords or FTS5 syntax (AND / OR / NOT / prefix*).
        project_id: Prism project ID — scopes both index writes and search results.

    Returns:
        Up to 10 result dicts {session_id, date, cwd, snippet, indexed_new},
        ordered by FTS5 relevance rank.
    """
    conn = _open_db()
    _ensure_schema(conn)

    # Determine which sessions need (re-)indexing (new or file grew)
    indexed = _get_indexed(conn, project_id)
    to_index = [
        s for s in sessions
        if s["session_id"] not in indexed
        or indexed[s["session_id"]] != s["size"]
    ]

    if to_index:
        for sess in to_index:
            _index_session(conn, sess)
        conn.commit()

    if not sessions:
        conn.close()
        return []

    # Scope FTS5 query to the exact candidate set (respects --last N)
    session_ids = [s["session_id"] for s in sessions]
    placeholders = ",".join("?" * len(session_ids))

    try:
        rows = conn.execute(
            f"""
            SELECT s.session_id, s.date, s.cwd, f.user_prompts
            FROM   sessions_fts f
            JOIN   sessions s ON f.session_id = s.session_id
            WHERE  sessions_fts MATCH ?
              AND  s.project_id = ?
              AND  s.session_id IN ({placeholders})
            ORDER  BY rank
            LIMIT  10
            """,
            [query, project_id] + session_ids,
        ).fetchall()
    except sqlite3.OperationalError:
        # FTS5 parse error (e.g. unbalanced quotes) — return empty rather than crash
        conn.close()
        return []

    results = [
        {
            "session_id": row["session_id"],
            "date": row["date"],
            "cwd": row["cwd"],
            "snippet": _make_snippet(row["user_prompts"] or "", query),
        }
        for row in rows
    ]
    conn.close()
    return results
