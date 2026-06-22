"""Subprocess runners for IDE-native agent CLIs (Claude Code or Cursor agent)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import PRISM_HOME, get_config

Tier = Literal["fast", "strong"]
Backend = Literal["claude", "cursor"]
PendingKind = Literal["cursor", "claude", "mixed", "empty"]

DEFAULT_CURSOR_MODELS = {
    "fast": "composer-2.5[fast=false]",
    "strong": "claude-4.6-sonnet-medium",
}

_CLAUDE_HOOK_SOURCES = frozenset({"claude_code", "session_import", "session_review"})

_CLAUDE_TOOLS: dict[Tier, list[str]] = {
    "fast": ["Read", "Write", "Glob", "Grep"],
    "strong": ["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
}

_CLAUDE_MODELS: dict[Tier, str] = {
    "fast": "haiku",
    "strong": "sonnet",
}


@dataclass(frozen=True)
class AgentResult:
    returncode: int
    stdout: str
    stderr: str
    backend: str
    timed_out: bool = False
    cli_missing: bool = False


def backend_from_prism_source() -> str | None:
    """Map hook PRISM_SOURCE env to extract backend, if set."""
    source = os.environ.get("PRISM_SOURCE", "").strip().lower()
    if source == "cursor":
        return "cursor"
    if source == "claude_code":
        return "claude"
    return None


def resolve_backend(
    project_id: str | None = None,
    *,
    override: str | None = None,
) -> Backend:
    """Pick claude vs cursor for agentic subprocess calls."""
    if override in ("claude", "cursor"):
        return override  # type: ignore[return-value]

    env_backend = os.environ.get("PRISM_AGENT_BACKEND", "").strip().lower()
    if env_backend in ("claude", "cursor"):
        return env_backend  # type: ignore[return-value]

    config_backend = get_config().get("agent_backend", "auto")
    if config_backend in ("claude", "cursor"):
        return config_backend  # type: ignore[return-value]

    mapped = backend_from_prism_source()
    if mapped:
        return mapped  # type: ignore[return-value]

    if project_id and config_backend == "auto":
        kind = classify_pending_sources(project_id)
        if kind == "cursor":
            return "cursor"
        if kind == "claude":
            return "claude"
        if kind == "mixed":
            return _pick_mixed_backend()

    return "claude"


def classify_pending_sources(project_id: str) -> PendingKind:
    """Classify pending observation sources for backend routing."""
    counts = pending_source_counts(project_id)
    cursor_n = counts.get("cursor", 0)
    claude_n = counts.get("claude", 0)
    if cursor_n == 0 and claude_n == 0:
        return "empty"
    if cursor_n > 0 and claude_n > 0:
        return "mixed"
    if cursor_n > 0:
        return "cursor"
    return "claude"


def pending_source_counts(project_id: str) -> dict[str, int]:
    """Count pending observations grouped as cursor vs claude hook families."""
    try:
        from .storage import get_active
        obs = get_active(project_id)
    except Exception:
        return {"cursor": 0, "claude": 0}

    cursor_n = 0
    claude_n = 0
    for row in obs:
        src = row.get("source") or "claude_code"
        if src == "cursor":
            cursor_n += 1
        elif src in _CLAUDE_HOOK_SOURCES:
            claude_n += 1
    return {"cursor": cursor_n, "claude": claude_n}


def _pick_mixed_backend() -> Backend:
    """When pending obs are mixed (or preference applies), pick an available CLI."""
    config = get_config()
    pref = config.get("mixed_backend_preference", "cursor")
    if pref not in ("claude", "cursor"):
        pref = "cursor"
    other: Backend = "claude" if pref == "cursor" else "cursor"  # type: ignore[assignment]

    for candidate in (pref, other):
        if candidate == "cursor" and _find_agent_cli():
            return "cursor"
        if candidate == "claude" and shutil.which("claude"):
            return "claude"
    return pref  # type: ignore[return-value]


def _cursor_models() -> dict[str, str]:
    config = get_config()
    models = config.get("cursor_models")
    if isinstance(models, dict):
        merged = dict(DEFAULT_CURSOR_MODELS)
        for tier in ("fast", "strong"):
            val = models.get(tier)
            if isinstance(val, str) and val.strip():
                merged[tier] = val.strip()
        return merged
    return dict(DEFAULT_CURSOR_MODELS)


def _find_agent_cli() -> str:
    for name in ("agent", "cursor-agent"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (
        Path.home() / ".local" / "bin" / "agent",
        Path.home() / ".cursor" / "bin" / "agent",
    ):
        if candidate.is_file():
            return str(candidate)
    return ""


def run_agent(
    prompt: str,
    *,
    tier: Tier,
    cwd: Path | None = None,
    timeout: int = 300,
    write_files: bool = False,
    project_id: str | None = None,
    backend: str | None = None,
) -> AgentResult:
    """Run a one-shot agent prompt via the resolved IDE CLI backend."""
    resolved = resolve_backend(project_id, override=backend)
    workdir = cwd or PRISM_HOME
    if resolved == "cursor":
        return _run_cursor(prompt, tier=tier, cwd=workdir, timeout=timeout, write_files=write_files)
    return _run_claude(prompt, tier=tier, cwd=workdir, timeout=timeout)


def _run_claude(prompt: str, *, tier: Tier, cwd: Path, timeout: int) -> AgentResult:
    cli = shutil.which("claude") or ""
    if not cli:
        return AgentResult(0, "", "", "claude", cli_missing=True)

    argv = [
        cli, "--print", "--model", _CLAUDE_MODELS[tier], "-p", prompt,
        "--allowedTools", ",".join(_CLAUDE_TOOLS[tier]),
    ]
    return _subprocess(argv, cwd=cwd, timeout=timeout, backend="claude")


def _run_cursor(
    prompt: str,
    *,
    tier: Tier,
    cwd: Path,
    timeout: int,
    write_files: bool,
) -> AgentResult:
    cli = _find_agent_cli()
    if not cli:
        return AgentResult(0, "", "", "cursor", cli_missing=True)

    model = _cursor_models()[tier]
    argv = [cli, "-p", prompt, "--model", model, "--output-format", "text"]
    if write_files:
        argv.append("--force")
    return _subprocess(argv, cwd=cwd, timeout=timeout, backend="cursor")


def _subprocess(argv: list[str], *, cwd: Path, timeout: int, backend: str) -> AgentResult:
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
        )
        return AgentResult(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            backend=backend,
        )
    except subprocess.TimeoutExpired:
        return AgentResult(1, "", "", backend, timed_out=True)
    except FileNotFoundError:
        return AgentResult(0, "", "", backend, cli_missing=True)


def cli_missing_message(backend: str) -> str:
    if backend == "cursor":
        return (
            "Error: 'agent' CLI not found. Install Cursor CLI: "
            "curl https://cursor.com/install -fsS | bash"
        )
    return "Error: 'claude' CLI not found. Install Claude Code to use extraction."


def failure_message(result: AgentResult) -> str:
    """Best-effort error text from a failed agent subprocess."""
    if result.timed_out:
        return "timeout"
    msg = (result.stderr.strip() or result.stdout.strip() or "(no output)")[:500]
    return msg
