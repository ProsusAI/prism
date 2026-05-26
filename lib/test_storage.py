"""Tests for observation storage timestamps and trigger counts."""
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_parse_observation_timestamp_iso_z():
    from lib.storage import parse_observation_timestamp

    ts = parse_observation_timestamp("2026-04-14T12:00:00Z")
    assert ts is not None
    assert datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().startswith("2026-04-14T12:00:00")


def test_parse_observation_timestamp_with_fraction():
    from lib.storage import parse_observation_timestamp

    ts = parse_observation_timestamp("2026-04-14T12:00:00.123Z")
    assert ts is not None


def test_parse_observation_timestamp_invalid():
    from lib.storage import parse_observation_timestamp

    assert parse_observation_timestamp("") is None
    assert parse_observation_timestamp("not-a-date") is None


def test_batch_insert_preserves_iso_timestamps():
    import lib.storage as storage
    import sqlite3
    from lib.storage import init_db, insert_observations_batch

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "prism.db"
        storage.DB_PATH = db_path
        init_db(db_path)

        t1 = "2026-01-10T10:00:00Z"
        t2 = "2026-01-10T10:05:00Z"
        insert_observations_batch([
            {
                "session": "sess-a",
                "project_id": "proj1",
                "event": "tool_start",
                "tool": "Read",
                "source": "session_import",
                "input_summary": "first",
                "timestamp": t1,
            },
            {
                "session": "sess-a",
                "project_id": "proj1",
                "event": "tool_end",
                "tool": "Read",
                "source": "session_import",
                "input_summary": "second",
                "timestamp": t2,
            },
        ], db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT ts FROM observations ORDER BY ts"
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0][0] < rows[1][0]
        assert rows[0][0] == int(
            datetime.fromisoformat("2026-01-10T10:00:00+00:00").timestamp()
        )


def test_count_active_for_triggers_excludes_insights():
    import lib.storage as storage
    from lib.storage import init_db, insert_observation, count_active

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "prism.db"
        storage.DB_PATH = db_path
        init_db(db_path)

        for i in range(4):
            insert_observation(
                session_id="s",
                project_id="p1",
                event="tool_start",
                tool="Edit",
                source="test",
                input_summary=f"tool {i}",
                db_path=db_path,
            )
        insert_observation(
            session_id="s",
            project_id="p1",
            event="session_insight",
            tool="reviewer",
            source="session_review",
            input_summary="insight",
            db_path=db_path,
        )

        assert count_active("p1", db_path=db_path) == 5
        assert count_active("p1", db_path=db_path, for_triggers=True) == 4


def test_insert_returns_separate_trigger_count():
    import lib.storage as storage
    from lib.storage import init_db, insert_observation

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "prism.db"
        storage.DB_PATH = db_path
        init_db(db_path)

        insert_observation(
            session_id="s",
            project_id="p1",
            event="tool_start",
            tool="Edit",
            source="test",
            input_summary="one",
            db_path=db_path,
        )
        _, backlog, trigger = insert_observation(
            session_id="s",
            project_id="p1",
            event="session_insight",
            tool="reviewer",
            source="session_review",
            input_summary="insight",
            db_path=db_path,
        )
        assert backlog == 2
        assert trigger == 1


if __name__ == "__main__":
    test_parse_observation_timestamp_iso_z()
    print("PASS: test_parse_observation_timestamp_iso_z")
    test_parse_observation_timestamp_with_fraction()
    print("PASS: test_parse_observation_timestamp_with_fraction")
    test_parse_observation_timestamp_invalid()
    print("PASS: test_parse_observation_timestamp_invalid")
    test_batch_insert_preserves_iso_timestamps()
    print("PASS: test_batch_insert_preserves_iso_timestamps")
    test_count_active_for_triggers_excludes_insights()
    print("PASS: test_count_active_for_triggers_excludes_insights")
    test_insert_returns_separate_trigger_count()
    print("PASS: test_insert_returns_separate_trigger_count")
    print("\nAll storage tests passed!")
