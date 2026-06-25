# Copyright © 2026 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Extraction pipeline - Phase 1 (Haiku) and Phase 2 (Sonnet)."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    PRISM_HOME,
    get_candidates_dir,
    get_config,
    get_engrams_dir,
    get_project_dir,
    ensure_dirs,
)
from .storage import count_active, get_active, mark_extracted, purge_old
from .index import (
    add_entry,
    build_index_entry,
    get_entry,
    load_index,
    merge_file_entry_with_index,
    remove_entry,
)


def _find_agent_prompt(filename: str):
    """Find an agent prompt file. Checks ~/.prism/agents/ first, then repo dir."""
    # Installed location
    installed = PRISM_HOME / "agents" / filename
    if installed.exists():
        return installed
    # Repo-relative location (for development / before install)
    repo = Path(__file__).parent.parent / "agents" / filename
    if repo.exists():
        return repo
    return None


def _batch_ids_path(project_id: str) -> Path:
    """Sidecar listing observation row ids exported for the current extraction."""
    return get_project_dir(project_id) / ".extract_obs_ids.json"


def _save_batch_ids(project_id: str, observation_ids: list[int]) -> None:
    path = _batch_ids_path(project_id)
    path.write_text(json.dumps({"observation_ids": observation_ids}) + "\n")


def _load_batch_ids(project_id: str) -> list[int] | None:
    path = _batch_ids_path(project_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        ids = data.get("observation_ids")
        if isinstance(ids, list) and all(isinstance(i, int) for i in ids):
            return ids
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return None


def _clear_batch_ids(project_id: str) -> None:
    try:
        _batch_ids_path(project_id).unlink(missing_ok=True)
    except OSError:
        pass


def run_extraction(project_id: str, backend: str | None = None) -> dict:
    """Run the full extraction + validation pipeline.

    Returns {"extracted": N, "approved": N, "rejected": N, "modified": N}.
    """
    ensure_dirs(project_id)
    lock = PRISM_HOME / ".extracting"
    batch_ids: list[int] | None = None

    try:
        # Clear stale lock (> 10 minutes old = crashed extraction)
        if lock.exists():
            age_seconds = time.time() - lock.stat().st_mtime
            if age_seconds > 600:
                print(f"Removing stale lock ({int(age_seconds)}s old).")
                lock.unlink(missing_ok=True)

        # Atomic lock - fails if already held (prevents concurrent extractions)
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            print("Extraction already in progress.")
            return {"extracted": 0, "approved": 0, "rejected": 0, "modified": 0}

        # Phase 1: Haiku extracts candidates
        # Skip if candidates already exist from a previous interrupted run
        existing_candidates = list(get_candidates_dir(project_id).glob("*.md"))
        if existing_candidates:
            print(f"Resuming: {len(existing_candidates)} candidates from previous run, skipping phase 1.")
            n_candidates = len(existing_candidates)
            batch_ids = _load_batch_ids(project_id)
            if batch_ids is None:
                print(
                    "Warning: no extraction batch file; rotation will mark "
                    "current active observations only if validation completes."
                )
        else:
            n_candidates, batch_ids = _phase1_extract(project_id, backend=backend)
            if n_candidates < 0:
                _clear_batch_ids(project_id)
                # Hard failure (subprocess error, CLI missing, timeout) — preserve
                # observations so the next extraction cycle can retry them.
                return {"extracted": 0, "approved": 0, "rejected": 0, "modified": 0}
            if n_candidates == 0:
                # Haiku ran but found nothing worth capturing — mark batch as processed.
                if batch_ids:
                    _rotate_observations(project_id, batch_ids)
                return {"extracted": 0, "approved": 0, "rejected": 0, "modified": 0}

        # Phase 2: Sonnet validates candidates
        snapshot = _take_validation_snapshot(project_id)
        results = _phase2_validate(project_id, snapshot, backend=backend)
        results["extracted"] = n_candidates

        rotate = _should_rotate_observations(results, n_candidates, project_id)
        if results.get("parse_failed"):
            print(
                "Warning: validation JSON could not be parsed; "
                "observations kept unless all candidates were resolved on disk."
            )
        _apply_validation_results(
            project_id, results, rotate=rotate, observation_ids=batch_ids,
        )

        # Post-extraction: sync .claude/prism.md with new engrams (EXT-05, CTX-04)
        try:
            from .sync import sync_claude_code
            sync_claude_code(project_id)
        except Exception:
            pass  # Don't let sync failure break extraction

        return results
    finally:
        lock.unlink(missing_ok=True)
        try:
            from .trigger import clear_extract_pending
            clear_extract_pending(project_id)
        except Exception:
            pass


def _normalize_obs(obs: dict) -> dict:
    """Remap SQLite column names to human-readable keys for the Haiku temp file."""
    summary = obs.get("input_summary", "")
    try:
        from .expand import expand
        summary = expand(summary)
    except Exception:
        pass
    return {
        "timestamp": datetime.fromtimestamp(obs["ts"], tz=timezone.utc).isoformat()
                     if obs.get("ts") else "",
        "session": obs.get("session_id", ""),
        "event": obs.get("event", ""),
        "tool": obs.get("tool", ""),
        "input_summary": summary,
        "project_id": obs.get("project_id", ""),
        "source": obs.get("source", ""),
        "insight_type": obs.get("insight_type"),
        "evidence": obs.get("evidence"),
    }


def _phase1_extract(project_id: str, backend: str | None = None) -> tuple[int, list[int] | None]:
    """Run Haiku extraction on observations.

    Returns (candidate_count, batch_observation_ids). ``batch_observation_ids``
  is the set exported to Haiku; rotation must only mark these rows.
    """
    import tempfile

    obs_count = count_active(project_id)
    if obs_count == 0:
        print("No observations to process.")
        return 0, None

    candidates_dir = get_candidates_dir(project_id)
    index_path = PRISM_HOME / "index.json"
    extractor_prompt_path = _find_agent_prompt("extractor.md")

    if not extractor_prompt_path:
        print("Error: extractor prompt not found. Run ./install.sh to set up.")
        return -1, None

    config = get_config()
    threshold = config.get("extract_threshold", 15)
    print(f"Found {obs_count} observations (threshold: {threshold})")

    # Export active observations to a temp JSONL file for Haiku to read
    observations = get_active(project_id)
    batch_ids = [int(obs["id"]) for obs in observations if obs.get("id") is not None]
    _save_batch_ids(project_id, batch_ids)

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".jsonl", prefix="prism_obs_")
    observations_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w") as tmp:
            for obs in observations:
                tmp.write(json.dumps(_normalize_obs(obs)) + "\n")

        # Build the prompt for Haiku
        prompt = f"""Read the extractor instructions at {extractor_prompt_path}.
Analyze the observations at {observations_path}.
Current knowledge index: {index_path}.
Write candidate files to {candidates_dir}/. Project ID: {project_id}.
No output text. Write files only.
"""

        from .agent_runner import cli_missing_message, failure_message, run_agent

        result = run_agent(
            prompt,
            tier="fast",
            timeout=300,
            write_files=True,
            project_id=project_id,
            backend=backend,
        )
        if result.cli_missing:
            print(cli_missing_message(result.backend))
            _log_extract_error(
                stage="phase1_subprocess",
                reason=f"{result.backend} CLI not found",
            )
            _clear_batch_ids(project_id)
            return -1, None
        if result.timed_out:
            print("Extraction timed out (300s limit).")
            _log_extract_error(stage="phase1_subprocess", reason="timeout after 300s")
            _clear_batch_ids(project_id)
            return -1, None
        if result.returncode != 0:
            msg = failure_message(result)
            print(f"Extraction failed: {msg}")
            _log_extract_error(
                stage="phase1_subprocess",
                reason=f"returncode={result.returncode} backend={result.backend}",
                raw_output=msg,
            )
            _clear_batch_ids(project_id)
            return -1, None
    finally:
        observations_path.unlink(missing_ok=True)

    # Count candidates created
    candidates = list(candidates_dir.glob("*.md"))
    print(f"Extraction complete: {len(candidates)} candidates created")
    return len(candidates), batch_ids


def _take_validation_snapshot(project_id: str) -> dict:
    """Capture engram/candidate filenames before phase 2 file operations."""
    engrams_dir = get_engrams_dir(project_id)
    candidates_dir = get_candidates_dir(project_id)
    return {
        "engrams_before": {p.name for p in engrams_dir.glob("*.md")},
        "candidates_before": {p.name for p in candidates_dir.glob("*.md")},
    }


def _phase2_validate(project_id: str, snapshot: dict, backend: str | None = None) -> dict:
    """Run Sonnet validation on candidates. Returns results dict."""
    candidates_dir = get_candidates_dir(project_id)
    candidates = list(candidates_dir.glob("*.md"))
    if not candidates:
        return {"approved": 0, "rejected": 0, "modified": 0, "decisions": []}

    index_path = PRISM_HOME / "index.json"
    constitution_path = PRISM_HOME / "constitution.md"
    validator_prompt_path = _find_agent_prompt("validator.md")

    if not validator_prompt_path:
        print("Error: validator prompt not found. Run ./install.sh to set up.")
        return {"approved": 0, "rejected": 0, "modified": 0}

    if not constitution_path.exists():
        print(f"Warning: constitution not found at {constitution_path}")

    # Build the prompt for Sonnet
    candidate_list = "\n".join(f"  - {c.name}" for c in candidates)
    n_candidates = len(candidates)
    engrams_dir = get_engrams_dir(project_id)
    prompt = f"""Read the validator instructions at {validator_prompt_path}.
Read the constitution at {constitution_path}.
Read the knowledge index at {index_path}.

Review each candidate in {candidates_dir}/:
{candidate_list}

For each candidate: evaluate all 5 gates, then perform file operations:
- APPROVED → move to {engrams_dir}/
- REJECTED → delete from candidates/
- MODIFIED → apply changes, then move to {engrams_dir}/

CRITICAL OUTPUT REQUIREMENT: After ALL file operations, your response MUST end with ONLY a single ```json fenced block. Do NOT write prose, markdown tables, or summaries — any text outside the JSON block will cause a parse failure. The JSON block must be the last thing in your response.

Exactly {n_candidates} elements — one per candidate, no omissions.
`gates` contains only failed gates: {{"gate_name": "reason"}}. Omit passing gates.

```json
[{{"candidate_id": "...", "decision": "APPROVED|REJECTED|MODIFIED", "gates": {{}}, "deprecates": []}}]
```
"""

    from .agent_runner import cli_missing_message, failure_message, run_agent

    result = run_agent(
        prompt,
        tier="strong",
        timeout=300,
        write_files=True,
        project_id=project_id,
        backend=backend,
    )
    if result.cli_missing:
        print(cli_missing_message(result.backend))
        _log_extract_error(stage="phase2_subprocess", reason=f"{result.backend} CLI not found")
        return {"approved": 0, "rejected": 0, "modified": 0}
    if result.timed_out:
        print("Validation timed out (300s limit).")
        _log_extract_error(stage="phase2_subprocess", reason="timeout after 300s")
        return {"approved": 0, "rejected": 0, "modified": 0}
    if result.returncode != 0:
        msg = failure_message(result)
        print(f"Validation failed: {msg}")
        _log_extract_error(
            stage="phase2_subprocess",
            reason=f"returncode={result.returncode} backend={result.backend}",
            raw_output=msg,
        )
        return {"approved": 0, "rejected": 0, "modified": 0}

    # Parse validation results from output
    return _parse_validation_output(result.stdout, project_id, snapshot, n_candidates)


def _infer_results_from_snapshot(project_id: str, snapshot: dict, n_candidates: int) -> dict:
    """Heuristic counts from before/after filenames when JSON parsing fails."""
    engrams_dir = get_engrams_dir(project_id)
    candidates_dir = get_candidates_dir(project_id)
    engrams_after = {p.name for p in engrams_dir.glob("*.md")}
    candidates_after = {p.name for p in candidates_dir.glob("*.md")}
    new_engrams = engrams_after - snapshot["engrams_before"]
    removed_candidates = snapshot["candidates_before"] - candidates_after
    new_stems = {Path(name).stem for name in new_engrams}

    approved = len(new_engrams)
    rejected = sum(
        1 for name in removed_candidates if Path(name).stem not in new_stems
    )

    return {
        "approved": approved,
        "rejected": rejected,
        "modified": 0,
        "decisions": [],
        "parse_failed": True,
        "new_engram_names": new_engrams,
        "candidates_remaining": candidates_after,
        "n_candidates": n_candidates,
    }


def _should_rotate_observations(results: dict, n_candidates: int, project_id: str) -> bool:
    """Whether to mark observations extracted after phase 2."""
    if results.get("parse_failed"):
        if results.get("candidates_remaining"):
            return False
        new_engrams = results.get("new_engram_names") or set()
        return len(new_engrams) <= n_candidates
    decided = (
        results.get("approved", 0)
        + results.get("rejected", 0)
        + results.get("modified", 0)
    )
    return decided > 0


def _parse_validation_output(
    output: str, project_id: str, snapshot: dict, n_candidates: int,
) -> dict:
    """Parse Sonnet's validation output and extract decisions.

    Handles three Sonnet output shapes:
    1. Multiple ```json blocks (one decision dict per block) — collect all.
    2. Single ```json block wrapping a JSON array of N decisions.
    3. Single ```json block wrapping a single dict (wrap into 1-element list).
    On total parse failure, infers counts from snapshot diff (not total engrams/).
    """
    results = {"approved": 0, "rejected": 0, "modified": 0, "decisions": [], "parse_failed": False}

    decisions: list = []
    parsed_any = False

    try:
        import re

        matches = re.findall(r"```(?:json)?\s*\n(.*?)```", output, re.DOTALL)

        if len(matches) > 1:
            # Multiple fenced json blocks — parse each independently so one
            # malformed block does not nuke the rest.
            for block in matches:
                try:
                    parsed = json.loads(block)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    decisions.append(parsed)
                    parsed_any = True
                elif isinstance(parsed, list):
                    decisions.extend(parsed)
                    parsed_any = True
        elif len(matches) == 1:
            # Single fenced block — could be array or single dict.
            parsed = json.loads(matches[0])
            if isinstance(parsed, list):
                decisions = parsed
            elif isinstance(parsed, dict):
                decisions = [parsed]
            parsed_any = True
        else:
            # No fenced blocks — try parsing the whole output as JSON.
            parsed = json.loads(output)
            if isinstance(parsed, list):
                decisions = parsed
            elif isinstance(parsed, dict):
                decisions = [parsed]
            parsed_any = True

        if not parsed_any:
            # All blocks failed to parse individually — trip outer fallback.
            raise json.JSONDecodeError("no parseable json blocks", output, 0)

        if isinstance(decisions, list):
            for d in decisions:
                if not isinstance(d, dict):
                    continue
                decision = d.get("decision", "REJECTED").upper()
                if decision == "APPROVED":
                    results["approved"] += 1
                elif decision == "MODIFIED":
                    results["modified"] += 1
                else:
                    results["rejected"] += 1
                results["decisions"].append(d)

    except (json.JSONDecodeError, KeyError) as exc:
        results = _infer_results_from_snapshot(project_id, snapshot, n_candidates)
        _log_extract_error(
            stage="validation_parse",
            reason=str(exc),
            raw_output=output,
        )

    # Log validation results (skipped when parse_failed — no structured decisions)
    if not results.get("parse_failed"):
        _log_validation(results["decisions"])

    return results


def _log_extract_error(stage: str, reason: str, raw_output: str = "") -> None:
    """Append a structured error record to extract_errors.jsonl."""
    log_path = PRISM_HOME / "extract_errors.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "reason": reason,
        "raw_output_snippet": raw_output[:500],
    }
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass


def _resolve_engram_file_path(entry_id: str, project_id: str) -> Path | None:
    """Resolve an engram markdown path from the index or conventional locations."""
    if not entry_id:
        return None
    home = PRISM_HOME.resolve()
    entry = get_entry(entry_id)
    if entry and entry.get("path"):
        path = (PRISM_HOME / entry["path"]).resolve()
        if str(path).startswith(str(home)) and path.is_file():
            return path
    for base in (get_engrams_dir(project_id), PRISM_HOME / "global" / "engrams"):
        candidate = base / f"{entry_id}.md"
        if candidate.is_file():
            return candidate
    return None


def _deprecate_entry(entry_id: str, project_id: str) -> bool:
    """Delete a superseded engram file, then remove it from the index."""
    path = _resolve_engram_file_path(entry_id, project_id)
    if path:
        try:
            path.unlink()
        except OSError:
            pass
    removed = remove_entry(entry_id)
    return path is not None or removed is not None


def _collect_deprecated_ids(results: dict) -> list[str]:
    """Unique deprecated entry IDs from validation decisions."""
    seen: set[str] = set()
    ordered: list[str] = []
    for decision in results.get("decisions", []):
        for entry_id in decision.get("deprecates") or []:
            if entry_id and entry_id not in seen:
                seen.add(entry_id)
                ordered.append(entry_id)
    return ordered


def _apply_validation_results(
    project_id: str,
    results: dict,
    rotate: bool = True,
    observation_ids: list[int] | None = None,
) -> None:
    """Update the index based on validation results."""
    engrams_dir = get_engrams_dir(project_id)

    # Deprecate before disk scan so orphaned files are not re-indexed
    for entry_id in _collect_deprecated_ids(results):
        _deprecate_entry(entry_id, project_id)

    # Scan engrams on disk; merge with index so reinforce/maintain metrics are not lost
    from .frontmatter import sync_entry_to_file

    for entry_file in engrams_dir.glob("*.md"):
        file_entry = _parse_frontmatter(entry_file, project_id)
        if not file_entry:
            continue
        existing = get_entry(file_entry["id"])
        if existing:
            merged = merge_file_entry_with_index(file_entry, existing)
            add_entry(merged)
            sync_entry_to_file(merged)
        else:
            add_entry(file_entry)

    # Clean up candidates Sonnet left behind.
    candidates_dir = get_candidates_dir(project_id)
    orphans = list(candidates_dir.glob("*.md"))
    if orphans and results.get("parse_failed"):
        # JSON unknown — only remove files already promoted to engrams/
        new_stems = {Path(n).stem for n in results.get("new_engram_names", set())}
        for orphan in orphans:
            if orphan.stem in new_stems:
                orphan.unlink(missing_ok=True)
    elif orphans:
        decided_ids = {d.get("candidate_id") for d in results.get("decisions", [])}
        for orphan in orphans:
            if orphan.stem not in decided_ids:
                results["rejected"] = results.get("rejected", 0) + 1
                orphan.unlink(missing_ok=True)
        remaining = list(candidates_dir.glob("*.md"))
        if remaining:
            for leftover in remaining:
                results["rejected"] = results.get("rejected", 0) + 1
                leftover.unlink(missing_ok=True)

    # Only rotate observations if phase 2 completed successfully
    if rotate and observation_ids:
        _rotate_observations(project_id, observation_ids)
    elif rotate and observation_ids is None:
        loaded = _load_batch_ids(project_id)
        if loaded:
            _rotate_observations(project_id, loaded)


def _parse_frontmatter(filepath: Path, project_id: str) -> "dict | None":
    """Parse YAML frontmatter from an knowledge entry markdown file."""
    try:
        content = filepath.read_text()
    except OSError:
        return None

    if not content.startswith("---"):
        return None

    # Simple YAML frontmatter parser (no PyYAML dependency)
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    frontmatter = {}
    for line in parts[1].strip().split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Handle simple types
            if value.startswith("[") and value.endswith("]"):
                # Simple list parsing
                items = value[1:-1].split(",")
                value = [item.strip().strip("'\"") for item in items if item.strip()]
            elif value.lower() in ("true", "false"):
                value = value.lower() == "true"
            else:
                try:
                    value = float(value)
                    if value == int(value):
                        value = int(value)
                except ValueError:
                    value = value.strip("'\"")
            frontmatter[key] = value

    entry_id = frontmatter.get("id", filepath.stem)
    rel_path = str(filepath.relative_to(PRISM_HOME)) if str(filepath).startswith(str(PRISM_HOME)) else str(filepath)

    return build_index_entry(
        entry_id=entry_id,
        kind=frontmatter.get("kind", "preference"),
        trigger=frontmatter.get("trigger", ""),
        confidence=float(frontmatter.get("confidence", 0.5)),
        domain=frontmatter.get("domain", "general"),
        scope=frontmatter.get("scope", "project"),
        project_id=frontmatter.get("project_id", project_id),
        path=rel_path,
        evidence_count=int(frontmatter.get("evidence_count", 1)),
        tags=frontmatter.get("tags", []),
        success_count=int(frontmatter.get("success_count", 0)),
        failure_count=int(frontmatter.get("failure_count", 0)),
        pinned=bool(frontmatter.get("pinned", False)),
        last_observed=frontmatter.get("last_observed") or None,
    )


def _rotate_observations(project_id: str, observation_ids: list[int]) -> None:
    """Mark the extraction batch as extracted and purge old rows."""
    config = get_config()
    retain_seconds = config.get("observation_retention_seconds", 30 * 24 * 60 * 60)
    mark_extracted(project_id, observation_ids=observation_ids)
    _clear_batch_ids(project_id)
    purged = purge_old(project_id, retain_seconds=retain_seconds)
    if purged:
        print(f"Purged {purged} old observations (retention: {retain_seconds}s).")


def _log_validation(decisions: list) -> None:
    """Append validation decisions to the log."""
    log_path = PRISM_HOME / "validation-log.jsonl"
    timestamp = datetime.now(timezone.utc).isoformat()

    with open(log_path, "a") as f:
        for d in decisions:
            entry = {
                "timestamp": timestamp,
                "candidate": d.get("candidate_id", "unknown"),
                "decision": d.get("decision", "UNKNOWN"),
                "gates": d.get("gates", {}),
            }
            f.write(json.dumps(entry) + "\n")
