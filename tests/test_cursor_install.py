# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for Cursor hook installation/uninstallation (lib/commands.py).

Cursor reads hooks ONLY from .cursor/hooks.json with a {"version": 1, "hooks": {...}}
shape — never from settings.json. These tests pin that contract and the migration
that strips dead prism entries older installs left in settings.json.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib import commands


class _CursorInstallBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.project_root = self.tmp / "project"
        self.home = self.tmp / "home"
        self.project_root.mkdir()
        self.home.mkdir()
        self._patches = [
            mock.patch.object(commands, "get_project_root", return_value=self.project_root),
            mock.patch.object(Path, "home", return_value=self.home),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    @property
    def hooks_path(self) -> Path:
        return self.project_root / ".cursor" / "hooks.json"

    @property
    def settings_path(self) -> Path:
        return self.project_root / ".cursor" / "settings.json"

    @property
    def cursor_mcp_path(self) -> Path:
        return self.home / ".cursor" / "mcp.json"


class TestCursorHooksInstall(_CursorInstallBase):
    def test_writes_hooks_json_not_settings(self):
        commands._setup_cursor_hooks_and_mcp("pid123")

        self.assertTrue(self.hooks_path.exists())
        # Cursor must not get hooks written to settings.json.
        self.assertFalse(self.settings_path.exists())

        config = json.loads(self.hooks_path.read_text())
        self.assertEqual(config["version"], 1)
        pre = config["hooks"]["preToolUse"]
        self.assertEqual(len(pre), 1)
        cmd = pre[0]["command"]
        self.assertIn("capture_cursor.sh", cmd)
        self.assertIn("PRISM_PROJECT_ID=pid123", cmd)
        self.assertIn("PRISM_SOURCE=cursor", cmd)
        self.assertTrue(cmd.rstrip().endswith("pre"))

    def test_registers_cursor_mcp_server(self):
        commands._setup_cursor_hooks_and_mcp("pid123")
        data = json.loads(self.cursor_mcp_path.read_text())
        self.assertIn("prism", data["mcpServers"])
        self.assertEqual(data["mcpServers"]["prism"]["env"]["PRISM_PROJECT_ID"], "pid123")

    def test_idempotent_no_duplicate_entries(self):
        commands._setup_cursor_hooks_and_mcp("pid123")
        commands._setup_cursor_hooks_and_mcp("pid123")
        config = json.loads(self.hooks_path.read_text())
        self.assertEqual(len(config["hooks"]["preToolUse"]), 1)

    def test_preserves_user_hooks_json_entries(self):
        self.hooks_path.parent.mkdir(parents=True)
        self.hooks_path.write_text(json.dumps({
            "version": 1,
            "hooks": {"preToolUse": [{"command": "/usr/local/bin/my-own-hook"}]},
        }))
        commands._setup_cursor_hooks_and_mcp("pid123")
        config = json.loads(self.hooks_path.read_text())
        cmds = [e["command"] for e in config["hooks"]["preToolUse"]]
        self.assertIn("/usr/local/bin/my-own-hook", cmds)
        self.assertTrue(any("capture_cursor.sh" in c for c in cmds))

    def test_migrates_legacy_settings_json(self):
        # Simulate an old install that wrote prism hooks into settings.json,
        # plus an unrelated user hook that must be preserved.
        capture_script = str(commands.PRISM_HOME / "hooks" / "capture_cursor.sh")
        self.settings_path.parent.mkdir(parents=True)
        self.settings_path.write_text(json.dumps({
            "hooks": {
                "preToolUse": [
                    {"command": f"env PRISM_SOURCE=cursor {capture_script} pre"},
                    {"command": "/usr/local/bin/my-own-hook"},
                ]
            }
        }))

        commands._setup_cursor_hooks_and_mcp("pid123")

        settings = json.loads(self.settings_path.read_text())
        cmds = [e["command"] for e in settings["hooks"]["preToolUse"]]
        self.assertEqual(cmds, ["/usr/local/bin/my-own-hook"])  # prism entry stripped
        self.assertTrue(self.hooks_path.exists())  # real hook now in the right file

    def test_removes_settings_json_when_only_prism(self):
        capture_script = str(commands.PRISM_HOME / "hooks" / "capture_cursor.sh")
        self.settings_path.parent.mkdir(parents=True)
        self.settings_path.write_text(json.dumps({
            "hooks": {"preToolUse": [{"command": f"env PRISM_SOURCE=cursor {capture_script} pre"}]}
        }))
        commands._setup_cursor_hooks_and_mcp("pid123")
        self.assertFalse(self.settings_path.exists())


class TestCursorUninstall(_CursorInstallBase):
    def test_uninstall_removes_hook_and_mcp(self):
        commands._setup_cursor_hooks_and_mcp("pid123")
        self.assertTrue(self.hooks_path.exists())

        commands._uninstall_cursor_integration()

        # hooks.json had only the prism entry → removed entirely.
        self.assertFalse(self.hooks_path.exists())
        data = json.loads(self.cursor_mcp_path.read_text())
        self.assertNotIn("prism", data.get("mcpServers", {}))

    def test_uninstall_preserves_user_hook(self):
        self.hooks_path.parent.mkdir(parents=True)
        self.hooks_path.write_text(json.dumps({
            "version": 1,
            "hooks": {"preToolUse": [{"command": "/usr/local/bin/my-own-hook"}]},
        }))
        commands._setup_cursor_hooks_and_mcp("pid123")
        commands._uninstall_cursor_integration()

        self.assertTrue(self.hooks_path.exists())
        config = json.loads(self.hooks_path.read_text())
        cmds = [e["command"] for e in config["hooks"]["preToolUse"]]
        self.assertEqual(cmds, ["/usr/local/bin/my-own-hook"])


if __name__ == "__main__":
    unittest.main()
