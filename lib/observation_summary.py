# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Prepare observation input_summary for SQLite: scrub, compress, truncate."""

from __future__ import annotations

from .scrub import is_blocked_text, scrub_text, truncate

# Observation summaries keep more than scrub's generic 500-char security cap: the
# high-value field (Write `content`, Shell `command`, Edit `new_string`) is what
# extraction reads, and 500 chars truncated it away. Secrets are already removed
# by scrub_text() before truncation, so a larger cap here is safe.
MAX_OBSERVATION_LENGTH = 2000


def prepare_input_summary(text: str, intensity: str = "lite", compress: bool = True) -> str | None:
    """Scrub secrets, optionally compress prose, then cap length.

    Returns None when ``block_patterns`` match (caller must skip the observation).
    Pass compress=False for already-distilled text (e.g. reviewer insights) to
    avoid lossy article/filler removal on content that carries its own meaning.
    Safe for hot-path callers: compression failures fall back to scrubbed text.
    """
    if not text:
        return ""
    scrubbed = scrub_text(text)
    if is_blocked_text(scrubbed):
        return None
    if not compress:
        return truncate(scrubbed, MAX_OBSERVATION_LENGTH)
    try:
        from .compress import compress as _compress

        body = _compress(scrubbed, intensity)
    except Exception:
        body = scrubbed
    return truncate(body, MAX_OBSERVATION_LENGTH)
