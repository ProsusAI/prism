"""Background session review - extracts conversational insights that hooks miss.

Reads recent observations from SQLite (session_id scoped), expands compressed
summaries, and produces enriched observations (event: "session_insight") that
feed into the normal extraction pipeline.
"""

import json
import subprocess
import sys
from pathlib import Path

from .config import PRISM_HOME, get_config, ensure_dirs
from .expand import expand
from .index import load_index
from .observation_summary import prepare_input_summary


def run_review(session_id: str, project_id: str) -> dict:
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

    obs_context = _build_obs_context(rows)
    triggers = _load_existing_triggers()
    prompt = _build_prompt(obs_context, triggers)
    if not prompt:
        return {"insights": 0, "session_id": session_id, "status": "no_context"}

    reviewer_prompt = _find_reviewer_prompt()
    if reviewer_prompt:
        prompt = reviewer_prompt + "\n\n---\n\n" + prompt

    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "haiku", "-p", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return {"insights": 0, "session_id": session_id, "status": "haiku_error"}
    except FileNotFoundError:
        return {"insights": 0, "session_id": session_id, "status": "cli_not_found"}
    except subprocess.TimeoutExpired:
        return {"insights": 0, "session_id": session_id, "status": "timeout"}

    insights = _parse_review_output(result.stdout)
    if insights:
        _write_insights(insights, session_id, project_id)

    return {"insights": len(insights), "session_id": session_id, "status": "ok"}


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
        summary = prepare_input_summary(insight["summary"])
        if summary is None:
            continue
        evidence_prepared = prepare_input_summary(insight.get("evidence", ""))
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
