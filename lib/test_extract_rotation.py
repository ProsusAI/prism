"""Tests for extraction batch rotation (rotation race fix)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_mark_extracted_scoped_to_batch_ids():
    """Only observation IDs in the batch are marked; newer rows stay active."""
    import lib.storage as storage
    from lib.storage import init_db, insert_observation, mark_extracted, count_active

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "prism.db"
        storage.DB_PATH = db_path
        init_db(db_path)

        batch_ids = []
        for i in range(3):
            row_id, _, _ = insert_observation(
                session_id="s1",
                project_id="p1",
                event="tool_start",
                tool="Edit",
                source="test",
                input_summary=f"obs {i}",
                db_path=db_path,
            )
            batch_ids.append(row_id)

        # Simulate observation captured mid-extraction (not in batch)
        late_id, _, _ = insert_observation(
            session_id="s1",
            project_id="p1",
            event="tool_start",
            tool="Edit",
            source="test",
            input_summary="late obs",
            db_path=db_path,
        )

        marked = mark_extracted("p1", observation_ids=batch_ids, db_path=db_path)
        assert marked == 3
        assert count_active("p1", db_path=db_path) == 1

        import sqlite3
        conn = sqlite3.connect(str(db_path))
        late_row = conn.execute(
            "SELECT extracted_at FROM observations WHERE id = ?", (late_id,)
        ).fetchone()
        conn.close()
        assert late_row[0] is None, "late observation must remain unextracted"


def test_batch_ids_sidecar_roundtrip():
    from lib.extract import _save_batch_ids, _load_batch_ids, _clear_batch_ids
    import lib.config as config

    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        config.PRISM_HOME = home
        project_id = "proj-rot"
        (home / "projects" / project_id).mkdir(parents=True)

        _save_batch_ids(project_id, [1, 2, 3])
        assert _load_batch_ids(project_id) == [1, 2, 3]
        _clear_batch_ids(project_id)
        assert _load_batch_ids(project_id) is None


if __name__ == "__main__":
    test_mark_extracted_scoped_to_batch_ids()
    print("PASS: test_mark_extracted_scoped_to_batch_ids")
    test_batch_ids_sidecar_roundtrip()
    print("PASS: test_batch_ids_sidecar_roundtrip")
    print("\nAll extract rotation tests passed!")
