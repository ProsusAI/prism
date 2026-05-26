"""FTS5 search over Prism observations (primary prism.db only).

Replaces the old session-index.db / sessions_fts approach. Queries the
observations_fts virtual table that is maintained automatically by triggers
on the observations table in prism.db.
"""

from .storage import search_observations_fts


def search_sessions(
    query: str,
    project_id: str | None = None,
    limit: int = 10,
    ts_from: int | None = None,
) -> list[dict]:
    """FTS5 search across captured observations.

    Returns up to `limit` results as [{id, session_id, ts, snippet}],
    ordered by FTS5 relevance rank. Pass ts_from (Unix timestamp) to restrict
    to observations on or after that time.
    """
    return search_observations_fts(query, project_id=project_id, limit=limit, ts_from=ts_from)
