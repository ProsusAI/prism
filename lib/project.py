"""Project detection via git remote URL hashing."""

import hashlib
import os
import subprocess


def detect_project_id() -> str:
    """Detect project ID from git remote, repo path, or env var.

    Priority:
    1. PRISM_PROJECT_ID env var
    2. SHA256[:12] of git remote origin URL (portable across machines)
    3. SHA256[:12] of git repo root path (machine-specific fallback)
    4. "global" (no project detected)
    """
    env_id = os.environ.get("PRISM_PROJECT_ID")
    if env_id:
        return env_id

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
