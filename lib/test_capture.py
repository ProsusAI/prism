"""Tests for capture.py observation processing."""
import json
import os
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_basic_observation():
    """Pre-phase hook produces tool_start event."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        (prism_home / "projects" / "test123").mkdir(parents=True)
        obs_path = prism_home / "projects" / "test123" / "observations.jsonl"

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.py"},
            "session_id": "sess-001",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        assert obs_path.exists(), "observations.jsonl should be created"
        line = json.loads(obs_path.read_text().strip())
        assert line["tool"] == "Edit"
        assert line["event"] == "tool_start"
        assert line["session"] == "sess-001"
        assert line["project_id"] == "test123"
        assert "timestamp" in line
        assert line["source"] == "claude_code"


def test_post_phase():
    """Post-phase hook produces tool_end event."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        (prism_home / "projects" / "test123").mkdir(parents=True)
        obs_path = prism_home / "projects" / "test123" / "observations.jsonl"

        stdin_data = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "session_id": "sess-002",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "post"]):
                    capture.main()

        line = json.loads(obs_path.read_text().strip())
        assert line["event"] == "tool_end"


def test_secret_scrubbing():
    """Secrets are redacted in observations."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        (prism_home / "projects" / "test123").mkdir(parents=True)
        obs_path = prism_home / "projects" / "test123" / "observations.jsonl"

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"content": "api_key: sk-abc12345678901234567890123456"},
            "session_id": "sess-003",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        line = json.loads(obs_path.read_text().strip())
        assert "sk-abc" not in line["input_summary"], "Secret should be scrubbed"
        assert "REDACTED" in line["input_summary"]


def test_empty_stdin():
    """Empty stdin produces no output and no error."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        obs_path = prism_home / "projects" / "test123" / "observations.jsonl"

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO("")):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        assert not obs_path.exists(), "No file should be created for empty stdin"


def test_invalid_json():
    """Invalid JSON produces no output and no error."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        obs_path = prism_home / "projects" / "test123" / "observations.jsonl"

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO("not json {")):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        assert not obs_path.exists()


def test_truncation():
    """Long input summaries are truncated to ~500 chars."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        (prism_home / "projects" / "test123").mkdir(parents=True)
        obs_path = prism_home / "projects" / "test123" / "observations.jsonl"

        long_input = "x" * 2000
        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": long_input,
            "session_id": "sess-004",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        line = json.loads(obs_path.read_text().strip())
        assert len(line["input_summary"]) <= 520  # 500 + truncation indicator


def test_all_fields_present():
    """All 7 required fields are present in the observation."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        (prism_home / "projects" / "test123").mkdir(parents=True)
        obs_path = prism_home / "projects" / "test123" / "observations.jsonl"

        stdin_data = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.py"},
            "session_id": "sess-005",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    capture.main()

        line = json.loads(obs_path.read_text().strip())
        required_fields = ["timestamp", "event", "tool", "input_summary", "session", "project_id", "source"]
        for field in required_fields:
            assert field in line, f"Missing required field: {field}"


def test_extraction_trigger():
    """Extraction is triggered when observation count >= extract_threshold."""
    from lib import capture

    with tempfile.TemporaryDirectory() as tmpdir:
        prism_home = Path(tmpdir)
        project_dir = prism_home / "projects" / "test123"
        project_dir.mkdir(parents=True)
        obs_path = project_dir / "observations.jsonl"

        # Pre-populate with 14 observations (one more will hit threshold of 15)
        with open(obs_path, "w") as f:
            for i in range(14):
                f.write(json.dumps({"obs": i}) + "\n")

        stdin_data = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.py"},
            "session_id": "sess-006",
        })

        with patch.dict(os.environ, {"PRISM_HOME": str(prism_home), "PRISM_PROJECT_ID": "test123"}):
            with patch("sys.stdin", StringIO(stdin_data)):
                with patch("sys.argv", ["capture.py", "pre"]):
                    with patch.object(capture, "_spawn_background") as mock_spawn:
                        capture.main()

        # After adding 15th observation, trigger should fire
        mock_spawn.assert_called_once()
        call_args = mock_spawn.call_args
        assert "extract" in call_args[0][1], "Should spawn extraction"


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
    test_extraction_trigger()
    print("PASS: test_extraction_trigger")
    print("\nAll 8 capture tests passed!")
