"""Background session review - extracts conversational insights that hooks miss.

Reads the live session transcript and produces enriched observations
(event: "session_insight") that feed into the normal extraction pipeline.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import PRISM_HOME, get_config, get_observations_path, ensure_dirs
from .index import load_index
from .scrub import scrub_text

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
REVIEW_LOCK = PRISM_HOME / ".reviewing"
STALE_LOCK_SECONDS = 120


def run_review(session_id: str, project_id: str) -> dict:
    """Run a background review of the current session conversation.

    Returns {"insights": N, "session_id": str, "status": str}.
    """
    ensure_dirs(project_id)
    config = get_config()
    timeout = config.get("review_timeout", 60)

    # Acquire lock
    try:
        if REVIEW_LOCK.exists():
            age = time.time() - REVIEW_LOCK.stat().st_mtime
            if age <= STALE_LOCK_SECONDS:
                return {"insights": 0, "session_id": session_id, "status": "locked"}
            REVIEW_LOCK.unlink(missing_ok=True)

        fd = os.open(str(REVIEW_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return {"insights": 0, "session_id": session_id, "status": "locked"}

    try:
        # Find session transcript
        transcript_path = _find_session_transcript(session_id)
        conversation = ""
        if transcript_path:
            conversation = _extract_conversation(transcript_path, max_lines=50)

        # Read recent observations
        observations = _read_recent_observations(project_id, max_lines=20)

        # Read existing existing triggers for dedup
        triggers = _load_existing_triggers()

        # Assemble prompt
        prompt = _build_prompt(conversation, observations, triggers)
        if not prompt:
            return {"insights": 0, "session_id": session_id, "status": "no_context"}

        # Find reviewer agent prompt
        reviewer_prompt = _find_reviewer_prompt()
        if reviewer_prompt:
            prompt = reviewer_prompt + "\n\n---\n\n" + prompt

        # Run Haiku (no tools needed -- context is baked in)
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

        # Parse and write observations
        insights = _parse_review_output(result.stdout)
        if insights:
            _write_observations(insights, session_id, project_id)

        return {"insights": len(insights), "session_id": session_id, "status": "ok"}

    finally:
        REVIEW_LOCK.unlink(missing_ok=True)


def _find_session_transcript(session_id: str) -> "Path | None":
    """Find the live session JSONL file."""
    if not CLAUDE_PROJECTS_DIR.exists():
        return None

    # Primary: derive folder from cwd
    cwd = os.getcwd()
    folder_name = cwd.replace("/", "-")
    candidate = CLAUDE_PROJECTS_DIR / folder_name / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate

    # Fallback: glob for session ID across all project folders
    matches = list(CLAUDE_PROJECTS_DIR.glob(f"*/{session_id}.jsonl"))
    if matches:
        return matches[0]

    return None


def _extract_conversation(transcript_path: Path, max_lines: int = 50) -> str:
    """Extract filtered conversation text from session JSONL.

    Two passes:
    1. Scan the FULL transcript for correction-like user messages (preferences,
       corrections, pushback) -- these are high-signal and shouldn't be lost to windowing.
    2. Take the last N lines for recent conversational context.

    Skips tool_result content (the bulk of the file), attachments, thinking blocks.
    """
    try:
        with open(transcript_path) as f:
            all_lines = f.readlines()
    except OSError:
        return ""

    # --- Pass 1: Collect ALL user messages from full transcript ---
    # Don't filter with heuristics -- let Haiku decide what's a preference.
    # Just skip very short messages, IDE tags, and tool results.
    user_messages = []
    for line in all_lines:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") != "user":
            continue
        content = msg.get("message", {}).get("content", [])
        texts = []
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
        for text in texts:
            if not text or len(text) < 10 or len(text) > 500:
                continue
            lower = text.strip().lower()
            # Skip IDE-injected tags, JSON blobs, system messages
            if lower.startswith("<") or lower.startswith("{"):
                continue
            scrubbed = scrub_text(text)[:300]
            if scrubbed not in user_messages:
                user_messages.append(scrubbed)

    # --- Pass 2: Recent conversation window ---
    recent = all_lines[-max_lines:]
    parts = []
    for line in recent:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue  # Skip partial writes

        msg_type = msg.get("type")
        content = msg.get("message", {}).get("content", [])

        if msg_type == "user":
            if isinstance(content, str):
                text = scrub_text(content)
                if text and len(text) > 4:
                    parts.append(f"USER: {text[:500]}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = scrub_text(block.get("text", ""))
                        if text and len(text) > 4 and not text.strip().startswith("<"):
                            parts.append(f"USER: {text[:500]}")

        elif msg_type == "assistant":
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type")

                    if block_type == "text":
                        text = scrub_text(block.get("text", ""))
                        if text:
                            parts.append(f"ASSISTANT: {text[:500]}")

                    elif block_type == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_input = block.get("input", {})
                        summary = ""
                        if isinstance(tool_input, dict):
                            # Just key info, not full content
                            summary = json.dumps(tool_input, ensure_ascii=False)[:100]
                        parts.append(f"ASSISTANT [tool: {tool_name}]: {summary}")

    # Prepend all user messages from the session so Haiku can identify preferences
    result = ""
    if user_messages:
        result += "## All User Messages (from full session -- identify preferences, corrections, expectations)\n\n"
        for m in user_messages[:30]:  # Cap to keep prompt reasonable
            result += f"- {m}\n"
        result += "\n## Recent Conversation\n\n"
    result += "\n".join(parts)
    return result


def _read_recent_observations(project_id: str, max_lines: int = 20) -> str:
    """Read the last N lines from observations.jsonl."""
    obs_path = get_observations_path(project_id)
    if not obs_path.exists():
        return ""

    try:
        with open(obs_path) as f:
            all_lines = f.readlines()
    except OSError:
        return ""

    recent = all_lines[-max_lines:]
    summaries = []
    for line in recent:
        try:
            obs = json.loads(line.strip())
            event = obs.get("event", "")
            tool = obs.get("tool", "")
            summary = obs.get("input_summary", "")[:200]
            summaries.append(f"  {event}: {tool} -- {summary}")
        except json.JSONDecodeError:
            continue

    return "\n".join(summaries)


def _load_existing_triggers() -> str:
    """Load existing existing triggers for dedup context."""
    index = load_index()
    entries_list = index.get("engrams", [])
    if not entries_list:
        return "(none)"

    lines = []
    for e in entries_list[:30]:  # Cap to keep prompt small
        trigger = e.get("trigger", "")
        lines.append(f"  - {e['id']}: {trigger}")
    return "\n".join(lines)


def _find_reviewer_prompt() -> "str | None":
    """Find and read the reviewer agent prompt."""
    # Installed location
    installed = PRISM_HOME / "agents" / "reviewer.md"
    if installed.exists():
        try:
            return installed.read_text()
        except OSError:
            pass

    # Repo-relative (development)
    repo = Path(__file__).parent.parent / "agents" / "reviewer.md"
    if repo.exists():
        try:
            return repo.read_text()
        except OSError:
            pass

    return None


def _build_prompt(conversation: str, observations: str, triggers: str) -> str:
    """Assemble the full review prompt with context."""
    if not conversation and not observations:
        return ""

    sections = []

    if conversation:
        sections.append(f"## Recent Conversation\n\n{conversation}")

    if observations:
        sections.append(f"## Recent Tool Events (already captured by hooks)\n\n{observations}")

    sections.append(f"## Existing Knowledge Triggers (do not duplicate)\n\n{triggers}")

    return "\n\n---\n\n".join(sections)


def _parse_review_output(output: str) -> list:
    """Parse Haiku's review output into observation dicts."""
    import re

    # Try ```json fenced block first
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", output, re.DOTALL)
    raw = None
    if json_match:
        raw = json_match.group(1)
    else:
        # Try parsing whole output
        raw = output.strip()

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


def _write_observations(insights: list, session_id: str, project_id: str) -> None:
    """Append enriched observations to observations.jsonl."""
    obs_path = get_observations_path(project_id)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(obs_path, "a") as f:
        for insight in insights:
            obs = {
                "timestamp": timestamp,
                "event": "session_insight",
                "tool": "reviewer",
                "input_summary": scrub_text(insight["summary"]),
                "insight_type": insight["insight_type"],
                "evidence": scrub_text(insight.get("evidence", ""))[:300],
                "session": session_id,
                "project_id": project_id,
                "source": "session_review",
            }
            f.write(json.dumps(obs, ensure_ascii=False) + "\n")
