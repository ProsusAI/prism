#!/usr/bin/env python3
"""Prism observation capture processor.

Called by hooks/capture.sh via: python3 capture.py <phase>
Reads JSON from stdin (Claude Code hook payload), scrubs secrets,
appends one JSONL observation line, and checks trigger thresholds.

CRITICAL: This runs on EVERY tool use. Keep it fast.
CRITICAL: Never crash, never block. All exceptions swallowed.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "pre"
    prism_home = Path(os.environ.get("PRISM_HOME", os.path.expanduser("~/.prism")))

    # Read stdin (Claude Code hook payload)
    raw = sys.stdin.read()
    if not raw.strip():
        return

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = data.get("tool_name", "")
    session_id = data.get("session_id", "")
    tool_input = data.get("tool_input", {})

    # Detect project ID
    # Priority: PRISM_PROJECT_ID env > cached file > git detection
    project_id = _get_project_id(prism_home)
    project_dir = prism_home / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # Build input summary with scrubbing + truncation
    summary = _build_summary(tool_input)
    summary = _scrub_and_truncate(summary)

    # Build observation record
    obs = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": "tool_start" if phase == "pre" else "tool_end",
        "tool": tool_name,
        "input_summary": summary,
        "session": session_id,
        "project_id": project_id,
        "source": "claude_code",
    }

    # Atomic append using O_APPEND (OBS-04)
    # Single write under PIPE_BUF (4096 bytes) is atomic on POSIX
    line = json.dumps(obs, ensure_ascii=False) + "\n"
    line_bytes = line.encode("utf-8")
    obs_path = str(project_dir / "observations.jsonl")
    fd = os.open(obs_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line_bytes)
    finally:
        os.close(fd)

    # Session-start sentinel: once per project per day, fire prism sync in background
    # (restores +0.02 confidence-boost parity with MCP-queried engrams; see 260506-g5q)
    _check_session_sync(prism_home, project_id)

    # Trigger checks (background spawns, non-blocking)
    _check_triggers(prism_home, project_id, obs_path, session_id)


def _get_project_id(prism_home: Path) -> str:
    """Get project ID with caching for performance.

    Checks:
    1. PRISM_PROJECT_ID env var
    2. .prism_project_id file in cwd (written by prism init)
    3. Git remote detection (slow path, ~5ms for subprocess)
    """
    env_id = os.environ.get("PRISM_PROJECT_ID")
    if env_id:
        return env_id

    # Check cached project ID in cwd
    cached_path = Path.cwd() / ".claude" / ".prism_project_id"
    if cached_path.exists():
        try:
            cached = cached_path.read_text().strip()
            if cached:
                return cached
        except OSError:
            pass

    # Fall back to git detection (imported lazily)
    try:
        import hashlib
        import subprocess
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:12]

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:12]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return "global"


def _build_summary(tool_input) -> str:
    """Build a string summary from tool_input (may be dict, str, or other)."""
    if isinstance(tool_input, dict):
        return json.dumps(tool_input, ensure_ascii=False)
    elif isinstance(tool_input, str):
        return tool_input
    else:
        return str(tool_input)


def _scrub_and_truncate(text: str) -> str:
    """Scrub secrets and truncate to 500 chars (OBS-02, OBS-03).

    Imports from lib.scrub for pattern consistency, with inline fallback
    if import fails (capture must never crash).
    """
    try:
        # Try importing from the installed lib
        parent = Path(__file__).parent
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        if str(parent.parent) not in sys.path:
            sys.path.insert(0, str(parent.parent))
        from lib.scrub import sanitize_payload
        return sanitize_payload(text)
    except (ImportError, Exception):
        # Inline fallback: basic scrubbing if import fails
        import re
        patterns = [
            r"(?i)(api[_-]?key|secret|token|password|credential)\s*[:=]\s*\S+",
            r"(?i)bearer\s+\S+",
            r"sk-[a-zA-Z0-9]{20,}",
            r"ghp_[a-zA-Z0-9]{36}",
        ]
        result = text
        for p in patterns:
            try:
                result = re.sub(p, "[REDACTED]", result)
            except re.error:
                continue
        return result[:500]


def _check_triggers(prism_home: Path, project_id: str, obs_path: str, session_id: str) -> None:
    """Check if extraction or session review should be triggered (OBS-06, OBS-07).

    All triggers spawn background processes -- never block the hook.
    """
    try:
        # Count observations
        obs_count = 0
        with open(obs_path) as f:
            for _ in f:
                obs_count += 1
    except OSError:
        return

    # Load config for thresholds
    try:
        config_path = prism_home / "config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text())
        else:
            config = {}
    except (json.JSONDecodeError, OSError):
        config = {}

    extract_threshold = config.get("extract_threshold", 15)
    review_interval = config.get("review_interval", 5)

    # Auto-extraction trigger (OBS-06)
    if obs_count >= extract_threshold and not (prism_home / ".extracting").exists():
        _spawn_background(prism_home, ["extract", "--project", project_id])

    # Session review trigger (OBS-07)
    if (review_interval > 0 and obs_count > 0 and
        obs_count % review_interval == 0 and
        session_id and
        not (prism_home / ".reviewing").exists()):
        _spawn_background(prism_home, ["review", "--session", session_id, "--project", project_id])


def _spawn_background(prism_home: Path, args: list) -> None:
    """Spawn a background prism command. Non-blocking, fire-and-forget."""
    import shutil
    import subprocess

    # Find prism CLI
    prism_cli = shutil.which("prism")
    if not prism_cli:
        candidate = prism_home / "prism"
        if candidate.exists():
            prism_cli = str(candidate)

    if not prism_cli:
        return

    try:
        with open(os.devnull, "w") as devnull:
            subprocess.Popen(
                [sys.executable, prism_cli] + args,
                stdout=devnull,
                stderr=devnull,
                start_new_session=True,
            )
    except OSError:
        pass


def _check_session_sync(prism_home: Path, project_id: str) -> None:
    """Fire `prism sync` once per project per UTC-day.

    Fires sync_claude_code -> reinforce_entries once per project per day, restoring
    confidence-boost parity with MCP-queried engrams (which get +0.02 per search).
    See quick task 260506-g5q.

    Sentinel path: /tmp/prism_synced_{project_id}_{YYYYMMDD-UTC}

    Hot path (sentinel exists) is a single os.path.exists() call. On the first call
    of the day, stale sentinels for this project are cleaned and the spawn is fired.
    All exceptions are swallowed so capture.py can never crash.
    """
    try:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        sentinel_name = f"prism_synced_{project_id}_{today}"
        sentinel_path = f"/tmp/{sentinel_name}"

        # Hot path: single os.path.exists() — no stat, no open, no read.
        if os.path.exists(sentinel_path):
            return

        # Slow path (first call of the day for this project).
        # Clean stale sentinels for THIS project (different date suffix).
        prefix = f"prism_synced_{project_id}_"
        try:
            for entry in os.listdir("/tmp"):
                if entry.startswith(prefix) and entry != sentinel_name:
                    try:
                        os.unlink(f"/tmp/{entry}")
                    except OSError:
                        pass
        except OSError:
            # /tmp listing failed — skip cleanup silently
            pass

        # Atomic create: O_CREAT | O_EXCL | O_WRONLY. If another concurrent capture
        # already created it, FileExistsError is raised — silent return (race lost).
        try:
            fd = os.open(
                sentinel_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.close(fd)
        except FileExistsError:
            # Another concurrent capture won the race.
            return
        except OSError:
            # /tmp not writable, full disk, etc. — never crash.
            return

        # Sentinel created. Fire-and-forget background sync for this project.
        _spawn_background(prism_home, ["sync", "--project", project_id])
    except Exception:
        # Belt-and-suspenders: capture.py must never crash (OBS-05).
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # NEVER crash, NEVER block Claude Code (OBS-05)
