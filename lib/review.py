"""Background session review - extracts conversational insights that hooks miss.

Reads recent observations from SQLite (session_id scoped), expands compressed
summaries, and produces enriched observations (event: "session_insight") that
feed into the normal extraction pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import PRISM_HOME, get_config, ensure_dirs
from .expand import expand
from .index import load_index
from .observation_summary import prepare_input_summary


def run_review(session_id: str, project_id: str, backend: str | None = None) -> dict:
    """Run a background review of the current session conversation.

    Returns {"insights": N, "session_id": str, "status": str}.
    """
    ensure_dirs(project_id)
    config = get_config()
    timeout = config.get("review_timeout", 60)

    from .storage import get_session_observations
    rows = get_session_observations(session_id, limit=50)
    if not rows:
        return {"insights": 0, "session_id": session_id, "status": "no_context"}

    # Free use-signal for INJECTED (prism.md) engrams: they are never MCP-queried (they're
    # already in context), so their only use-event is overlap between their trigger/domain/
    # tags and what this session actually did. Pure in-process FTS-style token overlap over
    # rows we already loaded -- $0 tokens, no LLM. Fires the same daily-idempotent impulse as
    # an MCP retrieval. Detects *relevance*, not *application* (confidence_plan.md §3 Q3).
    try:
        _credit_relevant_injected(rows, project_id, config)
    except Exception:
        pass  # a use-signal must never break the review

    obs_context = _build_obs_context(rows)
    triggers = _load_existing_triggers()
    prompt = _build_prompt(obs_context, triggers)
    if not prompt:
        return {"insights": 0, "session_id": session_id, "status": "no_context"}

    reviewer_prompt = _find_reviewer_prompt()
    if reviewer_prompt:
        prompt = reviewer_prompt + "\n\n---\n\n" + prompt

    from .agent_runner import run_agent

    try:
        result = run_agent(
            prompt,
            tier="fast",
            timeout=timeout,
            project_id=project_id,
            backend=backend,
        )
        if result.cli_missing:
            return {"insights": 0, "session_id": session_id, "status": "cli_not_found"}
        if result.timed_out:
            return {"insights": 0, "session_id": session_id, "status": "timeout"}
        if result.returncode != 0:
            return {"insights": 0, "session_id": session_id, "status": "agent_error"}
    except Exception:
        return {"insights": 0, "session_id": session_id, "status": "agent_error"}

    insights = _parse_review_output(result.stdout)
    if insights:
        _write_insights(insights, session_id, project_id)

    return {"insights": len(insights), "session_id": session_id, "status": "ok"}


_OVERLAP_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "use", "using", "used",
    "when", "then", "than", "your", "you", "via", "are", "was", "not", "but", "all", "any",
    "should", "must", "always", "never", "code", "file", "files", "project", "claude",
}


def _significant_terms(*texts) -> set:
    """Lowercased alphanumeric tokens >= 4 chars, minus generic stopwords.

    Used to compare an engram's trigger/domain/tags against session activity. Short and
    generic tokens are dropped so overlap reflects a shared *topic*, not shared English.
    """
    import re
    terms = set()
    for text in texts:
        if not text:
            continue
        for tok in re.findall(r"[A-Za-z0-9_]+", str(text).lower()):
            if len(tok) >= 4 and tok not in _OVERLAP_STOPWORDS:
                terms.add(tok)
    return terms


def _credit_relevant_injected(rows: list[dict], project_id: str, config: dict) -> int:
    """Fire a use-event for injected (push-lane) engrams whose domain was active this session.

    Overlap = distinct significant terms shared between the engram's trigger/domain/tags and
    the session's observation summaries. An engram clears the bar at `overlap_min_terms`
    matches (default 2) -- high enough to avoid crediting on a single common word. Crediting
    goes through reinforce_entries, which is daily-idempotent, so repeated background reviews
    in one session credit each engram at most once/day.

    Returns the number of engrams credited.
    """
    from .index import list_entries, reinforce_entries
    from .config import PUSH_KINDS

    min_terms = config.get("overlap_min_terms", 2)

    # Build the session's significant-term set once from the observation summaries.
    session_terms = _significant_terms(*[expand(r.get("input_summary", "")) for r in rows])
    if not session_terms:
        return 0

    # Injected engrams = the push lane: pinned, or kind in PUSH_KINDS (mirrors sync selection).
    injected = [
        e for e in list_entries(project_id=project_id)
        if e.get("pinned") or e.get("kind") in PUSH_KINDS
    ]

    applied = []
    for e in injected:
        eng_terms = _significant_terms(
            e.get("trigger", ""), e.get("domain", ""), " ".join(e.get("tags", []) or [])
        )
        if len(eng_terms & session_terms) >= min_terms:
            applied.append(e["id"])

    if applied:
        reinforce_entries(applied)
    return len(applied)


def _build_obs_context(rows: list[dict]) -> str:
    """Format observation rows as reviewer context, expanding compressed summaries."""
    lines = []
    for row in rows:
        summary = expand(row.get("input_summary", ""))
        event = row.get("event", "")
        tool = row.get("tool", "")
        lines.append(f"  {event}: {tool} -- {summary[:300]}")
    return "\n".join(lines)


def _load_existing_triggers() -> str:
    """Load existing triggers for dedup context."""
    index = load_index()
    entries_list = index.get("engrams", [])
    if not entries_list:
        return "(none)"

    lines = []
    for e in entries_list[:30]:
        lines.append(f"  - {e['id']}: {e.get('trigger', '')}")
    return "\n".join(lines)


def _find_reviewer_prompt() -> "str | None":
    """Find and read the reviewer agent prompt."""
    installed = PRISM_HOME / "agents" / "reviewer.md"
    if installed.exists():
        try:
            return installed.read_text()
        except OSError:
            pass

    repo = Path(__file__).parent.parent / "agents" / "reviewer.md"
    if repo.exists():
        try:
            return repo.read_text()
        except OSError:
            pass

    return None


def _build_prompt(obs_context: str, triggers: str) -> str:
    """Assemble the review prompt from session observations and existing triggers."""
    if not obs_context:
        return ""

    return "\n\n---\n\n".join([
        f"## Recent Session Observations\n\n{obs_context}",
        f"## Existing Knowledge Triggers (do not duplicate)\n\n{triggers}",
    ])


def _parse_review_output(output: str) -> list:
    """Parse Haiku's review output into insight dicts."""
    import re

    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", output, re.DOTALL)
    raw = json_match.group(1) if json_match else output.strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    valid = []
    for item in data:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary", "")
        if not summary:
            continue
        valid.append({
            "insight_type": item.get("insight_type", "unknown"),
            "summary": summary,
            "evidence": item.get("evidence", ""),
        })
    return valid


def _write_insights(insights: list, session_id: str, project_id: str) -> None:
    """Insert review insights as observations into SQLite."""
    from .storage import insert_observation, init_db, DB_PATH
    if not DB_PATH.exists():
        init_db(DB_PATH)
    for insight in insights:
        summary = prepare_input_summary(insight["summary"], compress=False)
        if summary is None:
            continue
        evidence_prepared = prepare_input_summary(insight.get("evidence", ""), compress=False)
        insert_observation(
            session_id=session_id,
            project_id=project_id,
            event="session_insight",
            tool="reviewer",
            source="session_review",
            input_summary=summary,
            insight_type=insight.get("insight_type"),
            evidence=(evidence_prepared or "")[:300],
        )
