"""Tests for centralized auto-extraction trigger."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_request_auto_extraction_pending_blocks_duplicate():
    """Only one background extract is queued until pending is cleared."""
    import lib.config as config
    import lib.storage as storage
    from lib.storage import init_db, insert_observation
    from lib import trigger

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        config.PRISM_HOME = prism_home
        storage.DB_PATH = prism_home / "prism.db"
        project_id = "test123"
        db_path = storage.DB_PATH

        init_db(db_path)
        for i in range(15):
            insert_observation(
                session_id="setup",
                project_id=project_id,
                event="tool_start",
                tool="Edit",
                source="test",
                input_summary=f"obs {i}",
                db_path=db_path,
            )

        trigger.PRISM_HOME = prism_home
        with patch.object(trigger, "_find_prism_cli", return_value=str(prism_home / "prism")):
            with patch.object(trigger.subprocess, "Popen"):
                assert trigger.request_auto_extraction(project_id, obs_count=15) is True
                assert trigger.request_auto_extraction(project_id, obs_count=16) is False

                trigger.clear_extract_pending(project_id)
                assert trigger.request_auto_extraction(project_id, obs_count=16) is True


def test_clear_pending_on_extraction_finally():
    """run_extraction finally clears the per-project pending flag."""
    import lib.config as config
    import lib.storage as storage
    from lib.storage import init_db
    from lib import trigger
    from lib.extract import run_extraction

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        config.PRISM_HOME = prism_home
        storage.DB_PATH = prism_home / "prism.db"
        project_id = "test123"
        init_db(storage.DB_PATH)

        trigger.PRISM_HOME = prism_home
        trigger._try_acquire_pending(project_id)
        pending = trigger._pending_path(project_id)
        assert pending.exists()

        with patch("lib.extract._phase1_extract", return_value=0):
            with patch("lib.extract.PRISM_HOME", prism_home):
                run_extraction(project_id)

        assert not pending.exists()


if __name__ == "__main__":
    test_request_auto_extraction_pending_blocks_duplicate()
    print("PASS: test_request_auto_extraction_pending_blocks_duplicate")
    test_clear_pending_on_extraction_finally()
    print("PASS: test_clear_pending_on_extraction_finally")
    print("\nAll trigger tests passed!")
