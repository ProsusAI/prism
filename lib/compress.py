# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

import re
from typing import Literal

from .lexicon import abbreviations_for, articles_for, fillers_for, hedges_for, pleasantries_for
from .text_tokenize import Segment, tokenize

Intensity = Literal['lite', 'full']


def _remove_phrases(text: str, phrases: list[str]) -> str:
    if not phrases:
        return text
    # Sort longer phrases first so multi-word phrases match before single words.
    sorted_phrases = sorted(phrases, key=len, reverse=True)
    pattern = re.compile(
        r'\b(?:' + '|'.join(re.escape(p) for p in sorted_phrases) + r')\b',
        re.IGNORECASE,
    )
    return pattern.sub('', text)


def _match_case(source: str, target: str) -> str:
    if source == source.upper():
        return target.upper()
    if source[:1] and source[:1] == source[:1].upper():
        return target[:1].upper() + target[1:]
    return target


def _abbreviate(text: str, mapping: dict[str, str]) -> str:
    result = text
    for from_, to in mapping.items():
        pattern = re.compile(r'\b' + re.escape(from_) + r'\b', re.IGNORECASE)
        result = pattern.sub(lambda m, t=to: _match_case(m.group(0), t), result)
    return result


def _collapse_whitespace(text: str) -> str:
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' ?\n ?', '\n', text)
    text = re.sub(r' +([.,;:!?])', r'\1', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'^ +| +$', '', text, flags=re.MULTILINE)
    return text


def _compress_prose(text: str, intensity: str) -> str:
    # Preserve a single boundary space/newline so the seam with adjacent
    # preserved tokens (paths, inline code, URLs) isn't eaten by
    # _collapse_whitespace's per-line trim — "at /tmp/x" must not become
    # "at/tmp/x" when compressed.
    leading_m = re.match(r'^\s+', text)
    trailing_m = re.search(r'\s+$', text)
    leading = leading_m.group(0) if leading_m else ''
    trailing = trailing_m.group(0) if trailing_m else ''
    body = text[len(leading): len(text) - len(trailing) if trailing else None]
    if not body:
        return text
    out = body
    out = _remove_phrases(out, pleasantries_for(intensity))
    out = _remove_phrases(out, hedges_for(intensity))
    out = _remove_phrases(out, fillers_for(intensity))
    out = _remove_phrases(out, articles_for(intensity))
    out = _abbreviate(out, abbreviations_for(intensity))
    out = _collapse_whitespace(out)
    left_pad = '\n' if '\n' in leading else (' ' if leading else '')
    right_pad = '\n' if '\n' in trailing else (' ' if trailing else '')
    return f'{left_pad}{out}{right_pad}'


def compress(input_text: str, intensity: str = 'lite') -> str:
    """Compress prose segments while preserving code, URLs, paths, commands,
    version numbers, dates, identifiers, numbers, and headings verbatim."""
    segments: list[Segment] = tokenize(input_text)
    out: list[str] = []
    for seg in segments:
        if seg.preserved:
            out.append(seg.text)
        else:
            out.append(_compress_prose(seg.text, intensity))
    return re.sub(r'[ \t]+([.,;:!?])', r'\1', ''.join(out))
