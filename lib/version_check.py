# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Version check — compares installed commit against remote HEAD, once per day."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_CACHE_TTL = 86400  # 24 hours


def _prism_home() -> Path:
    return Path(os.environ.get("PRISM_HOME", Path.home() / ".prism"))


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _remote_head(source_url: str) -> str:
    try:
        r = subprocess.run(
            ["git", "ls-remote", source_url, "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout.split()[0]
    except Exception:
        pass
    return ""


def maybe_print_update_notice() -> None:
    """Print an update notice to stderr if a newer commit exists upstream (cached 24h)."""
    home = _prism_home()
    local_commit = _read(home / ".commit")
    source_url = _read(home / ".source_url")

    if not local_commit or not source_url:
        return

    cache_file = home / ".update_cache"
    now = time.time()

    try:
        cached = json.loads(cache_file.read_text())
        if now - cached.get("ts", 0) < _CACHE_TTL:
            if not cached.get("up_to_date", True):
                _print_notice(home)
            return
    except Exception:
        pass

    remote_commit = _remote_head(source_url)
    if not remote_commit:
        return  # network unavailable — skip silently

    # short-SHA prefix match handles detached HEAD installs
    up_to_date = (
        remote_commit == local_commit
        or remote_commit.startswith(local_commit)
        or local_commit.startswith(remote_commit)
    )

    try:
        cache_file.write_text(json.dumps({
            "ts": now,
            "up_to_date": up_to_date,
            "remote_commit": remote_commit,
            "local_commit": local_commit,
        }))
    except Exception:
        pass

    if not up_to_date:
        _print_notice(home)


def _print_notice(home: Path) -> None:
    version = _read(home / "VERSION")
    install_source = _read(home / ".install_source")
    ver = f" (installed: {version})" if version else ""
    update_cmd = f"cd {install_source} && git pull && ./install.sh" if install_source else "git pull && ./install.sh in your prism repo"
    print(f"\nNote: A Prism update is available{ver}. To upgrade:\n  {update_cmd}\n", file=sys.stderr)
