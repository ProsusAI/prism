"""Prepare observation input_summary for SQLite: scrub, compress, truncate."""

from .scrub import MAX_PAYLOAD_LENGTH, is_blocked_text, scrub_text, truncate


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
        return truncate(scrubbed, MAX_PAYLOAD_LENGTH)
    try:
        from .compress import compress as _compress

        body = _compress(scrubbed, intensity)
    except Exception:
        body = scrubbed
    return truncate(body, MAX_PAYLOAD_LENGTH)
