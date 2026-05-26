"""Prepare observation input_summary for SQLite: scrub, compress, truncate."""

from .scrub import MAX_PAYLOAD_LENGTH, is_blocked_text, scrub_text, truncate


def prepare_input_summary(text: str, intensity: str = "lite") -> str | None:
    """Scrub secrets, compress prose (preserve code/paths), then cap length.

    Returns None when ``block_patterns`` match (caller must skip the observation).
    Safe for hot-path callers: compression failures fall back to scrubbed text.
    """
    if not text:
        return ""
    scrubbed = scrub_text(text)
    if is_blocked_text(scrubbed):
        return None
    try:
        from .compress import compress

        body = compress(scrubbed, intensity)
    except Exception:
        body = scrubbed
    return truncate(body, MAX_PAYLOAD_LENGTH)
