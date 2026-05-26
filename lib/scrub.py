"""Secret scrubbing for observation payloads."""

import re
from typing import List

MAX_PAYLOAD_LENGTH = 500

# Hardcoded baseline patterns -- always applied regardless of config
# These are the minimum security floor for secret scrubbing
BASELINE_SCRUB_PATTERNS = [
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
]


def is_blocked_text(text: str, extra_patterns: "List[str] | None" = None) -> bool:
    """True if text matches adversarial / override patterns from config."""
    if not text:
        return False
    patterns: list[str] = []
    try:
        from .config import get_config
        for p in get_config().get("block_patterns", []):
            if p not in patterns:
                patterns.append(p)
    except (ImportError, Exception):
        pass
    if extra_patterns:
        for p in extra_patterns:
            if p not in patterns:
                patterns.append(p)
    for pattern in patterns:
        try:
            if re.search(pattern, text):
                return True
        except re.error:
            continue
    return False


def scrub_text(text: str, extra_patterns: "List[str] | None" = None) -> str:
    """Remove secrets from text using baseline + config + extra patterns.

    Pattern sources (all applied, deduplicated):
    1. BASELINE_SCRUB_PATTERNS (hardcoded, always applied)
    2. Config scrub_patterns (from config.json, user-extensible)
    3. extra_patterns parameter (caller-provided)
    """
    # Start with baseline patterns
    all_patterns = list(BASELINE_SCRUB_PATTERNS)

    # Add config patterns
    try:
        from .config import get_config
        config = get_config()
        config_patterns = config.get("scrub_patterns", [])
        for p in config_patterns:
            if p not in all_patterns:
                all_patterns.append(p)
    except (ImportError, Exception):
        pass  # Config unavailable -- baseline patterns still applied

    # Add extra patterns
    if extra_patterns:
        for p in extra_patterns:
            if p not in all_patterns:
                all_patterns.append(p)

    result = text
    for pattern in all_patterns:
        try:
            result = re.sub(pattern, "[REDACTED]", result)
        except re.error:
            continue
    return result


def truncate(text: str, max_length: int = MAX_PAYLOAD_LENGTH) -> str:
    """Truncate text to max_length, adding indicator if truncated."""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length] + "...[truncated]"


def sanitize_payload(text: str) -> str:
    """Scrub secrets and truncate a payload string."""
    return truncate(scrub_text(text))
