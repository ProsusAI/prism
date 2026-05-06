"""Extraction pipeline - Phase 1 (Haiku) and Phase 2 (Sonnet)."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    PRISM_HOME,
    get_candidates_dir,
    get_config,
    get_engrams_dir,
    get_observations_path,
    get_project_dir,
    ensure_dirs,
)
from .index import add_entry, build_index_entry, load_index, remove_entry


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


def run_extraction(project_id: str) -> dict:
    """Run the full extraction + validation pipeline.

    Returns {"extracted": N, "approved": N, "rejected": N, "modified": N}.
    """
    ensure_dirs(project_id)
    lock = PRISM_HOME / ".extracting"

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
        else:
            n_candidates = _phase1_extract(project_id)
            if n_candidates == 0:
                return {"extracted": 0, "approved": 0, "rejected": 0, "modified": 0}

        # Phase 2: Sonnet validates candidates
        results = _phase2_validate(project_id)
        results["extracted"] = n_candidates

        # Only rotate observations if phase 2 produced a meaningful result
        phase2_ran = results.get("approved", 0) + results.get("rejected", 0) + results.get("modified", 0) > 0
        _apply_validation_results(project_id, results, rotate=phase2_ran or not existing_candidates)

        # Post-extraction: sync .claude/prism.md with new engrams (EXT-05, CTX-04)
        try:
            from .sync import sync_claude_code
            sync_claude_code(project_id)
        except Exception:
            pass  # Don't let sync failure break extraction

        return results
    finally:
        lock.unlink(missing_ok=True)


def _phase1_extract(project_id: str) -> int:
    """Run Haiku extraction on observations. Returns count of candidates created."""
    observations_path = get_observations_path(project_id)
    if not observations_path.exists() or observations_path.stat().st_size == 0:
        print("No observations to process.")
        return 0

    candidates_dir = get_candidates_dir(project_id)
    index_path = PRISM_HOME / "index.json"
    extractor_prompt_path = _find_agent_prompt("extractor.md")

    if not extractor_prompt_path:
        print("Error: extractor prompt not found. Run ./install.sh to set up.")
        return 0

    # Count observations
    with open(observations_path) as f:
        obs_count = sum(1 for _ in f)

    config = get_config()
    threshold = config.get("extract_threshold", 15)
    print(f"Found {obs_count} observations (threshold: {threshold})")

    # Build the prompt for Haiku
    prompt = f"""Read the extractor instructions at {extractor_prompt_path}.

Then analyze the observations at {observations_path}.
The current knowledge index is at {index_path}.
Write candidate knowledge entry files to {candidates_dir}/.

The project ID is: {project_id}
"""

    # Run claude --print --model haiku
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "haiku", "-p", prompt,
             "--allowedTools", "Read,Write,Glob,Grep"],
            capture_output=True, text=True, timeout=300,
            cwd=str(PRISM_HOME),
        )
        if result.returncode != 0:
            msg = result.stderr[:500]
            print(f"Extraction failed: {msg}")
            _log_extract_error(stage="haiku_subprocess", reason=f"returncode={result.returncode}", raw_output=msg)
            return 0
    except FileNotFoundError:
        print("Error: 'claude' CLI not found. Install Claude Code to use extraction.")
        _log_extract_error(stage="haiku_subprocess", reason="claude CLI not found")
        return 0
    except subprocess.TimeoutExpired:
        print("Extraction timed out (120s limit).")
        _log_extract_error(stage="haiku_subprocess", reason="timeout after 300s")
        return 0

    # Count candidates created
    candidates = list(candidates_dir.glob("*.md"))
    print(f"Extraction complete: {len(candidates)} candidates created")
    return len(candidates)


def _phase2_validate(project_id: str) -> dict:
    """Run Sonnet validation on candidates. Returns results dict."""
    candidates_dir = get_candidates_dir(project_id)
    candidates = list(candidates_dir.glob("*.md"))
    if not candidates:
        return {"approved": 0, "rejected": 0, "modified": 0}

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
    prompt = f"""Read the validator instructions at {validator_prompt_path}.

Read the constitution at {constitution_path}.
Read the knowledge index at {index_path}.

Review each candidate file in {candidates_dir}/:
{candidate_list}

For each candidate, evaluate all 4 gates and output your decisions.

CRITICAL: You MUST output a decision for ALL {n_candidates} candidates in a single JSON array.
Every candidate — whether APPROVED, REJECTED, or MODIFIED — must appear in the array.
A candidate with no decision is a bug. The array must have exactly {n_candidates} elements.

Output your decisions as a JSON array wrapped in ```json fences:
[
  {{"candidate_id": "...", "decision": "APPROVED|REJECTED|MODIFIED", "gates": {{...}}, "modifications": "...", "deprecates": []}},
  ...
]

After outputting the JSON array:
- For APPROVED candidates: move them from {candidates_dir}/ to the entries directory
- For REJECTED candidates: delete them from {candidates_dir}/
- For MODIFIED candidates: apply modifications then move to the entries directory
"""

    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "sonnet", "-p", prompt,
             "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash"],
            capture_output=True, text=True, timeout=300,
            cwd=str(PRISM_HOME),
        )
        if result.returncode != 0:
            msg = result.stderr[:500]
            print(f"Validation failed: {msg}")
            _log_extract_error(stage="sonnet_subprocess", reason=f"returncode={result.returncode}", raw_output=msg)
            return {"approved": 0, "rejected": 0, "modified": 0}
    except FileNotFoundError:
        print("Error: 'claude' CLI not found.")
        _log_extract_error(stage="sonnet_subprocess", reason="claude CLI not found")
        return {"approved": 0, "rejected": 0, "modified": 0}
    except subprocess.TimeoutExpired:
        print("Validation timed out (300s limit).")
        _log_extract_error(stage="sonnet_subprocess", reason="timeout after 300s")
        return {"approved": 0, "rejected": 0, "modified": 0}

    # Parse validation results from output
    return _parse_validation_output(result.stdout, project_id)


def _parse_validation_output(output: str, project_id: str) -> dict:
    """Parse Sonnet's validation output and extract decisions.

    Handles three Sonnet output shapes:
    1. Multiple ```json blocks (one decision dict per block) — collect all.
    2. Single ```json block wrapping a JSON array of N decisions.
    3. Single ```json block wrapping a single dict (wrap into 1-element list).
    Falls back to parsing the whole body, then to counting engram files
    if nothing parses at all.
    """
    results = {"approved": 0, "rejected": 0, "modified": 0, "decisions": []}

    decisions: list = []
    parsed_any = False

    try:
        import re

        matches = re.findall(r"```json\s*\n(.*?)\n\s*```", output, re.DOTALL)

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
        # Total parse failure — count any files Sonnet moved to entries dir
        # and log a structured error so prism status can surface it.
        engrams_dir = get_engrams_dir(project_id)
        results["approved"] = len(list(engrams_dir.glob("*.md")))
        _log_extract_error(
            stage="validation_parse",
            reason=str(exc),
            raw_output=output,
        )

    # Log validation results
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


def _apply_validation_results(project_id: str, results: dict, rotate: bool = True) -> None:
    """Update the index based on validation results."""
    engrams_dir = get_engrams_dir(project_id)

    # Scan entries directory for any new files and add to index
    for entry_file in engrams_dir.glob("*.md"):
        entry = _parse_frontmatter(entry_file, project_id)
        if entry:
            add_entry(entry)

    # Handle deprecations
    for decision in results.get("decisions", []):
        for deprecated_id in decision.get("deprecates", []):
            remove_entry(deprecated_id)

    # Clean up any candidates Sonnet left behind (not moved or deleted).
    # These are orphans — the validator didn't mention them in its JSON output.
    # Treat as implicitly rejected so they don't accumulate across runs.
    candidates_dir = get_candidates_dir(project_id)
    orphans = list(candidates_dir.glob("*.md"))
    if orphans:
        decided_ids = {d.get("candidate_id") for d in results.get("decisions", [])}
        for orphan in orphans:
            if orphan.stem not in decided_ids:
                results["rejected"] = results.get("rejected", 0) + 1
                orphan.unlink(missing_ok=True)
        remaining = list(candidates_dir.glob("*.md"))
        if remaining:
            # Sonnet moved approved/modified ones but forgot to delete rejected — clean up
            for leftover in remaining:
                results["rejected"] = results.get("rejected", 0) + 1
                leftover.unlink(missing_ok=True)

    # Only rotate observations if phase 2 completed successfully
    if rotate:
        _rotate_observations(project_id)


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
    )


def _rotate_observations(project_id: str) -> None:
    """Archive processed observations."""
    obs_path = get_observations_path(project_id)
    if not obs_path.exists():
        return

    archive_dir = get_project_dir(project_id) / "observations.archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"observations_{timestamp}.jsonl"

    obs_path.rename(archive_path)
    # Create fresh empty file
    obs_path.touch()


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
