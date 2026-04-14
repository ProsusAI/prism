"""Auto-extraction trigger - spawns background extraction when threshold is met."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import PRISM_HOME, get_config, get_observations_path


def maybe_trigger_extraction(project_id: str, quiet: bool = False) -> bool:
    """Check if extraction should run, and spawn it in background if so.

    Returns True if extraction was triggered.
    """
    observations_path = get_observations_path(project_id)
    if not observations_path.exists():
        return False

    # Count observations
    try:
        with open(observations_path) as f:
            obs_count = sum(1 for _ in f)
    except OSError:
        return False

    config = get_config()
    threshold = config.get("extract_threshold", 15)
    if obs_count < threshold:
        return False

    # Check if extraction is already running (stale lock = > 10 min old)
    lock = PRISM_HOME / ".extracting"
    if lock.exists():
        try:
            age = time.time() - lock.stat().st_mtime
            if age <= 600:
                return False
        except OSError:
            return False

    # Find the prism CLI
    prism_cli = _find_prism_cli()
    if not prism_cli:
        return False

    # Spawn extraction in background
    try:
        devnull = open(os.devnull, "w")
        subprocess.Popen(
            [sys.executable, prism_cli, "extract", "--project", project_id],
            stdout=devnull,
            stderr=devnull,
            start_new_session=True,
        )
        if not quiet:
            print(f"Auto-extraction triggered ({obs_count} observations). Running in background...")
        return True
    except OSError:
        return False


def _find_prism_cli() -> str:
    """Resolve path to the prism CLI script."""
    # Check if prism is on PATH
    on_path = shutil.which("prism")
    if on_path:
        return on_path

    # Check relative to this file (repo layout: lib/trigger.py -> ../prism)
    repo_cli = Path(__file__).parent.parent / "prism"
    if repo_cli.exists():
        return str(repo_cli)

    return ""
