# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Tests for lib/agent_runner.py — IDE agent CLI backend resolution and argv."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib import agent_runner


class AgentRunnerTests(unittest.TestCase):
    def test_resolve_backend_defaults_to_claude(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch("lib.agent_runner.classify_pending_sources", return_value="empty"):
                self.assertEqual(agent_runner.resolve_backend("proj"), "claude")

    def test_resolve_backend_prism_source_cursor(self):
        with mock.patch.dict("os.environ", {"PRISM_SOURCE": "cursor"}, clear=True):
            self.assertEqual(agent_runner.resolve_backend("proj"), "cursor")

    def test_resolve_backend_prism_source_claude_code(self):
        with mock.patch.dict("os.environ", {"PRISM_SOURCE": "claude_code"}, clear=True):
            self.assertEqual(agent_runner.resolve_backend("proj"), "claude")

    def test_resolve_backend_override(self):
        self.assertEqual(
            agent_runner.resolve_backend("proj", override="claude"),
            "claude",
        )

    def test_resolve_backend_config_cursor(self):
        with mock.patch("lib.agent_runner.get_config", return_value={"agent_backend": "cursor"}):
            self.assertEqual(agent_runner.resolve_backend("proj"), "cursor")

    def test_classify_pending_unanimous_cursor(self):
        obs = [{"source": "cursor"}] * 3
        with mock.patch("lib.storage.get_active", return_value=obs):
            self.assertEqual(agent_runner.classify_pending_sources("p"), "cursor")

    def test_classify_pending_unanimous_claude(self):
        obs = [{"source": "claude_code"}] * 2
        with mock.patch("lib.storage.get_active", return_value=obs):
            self.assertEqual(agent_runner.classify_pending_sources("p"), "claude")

    def test_classify_pending_mixed(self):
        obs = [{"source": "cursor"}, {"source": "claude_code"}]
        with mock.patch("lib.storage.get_active", return_value=obs):
            self.assertEqual(agent_runner.classify_pending_sources("p"), "mixed")

    def test_resolve_backend_unanimous_cursor_without_env(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch("lib.agent_runner.get_config", return_value={"agent_backend": "auto"}):
                with mock.patch("lib.agent_runner.classify_pending_sources", return_value="cursor"):
                    self.assertEqual(agent_runner.resolve_backend("proj"), "cursor")

    def test_resolve_backend_mixed_uses_preference(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch(
                "lib.agent_runner.get_config",
                return_value={"agent_backend": "auto", "mixed_backend_preference": "cursor"},
            ):
                with mock.patch("lib.agent_runner.classify_pending_sources", return_value="mixed"):
                    with mock.patch("lib.agent_runner._find_agent_cli", return_value="/usr/bin/agent"):
                        self.assertEqual(agent_runner.resolve_backend("proj"), "cursor")

    def test_resolve_backend_mixed_prism_source_wins(self):
        with mock.patch.dict("os.environ", {"PRISM_SOURCE": "claude_code"}, clear=True):
            with mock.patch("lib.agent_runner.classify_pending_sources", return_value="mixed"):
                self.assertEqual(agent_runner.resolve_backend("proj"), "claude")

    def test_backend_from_prism_source(self):
        with mock.patch.dict("os.environ", {"PRISM_SOURCE": "cursor"}, clear=True):
            self.assertEqual(agent_runner.backend_from_prism_source(), "cursor")
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(agent_runner.backend_from_prism_source())

    @mock.patch("lib.agent_runner.subprocess.run")
    @mock.patch("lib.agent_runner.shutil.which", return_value="/usr/bin/claude")
    def test_run_claude_argv_unchanged(self, _which, run):
        run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
        result = agent_runner.run_agent(
            "prompt",
            tier="fast",
            backend="claude",
        )
        self.assertEqual(result.returncode, 0)
        argv = run.call_args[0][0]
        self.assertTrue(argv[0].endswith("claude"))
        self.assertEqual(argv[1:6], ["--print", "--model", "haiku", "-p", "prompt"])
        self.assertIn("--allowedTools", argv)
        self.assertIn("Read,Write,Glob,Grep", argv)

    @mock.patch("lib.agent_runner.subprocess.run")
    @mock.patch("lib.agent_runner._find_agent_cli", return_value="/usr/bin/agent")
    def test_run_cursor_argv(self, _find, run):
        run.return_value = mock.Mock(returncode=0, stdout="ok", stderr="")
        with mock.patch(
            "lib.agent_runner.get_config",
            return_value={
                "cursor_models": {
                    "fast": "composer-2.5[fast=false]",
                    "strong": "claude-4.6-sonnet-medium",
                },
            },
        ):
            result = agent_runner.run_agent(
                "prompt",
                tier="strong",
                write_files=True,
                backend="cursor",
            )
        self.assertEqual(result.backend, "cursor")
        argv = run.call_args[0][0]
        self.assertEqual(argv[0], "/usr/bin/agent")
        self.assertEqual(argv[1:3], ["-p", "prompt"])
        self.assertIn("--model", argv)
        self.assertIn("claude-4.6-sonnet-medium", argv)
        self.assertIn("--force", argv)

    @mock.patch("lib.agent_runner._find_agent_cli", return_value="")
    def test_cursor_cli_missing(self, _find):
        result = agent_runner.run_agent("p", tier="fast", backend="cursor")
        self.assertTrue(result.cli_missing)


class TriggerBackendTests(unittest.TestCase):
    @mock.patch("lib.trigger.extraction_in_progress", return_value=False)
    @mock.patch("lib.trigger.subprocess.Popen")
    @mock.patch("lib.trigger._find_prism_cli", return_value="/tmp/prism")
    @mock.patch("lib.trigger._try_acquire_pending", return_value=True)
    @mock.patch("lib.trigger.open", new_callable=mock.mock_open)
    def test_auto_extract_passes_backend_from_prism_source(
        self, _open, _pending, _cli, popen, _in_progress,
    ):
        from lib import trigger

        with mock.patch.dict("os.environ", {"PRISM_SOURCE": "cursor"}, clear=True):
            started = trigger.request_auto_extraction("pid123", obs_count=20, quiet=True)
        self.assertTrue(started)
        popen.assert_called_once()
        args = popen.call_args[0][0]
        self.assertIn("--backend", args)
        self.assertIn("cursor", args)


if __name__ == "__main__":
    unittest.main()
