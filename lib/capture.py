#!/usr/bin/env python3
# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Prism observation capture processor.

Called by hooks/capture.sh (Claude Code) or hooks/capture_cursor.sh (Cursor)
via: python3 capture.py <phase>
Reads JSON from stdin (Claude Code / Cursor hook payload), scrubs/compresses/
truncates summaries into SQLite, and checks trigger thresholds.

CRITICAL: This runs on EVERY tool use. Keep it fast.
CRITICAL: Never crash, never block. All exceptions swallowed.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "pre"
    prism_home = Path(os.environ.get("PRISM_HOME", os.path.expanduser("~/.prism")))

    # Read stdin hook payload. Claude Code and Cursor both send snake_case JSON
    # with the fields we read here (session_id, tool_name, tool_input), so no
    # per-source field remapping is needed.
    raw = sys.stdin.read()
    if not raw.strip():
        return

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    source = os.environ.get("PRISM_SOURCE", "claude_code")

    tool_name = data.get("tool_name", "")
    session_id = data.get("session_id", "")
    tool_input = data.get("tool_input", {})

    _ensure_prism_on_path(prism_home)
    from lib.project import detect_project_id

    # Project id is normally baked into the hook env (PRISM_PROJECT_ID). If it is
    # not, fall back to the workspace path Cursor sends in the payload (cwd, or
    # workspace_roots[0]) so detection runs against the real project, not the
    # hook process's cwd.
    if not os.environ.get("PRISM_PROJECT_ID"):
        cursor_cwd = data.get("cwd") or (data.get("workspace_roots") or [None])[0]
        if isinstance(cursor_cwd, str) and os.path.isdir(cursor_cwd):
            try:
                os.chdir(cursor_cwd)
            except OSError:
                pass

    project_id = detect_project_id()

    # Build input summary: scrub, block check, compress, truncate (OBS-02, OBS-03).
    # Pass cwd as the project root so absolute paths are stored relative — cwd is
    # free (the Cursor chdir above already set it), unlike get_project_root() which
    # would add a git subprocess to every tool call.
    summary = _prepare_summary(tool_input, os.getcwd())
    if summary is None:
        return  # block_patterns matched — do not persist

    event = "tool_start" if phase == "pre" else "tool_end"
    obs_count = _write_observation(prism_home, session_id, project_id, event, tool_name, source, summary)

    # Session-start sentinel: once per project per day, fire prism sync in background
    # (restores +0.02 confidence-boost parity with MCP-queried engrams; see 260506-g5q)
    _check_session_sync(prism_home, project_id)

    # Trigger checks (background spawns, non-blocking)
    _check_triggers(prism_home, project_id, obs_count, session_id)


# Tool-input fields that never contribute to an engram. Identical across Claude
# Code and Cursor (Cursor normalizes to the same tool schema). Dropping them
# means the truncation budget goes to the high-value field (Write `content`,
# Shell `command`, Edit `new_string`) instead of metadata like an always-empty
# cwd or a constant timeout.
_NOISE_KEYS = frozenset({"cwd", "timeout", "output_mode", "head_limit", "multiline", "-n"})


def _strip_root(text: str, root: str) -> str:
    """Rewrite absolute paths under the project root as relative ones.

    The machine-specific prefix (e.g. /Users/<name>/Documents/<project>) repeats
    on every observation — in file_path and embedded in shell `cd` commands — and
    is pure noise that steals truncation budget from the high-value content. We
    anchor strictly to the project root, so paths outside it keep their full path.
    """
    if not root or root == "/" or root not in text:
        return text
    # "/root/src/x.js" -> "src/x.js"; bare "/root" (e.g. `cd /root`) -> "."
    return text.replace(root + "/", "").replace(root, ".")


def _build_summary(tool_input, root: str = "") -> str:
    """Build a string summary from tool_input (may be dict, str, or other)."""
    if isinstance(tool_input, dict):
        cleaned = {
            k: v for k, v in tool_input.items()
            if k not in _NOISE_KEYS and v not in ("", None, [], {})
        }
        # Fall back to the original if cleaning emptied it (don't store "{}").
        text = json.dumps(cleaned or tool_input, ensure_ascii=False)
    elif isinstance(tool_input, str):
        text = tool_input
    else:
        text = str(tool_input)
    return _strip_root(text, root)


def _prepare_summary(tool_input, root: str = "") -> str | None:
    """Build, scrub, compress, and truncate tool input for storage."""
    text = _build_summary(tool_input, root)
    return _prepare_input_summary(text)


def _ensure_prism_on_path(prism_home: Path) -> None:
    """Put PRISM_HOME on sys.path; drop lib/ script dir (avoids import shadowing)."""
    home = str(prism_home.resolve())
    lib_dir = str(Path(__file__).resolve().parent)
    if home not in sys.path:
        sys.path.insert(0, home)
    if lib_dir in sys.path and lib_dir != home:
        sys.path.remove(lib_dir)


def _prepare_input_summary(text: str) -> str | None:
    """Scrub, compress, truncate. Inline fallback if imports fail (OBS-05)."""
    try:
        prism_home = Path(os.environ.get("PRISM_HOME", os.path.expanduser("~/.prism")))
        _ensure_prism_on_path(prism_home)
        from lib.observation_summary import prepare_input_summary
        return prepare_input_summary(text)
    except (ImportError, Exception):
        import re
        scrub_patterns = [
            r"(?i)(api[_-]?key|secret|token|password|credential)\s*[:=]\s*\S+",
            r"(?i)bearer\s+\S+",
            r"sk-[a-zA-Z0-9]{20,}",
            r"ghp_[a-zA-Z0-9]{36}",
        ]
        block_patterns = [
            r"(?i)expand\s+access",
            r"(?i)grant\s+permissions",
            r"(?i)ignore\s+safety",
            r"(?i)skip\s+validation",
            r"(?i)bypass\s+checks",
            r"(?i)modify\s+prism\s+system",
            r"(?i)change\s+constitution",
            r"(?i)ignore\s+previous",
            r"(?i)disregard\s+rules",
        ]
        result = text
        for p in scrub_patterns:
            try:
                result = re.sub(p, "[REDACTED]", result)
            except re.error:
                continue
        for p in block_patterns:
            try:
                if re.search(p, result):
                    return None
            except re.error:
                continue
        if len(result) > 500:
            result = result[:500] + "...[truncated]"
        return result


def _write_observation(
    prism_home: Path,
    session_id: str,
    project_id: str,
    event: str,
    tool: str,
    source: str,
    input_summary: str,
) -> int:
    """Insert observation into SQLite. Returns active count. Never raises."""
    try:
        _ensure_prism_on_path(prism_home)
        from lib.storage import init_db, insert_observation
        db_path = prism_home / "prism.db"
        if not db_path.exists():
            init_db(db_path)
        _, _backlog, trigger_count = insert_observation(
            session_id=session_id,
            project_id=project_id,
            event=event,
            tool=tool,
            source=source,
            input_summary=input_summary,
            db_path=db_path,
        )
        return trigger_count
    except Exception:
        return 0  # NEVER crash (OBS-05)


def _check_triggers(prism_home: Path, project_id: str, trigger_count: int, session_id: str) -> None:
    """Spawn background extraction / review when thresholds are crossed (OBS-06, OBS-07).

    ``trigger_count`` excludes session_insight rows so review/extract are not
    accelerated by synthetic Haiku output. Comes from the INSERT transaction.
    """
    try:
        _ensure_prism_on_path(prism_home)
        from lib.trigger import request_auto_extraction

        request_auto_extraction(project_id, obs_count=trigger_count, quiet=True)
    except Exception:
        pass

    try:
        config_path = prism_home / "config.json"
        config = json.loads(config_path.read_text()) if config_path.exists() else {}
    except (json.JSONDecodeError, OSError):
        config = {}

    review_interval = config.get("review_interval", 5)
    review_cooldown = config.get("review_cooldown_seconds", 1800)

    # Session review trigger (OBS-07) — capture events only, with per-session cooldown
    if (
        review_interval > 0
        and trigger_count > 0
        and trigger_count % review_interval == 0
        and session_id
        and _try_acquire_review_sentinel(session_id, review_cooldown)
    ):
        _spawn_background(prism_home, ["review", "--session", session_id, "--project", project_id])


def _review_sentinel_path(session_id: str) -> str:
    """Stable /tmp path for per-session review cooldown (hashed session id)."""
    import hashlib

    digest = hashlib.sha256(session_id.encode()).hexdigest()[:16]
    return f"/tmp/prism_review_{digest}"


def _try_acquire_review_sentinel(session_id: str, cooldown_seconds: int) -> bool:
    """Return True if this session may spawn an auto-review (cooldown + atomic create)."""
    if cooldown_seconds <= 0:
        return True
    path = _review_sentinel_path(session_id)
    try:
        if os.path.exists(path):
            if time.time() - os.path.getmtime(path) < cooldown_seconds:
                return False
            os.unlink(path)
    except OSError:
        return False
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


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

    Regenerates prism.md from the index so newly-created corrections/preferences and
    decayed scores are reflected. Sync is READ-ONLY with respect to confidence -- it no
    longer reinforces the engrams it selects (that was the circular rich-get-richer loop;
    see confidence_plan.md §1). Confidence now moves only on real use-events: MCP retrieval,
    or the overlap signal in review.py.

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
