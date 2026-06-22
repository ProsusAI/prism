"""Tests for retrieval analytics (lib/storage.py retrieval funcs, schema v3)."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Repo root on path so ``lib`` imports work when run as ``python3 -m unittest``.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib import storage
from lib.storage import (
    init_db,
    insert_retrieval,
    retrieval_stats,
    retrieved_engram_ids,
    top_engrams,
)

WINDOW = 30 * 86400


class RetrievalTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "prism.db"
        init_db(self.db)

    def _backdate_last(self, seconds_ago: int) -> None:
        """Move the most-recent retrieval (and its engrams) back in time."""
        ts = int(time.time()) - seconds_ago
        conn = sqlite3.connect(str(self.db))
        try:
            rid = conn.execute("SELECT MAX(id) FROM retrievals").fetchone()[0]
            conn.execute("UPDATE retrievals SET ts = ? WHERE id = ?", (ts, rid))
            conn.execute("UPDATE retrieval_engrams SET ts = ? WHERE retrieval_id = ?", (ts, rid))
            conn.commit()
        finally:
            conn.close()


class TestInsertRetrieval(RetrievalTestBase):
    def test_writes_event_and_engram_rows(self):
        rid = insert_retrieval("proj", "claude_code", "prism_search", "flock",
                               ["a", "b"], db_path=self.db)
        conn = sqlite3.connect(str(self.db))
        try:
            row = conn.execute(
                "SELECT result_count, query, source FROM retrievals WHERE id = ?", (rid,)
            ).fetchone()
            n = conn.execute(
                "SELECT COUNT(*) FROM retrieval_engrams WHERE retrieval_id = ?", (rid,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(row[0], 2)        # result_count = len(ids)
        self.assertEqual(row[1], "flock")
        self.assertEqual(n, 2)             # one join row per engram

    def test_zero_results_logs_event_with_no_engrams(self):
        rid = insert_retrieval("proj", "cursor", "prism_search", "nope",
                               [], db_path=self.db)
        conn = sqlite3.connect(str(self.db))
        try:
            rc = conn.execute(
                "SELECT result_count FROM retrievals WHERE id = ?", (rid,)
            ).fetchone()[0]
            n = conn.execute(
                "SELECT COUNT(*) FROM retrieval_engrams WHERE retrieval_id = ?", (rid,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(rc, 0)
        self.assertEqual(n, 0)


class TestRetrievalStats(RetrievalTestBase):
    def _seed(self):
        insert_retrieval("proj", "claude_code", "prism_search", "q", ["a", "b"], db_path=self.db)
        insert_retrieval("proj", "cursor", "prism_search", "q", [], db_path=self.db)  # miss
        insert_retrieval("proj", "claude_code", "prism_get", "a", ["a"], db_path=self.db)
        insert_retrieval("proj", "sync", "sync_push", "", ["a", "b", "c"], db_path=self.db)

    def test_counts_and_hit_rate(self):
        self._seed()
        s = retrieval_stats("proj", WINDOW, db_path=self.db)
        self.assertEqual(s["window_retrievals"], 3)        # 2 searches + 1 get (MCP only)
        self.assertEqual(s["total_searches"], 2)           # get excluded from hit-rate
        self.assertEqual(s["hit_searches"], 1)             # only the search returning engrams
        self.assertEqual(s["by_source"], {"claude_code": 2, "cursor": 1})
        self.assertEqual(s["surfaced_pushes"], 1)
        self.assertEqual(s["surfaced_engrams"], 3)

    def test_prior_window_trend(self):
        insert_retrieval("proj", "claude_code", "prism_search", "old", ["a"], db_path=self.db)
        self._backdate_last(WINDOW + 86400)                # push into prior window
        insert_retrieval("proj", "claude_code", "prism_search", "new", ["b"], db_path=self.db)
        s = retrieval_stats("proj", WINDOW, db_path=self.db)
        self.assertEqual(s["window_retrievals"], 1)
        self.assertEqual(s["prior_retrievals"], 1)

    def test_empty_db(self):
        s = retrieval_stats("proj", WINDOW, db_path=self.db)
        self.assertEqual(s["window_retrievals"], 0)
        self.assertEqual(s["by_source"], {})


class TestTopAndDead(RetrievalTestBase):
    def test_top_engrams_excludes_sync_push(self):
        insert_retrieval("proj", "claude_code", "prism_search", "q", ["a", "b"], db_path=self.db)
        insert_retrieval("proj", "claude_code", "prism_get", "a", ["a"], db_path=self.db)
        insert_retrieval("proj", "sync", "sync_push", "", ["c"], db_path=self.db)
        since = int(time.time()) - WINDOW
        tops = top_engrams("proj", since, db_path=self.db)
        counts = {t["id"]: t["count"] for t in tops}
        self.assertEqual(counts.get("a"), 2)   # search + get
        self.assertEqual(counts.get("b"), 1)
        self.assertNotIn("c", counts)          # surfaced-only, never pulled
        self.assertEqual(tops[0]["id"], "a")   # ordered by count desc

    def test_retrieved_ids_distinct_and_mcp_only(self):
        insert_retrieval("proj", "claude_code", "prism_search", "q", ["a", "b"], db_path=self.db)
        insert_retrieval("proj", "sync", "sync_push", "", ["c"], db_path=self.db)
        since = int(time.time()) - WINDOW
        ids = retrieved_engram_ids("proj", since, db_path=self.db)
        self.assertEqual(ids, {"a", "b"})

    def test_window_excludes_old(self):
        insert_retrieval("proj", "claude_code", "prism_search", "q", ["a"], db_path=self.db)
        self._backdate_last(WINDOW + 86400)
        since = int(time.time()) - WINDOW
        self.assertEqual(retrieved_engram_ids("proj", since, db_path=self.db), set())


class TestMigration(unittest.TestCase):
    def test_v2_to_v3_creates_tables(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "old.db"
        # Simulate a pre-v3 DB: schema_version present at 2, no retrieval tables.
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO schema_version(version) VALUES (?)", [(1,), (2,)])
        conn.commit()
        conn.close()
        # Connecting through storage applies pending migrations.
        conn = storage._connect(db)
        try:
            names = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            ver = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        finally:
            conn.close()
        self.assertIn("retrievals", names)
        self.assertIn("retrieval_engrams", names)
        self.assertEqual(ver, 3)

    def test_init_db_idempotent(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "p.db"
        init_db(db)
        init_db(db)  # second call must not raise
        insert_retrieval("proj", "claude_code", "prism_search", "q", ["a"], db_path=db)
        self.assertEqual(
            retrieval_stats("proj", WINDOW, db_path=db)["window_retrievals"], 1
        )


if __name__ == "__main__":
    unittest.main()
