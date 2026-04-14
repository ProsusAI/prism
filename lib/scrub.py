"""Secret scrubbing for observation payloads."""

import re

from .config import get_config

MAX_PAYLOAD_LENGTH = 500


def scrub_text(text: str) -> str:
    """Remove secrets from text using configured patterns."""
    config = get_config()
    result = text
    for pattern in config.get("scrub_patterns", []):
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
