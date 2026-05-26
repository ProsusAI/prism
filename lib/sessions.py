"""Analyze existing Claude Code session transcripts to bootstrap Prism observations."""

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .config import PRISM_HOME, ensure_dirs
from .storage import insert_observations_batch, init_db, DB_PATH, delete_by_session_ids
from .observation_summary import prepare_input_summary


def _append_observation(observations: list, *, raw_summary: str, **fields) -> None:
    """Append an observation unless block_patterns reject the summary text."""
    summary = prepare_input_summary(raw_summary)
    if summary is None:
        return
    observations.append({**fields, "input_summary": summary})


CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CURSOR_PROJECTS_DIR = Path.home() / ".cursor" / "projects"
TRACKER_PATH = PRISM_HOME / "analyzed-sessions.json"

# Heuristic: user text that looks like a correction or preference
# Matched as whole words, any position.
import re as _re
_CORRECTION_KEYWORDS = (
    "no", "don't", "dont", "stop", "actually", "instead", "wait",
    "always", "never", "prefer", "wrong", "keep", "reduce", "use",
    "make sure", "instead of", "don't use", "do not use", "should use", "not that",
    "i want",
)
_CORRECTION_RE = _re.compile(
    r"\b(" + "|".join(_re.escape(k) for k in _CORRECTION_KEYWORDS) + r")\b",
    _re.IGNORECASE,
)


def is_correction_like(text: str) -> bool:
    """Heuristic filter: does this user message look like guidance/correction?"""
    if not text or len(text) < 5 or len(text) > 300:
        return False
    if text.lstrip().startswith("<"):
        return False
    return bool(_CORRECTION_RE.search(text))


def resolve_project_id_from_cwd(cwd: str, cache: dict) -> str:
    """Resolve a cwd path to a prism project_id using git."""
    if cwd in cache:
        return cache[cwd]

    project_id = "global"
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            project_id = hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:12]
        else:
            result = subprocess.run(
                ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                project_id = hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:12]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    cache[cwd] = project_id
    return project_id


def _load_tracker() -> dict:
    """Load the analyzed-sessions tracker."""
    if TRACKER_PATH.exists():
        try:
            with open(TRACKER_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"sessions": {}}


def _save_tracker(tracker: dict) -> None:
    """Save the analyzed-sessions tracker."""
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKER_PATH, "w") as f:
        json.dump(tracker, f, indent=2)
        f.write("\n")


def _should_analyze(session_id: str, file_size: int, tracker: dict) -> bool:
    """Check if a session needs (re-)analysis."""
    entry = tracker.get("sessions", {}).get(session_id)
    if entry is None:
        return True
    # Re-analyze if file grew
    return entry.get("file_size", 0) != file_size


def _session_date(jsonl_path_str: str) -> "date":
    """Extract approximate date from session file modification time."""
    from datetime import date as date_type
    try:
        mtime = os.path.getmtime(jsonl_path_str)
        return date_type.fromtimestamp(mtime)
    except OSError:
        return date_type.min


def list_sessions(
    project_filter: "str | None" = None,
    since_date: "str | None" = None,
    last_n: "int | None" = None,
) -> list[dict]:
    """List available sessions with metadata.

    Returns list of dicts: {path, session_id, folder_name, size, cwd, line_count}.
    If project_filter is set, only sessions whose cwd resolves to that project_id.
    """
    if not CLAUDE_PROJECTS_DIR.exists():
        return []

    sessions = []
    cwd_cache: dict[str, str] = {}

    for folder in sorted(CLAUDE_PROJECTS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        for jsonl_file in folder.glob("*.jsonl"):
            session_id = jsonl_file.stem
            size = jsonl_file.stat().st_size
            if size == 0:
                continue

            # Read first user message to get cwd
            cwd = _extract_cwd(jsonl_file)
            if not cwd:
                # Derive from folder name: -Users-gaurav-codes-prism -> /Users/gaurav/codes/prism
                cwd = folder.name.replace("-", "/")
                if not cwd.startswith("/"):
                    cwd = "/" + cwd

            pid = resolve_project_id_from_cwd(cwd, cwd_cache) if cwd else "global"

            if project_filter and pid != project_filter:
                continue

            # Count lines (approximate message count)
            line_count = 0
            try:
                with open(jsonl_file) as f:
                    for _ in f:
                        line_count += 1
            except OSError:
                continue

            sessions.append({
                "path": str(jsonl_file),
                "session_id": session_id,
                "folder_name": folder.name,
                "size": size,
                "cwd": cwd,
                "project_id": pid,
                "line_count": line_count,
                "ide": "claude_code",
            })

    # Filter by date if --since provided
    if since_date:
        try:
            from datetime import date as date_type
            cutoff = date_type.fromisoformat(since_date)
            sessions = [s for s in sessions if _session_date(s["path"]) >= cutoff]
        except ValueError:
            pass  # Invalid date format, skip filter

    # Sort by mtime ascending so --last N yields the N most recently modified sessions
    sessions.sort(key=lambda s: os.path.getmtime(s["path"]))

    # Limit to last N if --last provided
    if last_n is not None and last_n > 0:
        sessions = sessions[-last_n:]

    return sessions


def list_cursor_sessions(
    project_filter: "str | None" = None,
    since_date: "str | None" = None,
    last_n: "int | None" = None,
) -> list[dict]:
    """List available Cursor IDE sessions with metadata.

    Cursor stores transcripts under
    ~/.cursor/projects/<sanitized-path>/agent-transcripts/<id>.jsonl.
    The cwd is reconstructed from the sanitized folder name.
    """
    if not CURSOR_PROJECTS_DIR.exists():
        return []

    sessions = []
    cwd_cache: dict[str, str] = {}

    for folder in sorted(CURSOR_PROJECTS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        transcripts_dir = folder / "agent-transcripts"
        if not transcripts_dir.is_dir():
            continue
        for jsonl_file in transcripts_dir.glob("*.jsonl"):
            session_id = jsonl_file.stem
            size = jsonl_file.stat().st_size
            if size == 0:
                continue

            # Cursor folder names are project paths sanitized with non-alphanumerics
            # replaced by hyphens and leading hyphens trimmed. Reconstruct a cwd.
            cwd = "/" + folder.name.replace("-", "/").lstrip("/")
            pid = resolve_project_id_from_cwd(cwd, cwd_cache) if cwd else "global"

            if project_filter and pid != project_filter:
                continue

            line_count = 0
            try:
                with open(jsonl_file) as f:
                    for _ in f:
                        line_count += 1
            except OSError:
                continue

            sessions.append({
                "path": str(jsonl_file),
                "session_id": session_id,
                "folder_name": folder.name,
                "size": size,
                "cwd": cwd,
                "project_id": pid,
                "line_count": line_count,
                "ide": "cursor",
            })

    if since_date:
        try:
            from datetime import date as date_type
            cutoff = date_type.fromisoformat(since_date)
            sessions = [s for s in sessions if _session_date(s["path"]) >= cutoff]
        except ValueError:
            pass

    sessions.sort(key=lambda s: os.path.getmtime(s["path"]))

    if last_n is not None and last_n > 0:
        sessions = sessions[-last_n:]

    return sessions


def list_all_sessions(
    project_filter: "str | None" = None,
    since_date: "str | None" = None,
    last_n: "int | None" = None,
) -> list[dict]:
    """List Claude Code and Cursor sessions, deduplicated by session_id."""
    combined = list_sessions(
        project_filter=project_filter,
        since_date=since_date,
        last_n=None,
    ) + list_cursor_sessions(
        project_filter=project_filter,
        since_date=since_date,
        last_n=None,
    )

    by_id: dict[str, dict] = {}
    for sess in combined:
        session_id = sess["session_id"]
        current = by_id.get(session_id)
        if current is None or os.path.getmtime(sess["path"]) > os.path.getmtime(current["path"]):
            by_id[session_id] = sess

    sessions = list(by_id.values())
    sessions.sort(key=lambda s: os.path.getmtime(s["path"]))

    if last_n is not None and last_n > 0:
        sessions = sessions[-last_n:]

    return sessions


def _extract_cwd(jsonl_path: Path) -> str:
    """Extract cwd from the first user message in a session file."""
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    cwd = d.get("cwd")
                    if cwd:
                        return cwd
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return ""


def analyze_session(jsonl_path: Path, project_id: str, dry_run: bool = False) -> dict:
    """Analyze a single session file and write observations.

    Returns: {session_id, observations_written, tool_calls, rejections, corrections}
    """
    session_id = Path(jsonl_path).stem
    tool_id_map: dict[str, str] = {}  # tool_use_id -> tool_name
    observations: list[dict] = []

    with open(jsonl_path) as f:
        for line in f:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            timestamp = msg.get("timestamp", "")
            cwd = msg.get("cwd", "")
            sid = msg.get("sessionId", session_id)

            if msg_type == "assistant":
                # Extract tool_use blocks
                content = msg.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        tool_id = block.get("id", "")
                        tool_input = block.get("input", {})

                        if tool_id and tool_name:
                            tool_id_map[tool_id] = tool_name

                        input_summary = ""
                        if isinstance(tool_input, dict):
                            input_summary = json.dumps(tool_input, ensure_ascii=False)
                        elif isinstance(tool_input, str):
                            input_summary = tool_input

                        _append_observation(
                            observations,
                            raw_summary=input_summary,
                            timestamp=timestamp,
                            event="tool_start",
                            tool=tool_name,
                            session=sid,
                            project_id=project_id,
                            source="session_import",
                        )

            elif msg_type == "user":
                content = msg.get("message", {}).get("content", [])

                # toolUseResult is IDE metadata present on every user message in modern
                # Claude Code sessions — only emit an observation when it's an actual
                # Agent subagent result (dict with a "prompt" key, or an error string).
                # Never continue here: message.content holds the real tool_result blocks.
                tool_result = msg.get("toolUseResult")
                if isinstance(tool_result, str) and tool_result:
                    is_err = "error" in tool_result.lower()
                    _append_observation(
                        observations,
                        raw_summary=tool_result,
                        timestamp=timestamp,
                        event="tool_rejected" if is_err else "tool_end",
                        tool="unknown",
                        session=sid,
                        project_id=project_id,
                        source="session_import",
                    )
                elif isinstance(tool_result, dict) and tool_result.get("prompt"):
                    status = tool_result.get("status", "")
                    event = "tool_rejected" if status == "error" else "tool_end"
                    _append_observation(
                        observations,
                        raw_summary=str(tool_result["prompt"]),
                        timestamp=timestamp,
                        event=event,
                        tool="Agent",
                        session=sid,
                        project_id=project_id,
                        source="session_import",
                    )

                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue

                        if block.get("type") == "tool_result":
                            tool_use_id = block.get("tool_use_id", "")
                            tool_name = tool_id_map.get(tool_use_id, "unknown")
                            is_error = block.get("is_error", False)
                            event = "tool_rejected" if is_error else "tool_end"

                            result_content = block.get("content", "")
                            if isinstance(result_content, list):
                                # Extract text from content blocks
                                texts = [b.get("text", "") for b in result_content
                                         if isinstance(b, dict) and b.get("type") == "text"]
                                result_content = " ".join(texts)

                            _append_observation(
                                observations,
                                raw_summary=str(result_content),
                                timestamp=timestamp,
                                event=event,
                                tool=tool_name,
                                session=sid,
                                project_id=project_id,
                                source="session_import",
                            )

                        elif block.get("type") == "text":
                            text = block.get("text", "")
                            if is_correction_like(text):
                                _append_observation(
                                    observations,
                                    raw_summary=text,
                                    timestamp=timestamp,
                                    event="user_guidance",
                                    tool="user",
                                    session=sid,
                                    project_id=project_id,
                                    source="session_import",
                                )

                elif isinstance(content, str) and is_correction_like(content):
                    _append_observation(
                        observations,
                        raw_summary=content,
                        timestamp=timestamp,
                        event="user_guidance",
                        tool="user",
                        session=sid,
                        project_id=project_id,
                        source="session_import",
                    )

    stats = {
        "session_id": session_id,
        "observations_written": len(observations),
        "tool_calls": sum(1 for o in observations if o["event"] == "tool_start"),
        "rejections": sum(1 for o in observations if o["event"] == "tool_rejected"),
        "corrections": sum(1 for o in observations if o["event"] == "user_guidance"),
    }

    if not dry_run and observations:
        ensure_dirs(project_id)
        if not DB_PATH.exists():
            init_db(DB_PATH)
        insert_observations_batch(observations)

    return stats


def analyze_all_sessions(
    project_filter: "str | None" = None,
    all_projects: bool = False,
    dry_run: bool = False,
    since_date: "str | None" = None,
    last_n: "int | None" = None,
    force: bool = False,
    source: str = "all",
) -> dict:
    """Analyze sessions and write observations.

    Args:
        project_filter: Only analyze sessions for this project_id (default: auto-detect current).
        all_projects: Analyze all projects regardless of filter.
        dry_run: Don't write observations, just report what would happen.
        source: Session source to analyze: "claude", "cursor", or "all".

    Returns: {processed, skipped, total_observations, by_project: {pid: {sessions, observations}}}
    """
    if not all_projects and not project_filter:
        from .project import detect_project_id
        project_filter = detect_project_id()

    tracker = _load_tracker()
    if source == "claude":
        list_func = list_sessions
    elif source == "cursor":
        list_func = list_cursor_sessions
    else:
        list_func = list_all_sessions

    sessions = list_func(
        project_filter=None if all_projects else project_filter,
        since_date=since_date,
        last_n=last_n,
    )

    # --force: delete existing observations for sessions about to be re-processed
    # so re-runs don't stack duplicates.
    if force and not dry_run:
        force_ids = list({s["session_id"] for s in sessions})
        delete_by_session_ids(force_ids)

    processed = 0
    skipped = 0
    total_obs = 0
    by_project: dict[str, dict] = {}

    for sess in sessions:
        session_id = sess["session_id"]
        file_size = sess["size"]
        pid = sess["project_id"]

        if not force and not _should_analyze(session_id, file_size, tracker):
            skipped += 1
            continue

        stats = analyze_session(Path(sess["path"]), pid, dry_run=dry_run)
        processed += 1
        total_obs += stats["observations_written"]

        if pid not in by_project:
            by_project[pid] = {"sessions": 0, "observations": 0, "name": _project_name(sess["cwd"])}
        by_project[pid]["sessions"] += 1
        by_project[pid]["observations"] += stats["observations_written"]

        # Print per-session detail
        parts = []
        if stats["tool_calls"]:
            parts.append(f"{stats['tool_calls']} tool calls")
        if stats["rejections"]:
            parts.append(f"{stats['rejections']} rejections")
        if stats["corrections"]:
            parts.append(f"{stats['corrections']} user corrections")
        detail = ", ".join(parts) if parts else "no events"
        print(f"  {session_id[:12]}... {detail} -> {stats['observations_written']} observations")

        # Update tracker
        if not dry_run:
            tracker.setdefault("sessions", {})[session_id] = {
                "project_id": pid,
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "observations_written": stats["observations_written"],
                "file_size": file_size,
            }

    if not dry_run and processed > 0:
        _save_tracker(tracker)

    return {
        "processed": processed,
        "skipped": skipped,
        "total_observations": total_obs,
        "by_project": by_project,
    }


def _project_name(cwd: str) -> str:
    """Extract a short project name from cwd."""
    if cwd:
        return os.path.basename(cwd.rstrip("/"))
    return "unknown"
