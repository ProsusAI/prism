# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for Cursor agent-transcript import (lib/sessions.py, lib/project.py)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Repo root on path so ``lib`` imports work when run as ``python3 -m unittest``.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.project import cursor_project_slug, lookup_cursor_project, register_cursor_project
from lib.sessions import (
    _analyze_cursor_transcript,
    _infer_cursor_cwd,
    _message_text,
    _unwrap_user_query,
    is_cursor_guidance,
)


class TestCursorProjectSlug(unittest.TestCase):
    def test_macos_documents_path(self):
        slug = cursor_project_slug("/Users/lara.baseggio/Documents/prism")
        self.assertEqual(slug, "Users-lara-baseggio-Documents-prism")


class TestInferCursorCwd(unittest.TestCase):
    """Cursor transcripts carry no cwd; the real workspace root is recovered
    from absolute paths embedded in tool inputs, using the folder slug as a
    checksum. Hyphens/dots in path components make the slug lossy, so the disk
    check disambiguates collisions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # A workspace whose name contains hyphens — the case that breaks
        # naive slug → path reconstruction.
        self.workspace = Path(self.tmp.name) / "Documents" / "green-ros-advisor-v2"
        self.workspace.mkdir(parents=True)
        self.folder_name = cursor_project_slug(str(self.workspace))
        self.transcript = Path(self.tmp.name) / "session.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, *lines: dict) -> None:
        self.transcript.write_text("\n".join(json.dumps(l) for l in lines) + "\n")

    def test_recovers_hyphenated_workspace_root(self):
        edited = str(self.workspace / "src" / "app.py")
        self._write({
            "role": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": edited}},
            ]},
        })
        self.assertEqual(_infer_cursor_cwd(self.transcript, self.folder_name), str(self.workspace))

    def test_prefers_existing_dir_over_slug_collision(self):
        # A non-existent path that slugifies identically must lose to the real dir.
        collision = "/Documents/green-ros-advisor-v2"  # different root, same-ish slug
        real = str(self.workspace / "lib" / "x.py")
        self._write({
            "role": "user",
            "message": {"content": [{"type": "text", "text": f"see {collision}/y and {real}"}]},
        })
        self.assertEqual(_infer_cursor_cwd(self.transcript, self.folder_name), str(self.workspace))

    def test_rejects_depth_one_slug_artifact(self):
        # The literal slug echoed as a /single-component path is not a root.
        artifact = "/" + self.folder_name
        self._write({
            "role": "user",
            "message": {"content": [{"type": "text", "text": f"folder is {artifact}"}]},
        })
        self.assertEqual(_infer_cursor_cwd(self.transcript, self.folder_name), "")

    def test_no_match_returns_empty(self):
        self._write({"role": "user", "message": {"content": [{"type": "text", "text": "hi"}]}})
        self.assertEqual(_infer_cursor_cwd(self.transcript, self.folder_name), "")


class TestCursorProjectLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prism_home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_register_and_lookup(self):
        with mock.patch("lib.project.PRISM_HOME", self.prism_home):
            slug = register_cursor_project("abc123", "/Users/me/Documents/my-app")
            self.assertEqual(slug, "Users-me-Documents-my-app")
            pid, root = lookup_cursor_project(slug)
            self.assertEqual(pid, "abc123")
            self.assertEqual(root, "/Users/me/Documents/my-app")

    def test_lookup_via_project_json(self):
        projects = self.prism_home / "projects" / "deadbeef0001"
        projects.mkdir(parents=True)
        (projects / "project.json").write_text(
            json.dumps(
                {
                    "project_id": "deadbeef0001",
                    "root": "/Users/me/Documents/my-app",
                    "name": "my-app",
                }
            )
            + "\n"
        )
        with mock.patch("lib.project.PRISM_HOME", self.prism_home):
            pid, root = lookup_cursor_project("Users-me-Documents-my-app")
            self.assertEqual(pid, "deadbeef0001")
            self.assertEqual(root, "/Users/me/Documents/my-app")


class TestMessageParsing(unittest.TestCase):
    def test_unwrap_user_query(self):
        raw = "<user_query>\nFix login\n</user_query>"
        self.assertEqual(_unwrap_user_query(raw), "Fix login")

    def test_message_text_cursor_shape(self):
        msg = {
            "role": "user",
            "message": {"content": [{"type": "text", "text": "hello"}]},
        }
        self.assertEqual(_message_text(msg), "hello")

    def test_is_cursor_guidance_long_correction(self):
        text = "x" * 400 + " don't use that approach"
        self.assertTrue(is_cursor_guidance(text))

    def test_is_cursor_guidance_long_neutral(self):
        text = "x" * 400 + " please summarize the plan"
        self.assertFalse(is_cursor_guidance(text))


class TestAnalyzeCursorTranscript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prism_home = Path(self.tmp.name) / "prism_home"
        self.prism_home.mkdir()
        self.db_path = self.prism_home / "prism.db"

    def _write_transcript(self, lines: list[dict]) -> Path:
        path = Path(self.tmp.name) / "sess-uuid.jsonl"
        with path.open("w") as fh:
            for line in lines:
                fh.write(json.dumps(line) + "\n")
        return path

    def test_import_user_turns_dry_run(self):
        path = self._write_transcript(
            [
                {
                    "role": "user",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "<user_query>\nRead plan.md\n</user_query>",
                            }
                        ]
                    },
                },
                {
                    "role": "assistant",
                    "message": {
                        "content": [{"type": "text", "text": "Reading plan.md..."}]
                    },
                },
                {
                    "role": "user",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "No, use pytest instead of unittest",
                            }
                        ]
                    },
                },
            ]
        )
        with mock.patch("lib.sessions.PRISM_HOME", self.prism_home):
            with mock.patch("lib.sessions.DB_PATH", self.db_path):
                stats = _analyze_cursor_transcript(
                    path, "proj001", dry_run=True
                )

        self.assertEqual(stats["observations_written"], 2)
        self.assertEqual(stats["user_queries"], 1)
        self.assertEqual(stats["corrections"], 1)

    def test_import_writes_sqlite(self):
        path = self._write_transcript(
            [
                {
                    "role": "user",
                    "message": {
                        "content": [{"type": "text", "text": "Add tests for parser"}]
                    },
                },
            ]
        )
        with mock.patch("lib.sessions.PRISM_HOME", self.prism_home):
            with mock.patch("lib.sessions.DB_PATH", self.db_path):
                with mock.patch("lib.config.PRISM_HOME", self.prism_home):
                    with mock.patch("lib.storage.DB_PATH", self.db_path):
                        stats = _analyze_cursor_transcript(
                            path, "proj001", dry_run=False
                        )

        self.assertEqual(stats["observations_written"], 1)
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT event, source, project_id, input_summary FROM observations"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "user_query")
        self.assertEqual(row[1], "cursor_transcript")
        self.assertEqual(row[2], "proj001")
        self.assertIn("Add tests", row[3])


if __name__ == "__main__":
    unittest.main()
