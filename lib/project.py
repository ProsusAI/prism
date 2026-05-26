"""Project detection via git remote URL hashing."""

import hashlib
import os
import subprocess
from pathlib import Path

_project_root_cache: str = ""


def cached_project_id_path() -> Path:
    """Path to the project ID cache written by ``prism init``."""
    return get_project_root() / ".claude" / ".prism_project_id"


def read_cached_project_id() -> str:
    """Return cached project ID from ``.claude/.prism_project_id``, or \"\"."""
    path = cached_project_id_path()
    if not path.exists():
        return ""
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def capture_hook_command(
    hook_script: str,
    phase: str,
    project_id: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Shell command for PreToolUse capture with ``PRISM_PROJECT_ID`` set."""
    env = {"PRISM_PROJECT_ID": project_id}
    if extra_env:
        env.update(extra_env)
    assignments = " ".join(f"{key}={value}" for key, value in env.items())
    return f"env {assignments} {hook_script} {phase}"


def detect_project_id() -> str:
    """Detect project ID from env, init cache, or git metadata.

    Priority:
    1. PRISM_PROJECT_ID env var
    2. ``.claude/.prism_project_id`` at the git repo root (from ``prism init``)
    3. SHA256[:12] of git remote origin URL (portable across machines)
    4. SHA256[:12] of git repo root path (machine-specific fallback)
    5. ``global`` (no project detected)
    """
    env_id = os.environ.get("PRISM_PROJECT_ID")
    if env_id:
        return env_id

    cached = read_cached_project_id()
    if cached:
        return cached

    remote_url = _git_remote_url()
    if remote_url:
        return hashlib.sha256(remote_url.encode()).hexdigest()[:12]

    repo_root = _git_repo_root()
    if repo_root:
        return hashlib.sha256(repo_root.encode()).hexdigest()[:12]

    return "global"


def detect_project_name() -> str:
    """Best-effort project name from git remote or directory."""
    remote_url = _git_remote_url()
    if remote_url:
        # Extract repo name from URL: git@github.com:user/repo.git -> repo
        name = remote_url.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name

    repo_root = _git_repo_root()
    if repo_root:
        return os.path.basename(repo_root)

    return "unknown"


def detect_project_remote() -> str:
    """Return git remote URL or empty string."""
    return _git_remote_url() or ""


def _git_remote_url() -> str:
    """Get git remote origin URL, or empty string."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def get_project_root() -> Path:
    """Return the git repository root, or cwd if not in a git repo.

    Cached after first call — safe to call repeatedly within one process.
    """
    global _project_root_cache
    if not _project_root_cache:
        root = _git_repo_root()
        _project_root_cache = root if root else os.getcwd()
    return Path(_project_root_cache)


def _git_repo_root() -> str:
    """Get git repository root path, or empty string."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
