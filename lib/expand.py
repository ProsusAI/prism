# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

import re

from .lexicon import expansions
from .text_tokenize import tokenize


def _match_case(source: str, target: str) -> str:
    if source == source.upper():
        return target.upper()
    if source[:1] and source[:1] == source[:1].upper():
        return target[:1].upper() + target[1:]
    return target


def expand(input_text: str) -> str:
    """Expand abbreviations back to their long form. Does not restore dropped
    filler words — compression of those is lossy by design. Technical tokens
    are preserved byte-for-byte because they are held out of the expansion
    pass by the tokenizer."""
    segments = tokenize(input_text)
    mapping = expansions()
    keys = sorted(mapping.keys(), key=len, reverse=True)
    if not keys:
        return input_text
    pattern = re.compile(
        r'\b(?:' + '|'.join(re.escape(k) for k in keys) + r')\b',
        re.IGNORECASE,
    )

    def replace(m: re.Match) -> str:
        key = m.group(0).lower()
        target = mapping.get(key)
        return _match_case(m.group(0), target) if target else m.group(0)

    return ''.join(
        seg.text if seg.preserved else pattern.sub(replace, seg.text)
        for seg in segments
    )
