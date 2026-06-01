from __future__ import annotations

import json
from pathlib import Path

_DATA: dict | None = None


def _load() -> dict:
    global _DATA
    if _DATA is None:
        _DATA = json.loads((Path(__file__).parent / 'lexicon.json').read_text())
    return _DATA


def fillers_for(intensity: str) -> list[str]:
    return _load()['fillers'].get(intensity, [])


def articles_for(intensity: str) -> list[str]:
    return _load()['articles'].get(intensity, [])


def hedges_for(intensity: str) -> list[str]:
    return _load()['hedges'].get(intensity, [])


def pleasantries_for(intensity: str) -> list[str]:
    return _load()['pleasantries'].get(intensity, [])


def abbreviations_for(intensity: str) -> dict[str, str]:
    return _load()['abbreviations'].get(intensity, {})


def expansions() -> dict[str, str]:
    return _load()['expansions']
