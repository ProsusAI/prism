"""Tests for unified project ID detection."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_detect_project_id_reads_init_cache():
    from lib import project

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        cache = root / ".claude" / ".prism_project_id"
        cache.parent.mkdir(parents=True)
        cache.write_text("cached-id-12\n")

        with patch.object(project, "get_project_root", return_value=root):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("PRISM_PROJECT_ID", None)
                assert project.detect_project_id() == "cached-id-12"


def test_detect_project_id_env_overrides_cache():
    from lib import project

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        cache = root / ".claude" / ".prism_project_id"
        cache.parent.mkdir(parents=True)
        cache.write_text("from-cache\n")

        with patch.object(project, "get_project_root", return_value=root):
            with patch.dict(os.environ, {"PRISM_PROJECT_ID": "from-env"}):
                assert project.detect_project_id() == "from-env"


def test_capture_hook_command_includes_project_id():
    from lib.project import capture_hook_command

    cmd = capture_hook_command("/home/.prism/hooks/capture.sh", "pre", "abc123def456")
    assert cmd == "env PRISM_PROJECT_ID=abc123def456 /home/.prism/hooks/capture.sh pre"

    cursor_cmd = capture_hook_command(
        "/home/.prism/hooks/capture_cursor.sh",
        "pre",
        "abc123def456",
        extra_env={"PRISM_SOURCE": "cursor"},
    )
    assert "PRISM_PROJECT_ID=abc123def456" in cursor_cmd
    assert "PRISM_SOURCE=cursor" in cursor_cmd
    assert cursor_cmd.endswith("capture_cursor.sh pre")


if __name__ == "__main__":
    test_detect_project_id_reads_init_cache()
    print("PASS: test_detect_project_id_reads_init_cache")
    test_detect_project_id_env_overrides_cache()
    print("PASS: test_detect_project_id_env_overrides_cache")
    test_capture_hook_command_includes_project_id()
    print("PASS: test_capture_hook_command_includes_project_id")
    print("\nAll project tests passed!")
