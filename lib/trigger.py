"""Auto-extraction trigger — single policy for background extract spawns."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import PRISM_HOME, ensure_dirs, get_config, get_project_dir
from .storage import count_active

STALE_SECONDS = 600  # match extract.py lock staleness


def extraction_in_progress(prism_home: Path | None = None) -> bool:
    """True if a non-stale ~/.prism/.extracting lock is held."""
    home = prism_home or PRISM_HOME
    lock = home / ".extracting"
    if not lock.exists():
        return False
    try:
        return (time.time() - lock.stat().st_mtime) <= STALE_SECONDS
    except OSError:
        return False


def _pending_path(project_id: str) -> Path:
    ensure_dirs(project_id)
    return get_project_dir(project_id) / ".extract_pending"


def clear_extract_pending(project_id: str) -> None:
    """Drop per-project pending flag (called when extract finishes)."""
    try:
        _pending_path(project_id).unlink(missing_ok=True)
    except OSError:
        pass


def _try_acquire_pending(project_id: str) -> bool:
    """Atomically claim a pending auto-extract slot for this project."""
    path = _pending_path(project_id)
    if path.exists():
        try:
            if (time.time() - path.stat().st_mtime) > STALE_SECONDS:
                path.unlink(missing_ok=True)
            else:
                return False
        except OSError:
            return False
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def _log_trigger(msg: str) -> None:
    """Append a one-line note to extraction.log. Never raises.

    The trigger path is otherwise silent on failure (capture.py swallows all
    exceptions, and only a successfully-spawned child writes to the log), which
    made a non-firing auto-extract impossible to diagnose. Any bail-out reason
    is recorded here so the failure mode is always observable.
    """
    try:
        with open(PRISM_HOME / "extraction.log", "a") as f:
            f.write(f"[trigger {int(time.time())}] {msg}\n")
    except OSError:
        pass


def request_auto_extraction(
    project_id: str,
    *,
    obs_count: int | None = None,
    quiet: bool = False,
) -> bool:
    """Spawn background ``prism extract`` if threshold met and not already queued.

    Uses per-project ``.extract_pending`` (at-most-one spawn per backlog) plus the
  global ``.extracting`` lock. Manual ``prism extract`` bypasses this function.

    Returns True if a background extract was started.
    """
    if obs_count is None:
        obs_count = count_active(project_id, for_triggers=True)

    threshold = get_config().get("extract_threshold", 15)
    if obs_count < threshold:
        return False
    if extraction_in_progress():
        return False
    if not _try_acquire_pending(project_id):
        return False

    prism_cli = _find_prism_cli()
    if not prism_cli:
        clear_extract_pending(project_id)
        _log_trigger(
            f"{project_id}: prism CLI not found (PATH={os.environ.get('PATH', '')!r}); "
            "auto-extract skipped"
        )
        return False

    from .agent_runner import backend_from_prism_source

    extract_args = [sys.executable, prism_cli, "extract", "--project", project_id]
    hook_backend = backend_from_prism_source()
    if hook_backend:
        extract_args.extend(["--backend", hook_backend])

    log_path = PRISM_HOME / "extraction.log"
    try:
        with open(log_path, "a") as log_file:
            subprocess.Popen(
                extract_args,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )
    except OSError as e:
        clear_extract_pending(project_id)
        _log_trigger(f"{project_id}: spawn failed ({e}); cli={prism_cli!r}")
        return False

    if not quiet:
        print(
            f"Auto-extraction triggered ({obs_count} observations). "
            f"Running in background..."
        )
        print(f"  (output logged to {log_path})")
    return True


def maybe_trigger_extraction(project_id: str, quiet: bool = False) -> bool:
    """CLI safety-net entry point — same policy as capture hooks."""
    return request_auto_extraction(project_id, quiet=quiet)


def _find_prism_cli() -> str:
    """Resolve path to the prism CLI script.

    Deterministic locations come FIRST, ``shutil.which`` last: GUI-launched hooks
    (e.g. Cursor) inherit a stripped PATH without ``~/.local/bin``, so ``which``
    returns None there and the background spawn would silently never fire. The
    install always writes ``$PRISM_HOME/prism`` (install.sh), so anchor to that.
    All candidates are Python scripts, safe to run as ``[sys.executable, cli]``.
    """
    candidates = [
        PRISM_HOME / "prism",                     # canonical install location
        Path(__file__).parent.parent / "prism",   # dev/repo checkout
        Path.home() / ".local" / "bin" / "prism",  # symlink install target
    ]
    for cli in candidates:
        if cli.exists():
            return str(cli)

    on_path = shutil.which("prism")
    return on_path or ""
