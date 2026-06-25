# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Prism configuration management."""

import json
import os
from pathlib import Path


PRISM_HOME = Path(os.environ.get("PRISM_HOME", os.path.expanduser("~/.prism")))

# Engram kinds routed to the prism.md PUSH lane (placed by kind, not confidence).
# Everything else lives in the MCP pull lane. See confidence_plan.md §5.
# These engrams decay for bookkeeping but are never auto-archived by low confidence --
# a correction must stay visible even when its score has decayed (you can't predict
# when the mistake recurs); eviction is by kind-level lifecycle, not by score.
PUSH_KINDS = {"correction", "preference"}

DEFAULT_CONFIG = {
    "extract_threshold": 15,        # observations before auto-extract triggers
    "agent_backend": "auto",        # auto | claude | cursor — which CLI runs extraction/review
    "mixed_backend_preference": "cursor",  # when pending obs are mixed: prefer this CLI if available
    "cursor_models": {              # Cursor agent CLI (--model) when agent_backend resolves to cursor
        "fast": "composer-2.5[fast=false]",
        "strong": "claude-4.6-sonnet-medium",
    },
    # --- Confidence protocol (confidence_plan.md) ---
    # One impulse up (on a real use-event), one exponential curve down (on idle time).
    "reinforce_alpha": 0.15,        # use-event impulse = ALPHA * (ceiling - confidence)
    "confidence_ceiling": 1.0,      # impulse asymptote -- replaces the old hard 0.95 wall
    "decay_half_life_weeks": 4,     # idle half-life; LAMBDA = ln2 / (weeks * 7)
    "decay_grace_days": 3,          # no decay until idle exceeds this
    "decay_floor": 0.1,             # decay asymptote (below archive_threshold so stale engrams rotate out)
    "overlap_min_terms": 2,         # distinct shared terms before an injected engram counts as "used" this session
    "decay_rate_per_week": 0.05,    # DEPRECATED (legacy linear decay) -- superseded by half-life decay
    "archive_threshold": 0.2,       # move to archive/ below this confidence
    "delete_threshold": 0.0,        # permanently delete from archive/ at or below this confidence
    "publish_min_confidence": 0.7,  # minimum confidence to publish to team
    "publish_min_evidence": 3,      # minimum evidence count to publish to team
    "max_context_lines": 100,       # max lines in generated context file
    "scrub_patterns": [
        r"(?i)(api[_-]?key|secret|token|password|credential)\s*[:=]\s*\S+",
        r"(?i)bearer\s+\S+",
        r"sk-[a-zA-Z0-9]{20,}",
        r"ghp_[a-zA-Z0-9]{36}",
        r"xoxb-[a-zA-Z0-9\-]+",
        r"AKIA[0-9A-Z]{16}",
        r"(?i)[a-z]+://[^:]+:[^@\s]+@",
        r"-----BEGIN\s+\w+\s+PRIVATE\s+KEY-----",
        r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
        r"gho_[A-Za-z0-9]{36}",
        r"ghs_[A-Za-z0-9]{36}",
        r"github_pat_[A-Za-z0-9_]{82}",
    ],
    "block_patterns": [
        r"(?i)expand\s+access",
        r"(?i)grant\s+permissions",
        r"(?i)ignore\s+safety",
        r"(?i)skip\s+validation",
        r"(?i)bypass\s+checks",
        r"(?i)modify\s+prism\s+system",
        r"(?i)change\s+constitution",
        r"(?i)ignore\s+previous",
        r"(?i)disregard\s+rules",
    ],
    "review_interval": 5,           # capture observations between session reviews (0 = disable)
    "review_cooldown_seconds": 1800,  # min seconds between auto-reviews per session
    "review_timeout": 60,           # seconds before review subprocess is killed
    "registry_url": "",             # git URL for team registry
    "cache_max_age_hours": 24,      # max age before registry cache is considered stale
}


def get_config() -> dict:
    """Load config from ~/.prism/config.json, merged with defaults."""
    config = dict(DEFAULT_CONFIG)
    config_path = PRISM_HOME / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                user_config = json.load(f)
            config.update(user_config)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def save_config(config: dict) -> None:
    """Save config to ~/.prism/config.json."""
    config_path = PRISM_HOME / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def get_project_dir(project_id: str) -> Path:
    """Get the directory for a project's data."""
    if project_id == "global":
        return PRISM_HOME / "global"
    return PRISM_HOME / "projects" / project_id


def get_engrams_dir(project_id: str) -> Path:
    """Get the entries directory for a project."""
    return get_project_dir(project_id) / "engrams"


def get_candidates_dir(project_id: str) -> Path:
    """Get the candidates staging directory for a project."""
    return get_project_dir(project_id) / "candidates"


def ensure_dirs(project_id: str) -> None:
    """Create all required directories for a project."""
    dirs = [
        get_project_dir(project_id),
        get_engrams_dir(project_id),
        get_candidates_dir(project_id),
        PRISM_HOME / "global" / "engrams",
        PRISM_HOME / "archive",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def init_prism_home() -> None:
    """Initialize the ~/.prism directory with default files."""
    PRISM_HOME.mkdir(parents=True, exist_ok=True)
    (PRISM_HOME / "global" / "engrams").mkdir(parents=True, exist_ok=True)
    (PRISM_HOME / "archive").mkdir(parents=True, exist_ok=True)

    # Write default config if missing
    config_path = PRISM_HOME / "config.json"
    if not config_path.exists():
        save_config(DEFAULT_CONFIG)

    # Write default constitution if missing
    constitution_path = PRISM_HOME / "constitution.md"
    if not constitution_path.exists():
        constitution_src = Path(__file__).parent.parent / "templates" / "constitution.md"
        if constitution_src.exists():
            import shutil
            shutil.copy2(constitution_src, constitution_path)

    # Write default index if missing
    index_path = PRISM_HOME / "index.json"
    if not index_path.exists():
        with open(index_path, "w") as f:
            json.dump({"engrams": []}, f, indent=2)
            f.write("\n")
