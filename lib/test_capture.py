"""Tests for capture.py observation processing."""
import json
import os
import shutil
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def _fetch_obs(db_path: Path) -> list[dict]:
    """Return all observations from the SQLite DB as dicts."""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM observations").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def test_basic_observation():
    """Pre-phase hook produces tool_start event."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.py"},
            "session_id": "sess-001",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        assert db_path.exists(), "prism.db should be created"
        rows = _fetch_obs(db_path)
        assert len(rows) == 1
        row = rows[0]
        assert row["tool"] == "Edit"
        assert row["event"] == "tool_start"
        assert row["session_id"] == "sess-001"
        assert row["project_id"] == "test123"
        assert row["ts"] is not None
        assert row["source"] == "claude_code"


def test_post_phase():
    """Post-phase hook produces tool_end event."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"

        stdin_data = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "session_id": "sess-002",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "post"]):
                    capture.main()

        rows = _fetch_obs(db_path)
        assert rows[0]["event"] == "tool_end"


def test_secret_scrubbing():
    """Secrets are redacted in observations."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"content": "api_key: sk-abc12345678901234567890123456"},
            "session_id": "sess-003",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        rows = _fetch_obs(db_path)
        summary = rows[0]["input_summary"]
        assert "sk-abc" not in summary, "Secret should be scrubbed"
        assert "REDACTED" in summary


def test_empty_stdin():
    """Empty stdin produces no output and no error."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO("")):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        assert not db_path.exists(), "DB should not be created for empty stdin"


def test_invalid_json():
    """Invalid JSON produces no output and no error."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO("not json {")):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        assert not db_path.exists()


def test_truncation():
    """Long input summaries are truncated to ~500 chars."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": "x" * 2000,
            "session_id": "sess-004",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        rows = _fetch_obs(db_path)
        assert len(rows[0]["input_summary"]) <= 520


def test_all_fields_present():
    """All required SQLite columns are populated."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"

        stdin_data = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.py"},
            "session_id": "sess-005",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        rows = _fetch_obs(db_path)
        row = rows[0]
        for field in ("ts", "event", "tool", "input_summary", "session_id", "project_id", "source"):
            assert row.get(field) is not None, f"Missing required field: {field}"


def test_insights_do_not_accelerate_extract_trigger():
    """session_insight rows count toward backlog but not extract/review triggers."""
    from lib import capture
    from lib.storage import init_db, insert_observation

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"
        init_db(db_path)

        for i in range(10):
            insert_observation(
                session_id="setup",
                project_id="test123",
                event="tool_start",
                tool="Edit",
                source="test",
                input_summary=f"obs {i}",
                db_path=db_path,
            )
        for i in range(5):
            insert_observation(
                session_id="setup",
                project_id="test123",
                event="session_insight",
                tool="reviewer",
                source="session_review",
                input_summary=f"insight {i}",
                db_path=db_path,
            )

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.py"},
            "session_id": "sess-insights",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    with patch("lib.trigger.request_auto_extraction", return_value=False) as mock_extract:
                        capture.main()

        assert mock_extract.call_args.kwargs.get("obs_count") == 11


def test_review_cooldown_sentinel():
    """Second auto-review within cooldown is suppressed."""
    from lib import capture

    with patch.object(capture, "_try_acquire_review_sentinel", side_effect=[True, False]) as mock_sentinel:
        with patch.object(capture, "_spawn_background") as mock_spawn:
            capture._check_triggers(Path("/tmp"), "proj", 5, "session-abc")
            capture._check_triggers(Path("/tmp"), "proj", 10, "session-abc")

    assert mock_sentinel.call_count == 2
    assert mock_spawn.call_count == 1


def test_extraction_trigger():
    """Extraction is triggered when observation count >= extract_threshold."""
    from lib import capture
    from lib.storage import init_db, insert_observation

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"

        # Pre-populate 14 observations so the 15th hits the threshold
        init_db(db_path)
        for i in range(14):
            insert_observation(
                session_id="setup",
                project_id="test123",
                event="tool_start",
                tool="Edit",
                source="test",
                input_summary=f"obs {i}",
                db_path=db_path,
            )

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.py"},
            "session_id": "sess-006",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    with patch("lib.trigger.request_auto_extraction", return_value=True) as mock_extract:
                        capture.main()

        mock_extract.assert_called_once()
        assert mock_extract.call_args.kwargs.get("obs_count") == 15


def test_delete_observations_for_project():
    """reset/uninstall clears SQLite rows for the project only."""
    import lib.storage as storage
    from lib.storage import init_db, insert_observation, delete_observations_for_project, count_active

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "prism.db"
        storage.DB_PATH = db_path
        init_db(db_path)
        for pid in ("keep", "drop"):
            insert_observation(
                session_id="s",
                project_id=pid,
                event="tool_start",
                tool="Edit",
                source="test",
                input_summary="x",
                db_path=db_path,
            )
        assert delete_observations_for_project("drop", db_path=db_path) == 1
        assert count_active("drop", db_path=db_path) == 0
        assert count_active("keep", db_path=db_path) == 1


def test_hook_script_mode_trigger_import():
    """capture.py run as a script (hook path) must load lib.trigger, not relative imports."""
    import importlib.util

    repo = Path(__file__).parent.parent
    spec = importlib.util.spec_from_file_location(
        "capture_as_hook",
        repo / "lib" / "capture.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    prism_home = Path(tempfile.mkdtemp())
    try:
        (prism_home / "lib").mkdir(parents=True)
        for py in (repo / "lib").glob("*.py"):
            if py.name.startswith("test_"):
                continue
            shutil.copy(py, prism_home / "lib" / py.name)
        for sub in ("lexicon",):
            src = repo / "lib" / sub
            if src.is_dir():
                shutil.copytree(src, prism_home / "lib" / sub)

        called = []

        def fake_request(project_id, *, obs_count=None, quiet=False):
            called.append((project_id, obs_count))
            return False

        import sys
        sys.path.insert(0, str(prism_home))
        import lib.trigger as trigger_mod
        trigger_mod.request_auto_extraction = fake_request

        mod._ensure_prism_on_path(prism_home)
        mod._check_triggers(prism_home, "hookproj", 15, "sess-hook")
        assert called == [("hookproj", 15)]
    finally:
        shutil.rmtree(prism_home, ignore_errors=True)


def test_capture_during_extraction_lock():
    """Observations are always written; extract spawn is skipped when lock is held."""
    from lib import capture
    from lib.storage import init_db, insert_observation

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        db_path = prism_home / "prism.db"
        (prism_home / ".extracting").write_text("")

        init_db(db_path)
        for i in range(14):
            insert_observation(
                session_id="setup",
                project_id="test123",
                event="tool_start",
                tool="Edit",
                source="test",
                input_summary=f"obs {i}",
                db_path=db_path,
            )

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.py"},
            "session_id": "sess-lock",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    with patch("lib.trigger.request_auto_extraction", return_value=False) as mock_extract:
                        capture.main()

        rows = _fetch_obs(db_path)
        assert len(rows) == 15, "Observation must be captured despite extraction lock"
        mock_extract.assert_called_once()


if __name__ == "__main__":
    test_basic_observation()
    print("PASS: test_basic_observation")
    test_post_phase()
    print("PASS: test_post_phase")
    test_secret_scrubbing()
    print("PASS: test_secret_scrubbing")
    test_empty_stdin()
    print("PASS: test_empty_stdin")
    test_invalid_json()
    print("PASS: test_invalid_json")
    test_truncation()
    print("PASS: test_truncation")
    test_all_fields_present()
    print("PASS: test_all_fields_present")
    test_insights_do_not_accelerate_extract_trigger()
    print("PASS: test_insights_do_not_accelerate_extract_trigger")
    test_review_cooldown_sentinel()
    print("PASS: test_review_cooldown_sentinel")
    test_extraction_trigger()
    print("PASS: test_extraction_trigger")
    test_delete_observations_for_project()
    print("PASS: test_delete_observations_for_project")
    test_hook_script_mode_trigger_import()
    print("PASS: test_hook_script_mode_trigger_import")
    test_capture_during_extraction_lock()
    print("PASS: test_capture_during_extraction_lock")
    print("\nAll capture tests passed!")
