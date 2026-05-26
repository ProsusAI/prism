import re
from dataclasses import dataclass
from typing import Literal

SegmentKind = Literal[
    'fence', 'inline-code', 'url', 'path', 'command',
    'version', 'date', 'number', 'identifier', 'heading', 'prose', 'newline',
]


@dataclass
class Segment:
    kind: str
    text: str
    preserved: bool


@dataclass
class _RulePattern:
    kind: str
    priority: int
    pattern: re.Pattern


@dataclass
class _Span:
    start: int
    end: int
    kind: str
    priority: int


# Priority (higher wins on overlap): fence > inline-code > url > heading >
# path > date > version > number > identifier. Headings are line-scoped.
_RULES: list[_RulePattern] = [
    _RulePattern('fence', 100, re.compile(r'```[\s\S]*?```|~~~[\s\S]*?~~~')),
    _RulePattern('inline-code', 90, re.compile(r'`[^`\n]+`')),
    _RulePattern('url', 80, re.compile(r'\bhttps?://[^\s)\]]+')),
    _RulePattern('heading', 70, re.compile(r'^#{1,6}\s[^\n]*$', re.MULTILINE)),
    _RulePattern('path', 60, re.compile(
        r'(?:(?:\.{1,2})?/[A-Za-z0-9._\-/]+|~/[A-Za-z0-9._\-/]+|[A-Z]:\\[A-Za-z0-9._\-\\]+)'
    )),
    _RulePattern('date', 50, re.compile(
        r'\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?\b'
    )),
    _RulePattern('version', 40, re.compile(
        r'\bv?\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?\b'
    )),
    _RulePattern('number', 30, re.compile(r'\b\d+(?:\.\d+)?\b')),
    _RulePattern('identifier', 20, re.compile(
        r'\b[A-Za-z_][A-Za-z0-9_]*[-_][A-Za-z0-9_\-]+\b|\b[a-z]+[A-Z][A-Za-z0-9]*\b'
    )),
]


def tokenize(input_text: str) -> list[Segment]:
    """Single-pass tokenizer. Collects all rule matches across the input,
    resolves overlaps by priority (with earlier-start as tie-breaker, then
    wider span), and emits a non-overlapping list of preserved + prose
    segments."""
    spans: list[_Span] = []
    for rule in _RULES:
        for m in rule.pattern.finditer(input_text):
            if m.group(0):
                spans.append(_Span(
                    start=m.start(),
                    end=m.end(),
                    kind=rule.kind,
                    priority=rule.priority,
                ))

    # Resolve overlaps greedily: start ASC, priority DESC, end DESC (wider first).
    spans.sort(key=lambda s: (s.start, -s.priority, -s.end))

    resolved: list[_Span] = []
    cursor = 0
    for s in spans:
        if s.start < cursor:
            continue
        resolved.append(s)
        cursor = s.end

    resolved.sort(key=lambda s: s.start)

    out: list[Segment] = []
    pos = 0
    for s in resolved:
        if s.start > pos:
            out.append(Segment(kind='prose', text=input_text[pos:s.start], preserved=False))
        out.append(Segment(kind=s.kind, text=input_text[s.start:s.end], preserved=True))
        pos = s.end
    if pos < len(input_text):
        out.append(Segment(kind='prose', text=input_text[pos:], preserved=False))

    return out


def detokenize(segments: list[Segment]) -> str:
    return ''.join(s.text for s in segments)
