# Copyright © 2025 MIH AI B.V.
# Licensed under the Apache License, Version 2.0
# See LICENSE file in the project root

"""Prism bridge - promote engrams to publishable skill format."""

import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path

from .config import PRISM_HOME, get_config
from .index import get_entry


# Stop words removed from generated skill names
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of",
    "in", "for", "on", "with", "at", "by", "and", "or", "but", "not",
    "it", "this", "that",
})

# Map engram kind to skill category
_KIND_CATEGORY_MAP = {
    "preference": ["architecture"],
    "correction": ["architecture"],
    "procedure": ["execution-control"],
    "domain_fact": ["architecture"],
    "tool_pattern": ["tools"],
    "error_recipe": ["execution-control"],
}

# Skill name validation pattern (from plugin.schema.json)
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)+$")


def cmd_promote(entry_id, name_override=None):
    """Promote a high-confidence engram to publishable skill format.

    Creates a skill directory with plugin.json and SKILL.md in
    _analysis/extracted_skills_codebase/<skill-name>/.

    Gate checks enforce: confidence >= min, evidence >= min, source != registry.
    """
    # Load entry
    entry = get_entry(entry_id)
    if entry is None:
        print("Entry not found: {}".format(entry_id))
        return

    # Load config for gate thresholds
    config = get_config()

    # Gate: confidence
    conf = entry.get("confidence", 0)
    min_conf = config.get("publish_min_confidence", 0.7)
    if conf < min_conf:
        print("Gate failed: confidence {:.2f} < {}".format(conf, min_conf))
        return

    # Gate: evidence
    count = entry.get("evidence_count", 0)
    min_evidence = config.get("publish_min_evidence", 3)
    if count < min_evidence:
        print("Gate failed: evidence {} < {}".format(count, min_evidence))
        return

    # Gate: source != registry
    if entry.get("source") == "registry":
        print("Gate failed: cannot promote registry-sourced engrams")
        return

    # Read engram content
    entry_path = (PRISM_HOME / entry.get("path", "")).resolve()
    if not str(entry_path).startswith(str(PRISM_HOME.resolve())):
        print("Security: path escapes PRISM_HOME: {}".format(entry_path))
        return
    if not entry_path.exists():
        print("Engram file not found: {}".format(entry_path))
        return

    content = entry_path.read_text()
    frontmatter, body = _parse_frontmatter(content)

    # Generate skill name
    if name_override:
        skill_name = name_override
        if not _NAME_PATTERN.match(skill_name):
            print("Invalid skill name: {} (must match {})".format(
                skill_name, _NAME_PATTERN.pattern))
            return
    else:
        skill_name = _generate_skill_name(entry, frontmatter)

    # Build plugin.json and SKILL.md
    plugin = _build_plugin_json(skill_name, entry, frontmatter, body)
    skill_md = _build_skill_md(skill_name, entry, frontmatter, body)

    # Write output
    output_dir = Path.cwd() / "_analysis" / "extracted_skills_codebase" / skill_name
    output_dir.mkdir(parents=True, exist_ok=True)

    plugin_path = output_dir / "plugin.json"
    plugin_path.write_text(json.dumps(plugin, indent=2) + "\n")

    skill_md_path = output_dir / "SKILL.md"
    skill_md_path.write_text(skill_md)

    print("Promoted: {} -> {}".format(entry_id, skill_name))
    print("  Output: {}".format(output_dir))
    print("\nNext: /curate-skills then /publish-skills")


def _parse_frontmatter(content):
    """Parse YAML frontmatter from markdown content.

    Returns (frontmatter_dict, body_string). Handles simple key: value lines
    without requiring PyYAML (zero-dependency constraint).
    """
    frontmatter = {}
    body = content

    if not content.startswith("---"):
        return frontmatter, body

    parts = content.split("---", 2)
    if len(parts) < 3:
        return frontmatter, body

    # parts[0] is empty (before first ---), parts[1] is frontmatter, parts[2] is body
    fm_text = parts[1].strip()
    body = parts[2].strip()

    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes
            if value and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            # Handle list values like [tag1, tag2]
            if value.startswith("[") and value.endswith("]"):
                items = [v.strip().strip('"').strip("'")
                         for v in value[1:-1].split(",") if v.strip()]
                value = items
            frontmatter[key] = value

    return frontmatter, body


def _generate_skill_name(entry, frontmatter):
    """Generate a kebab-case skill name from engram trigger and kind.

    Follows plugin.schema.json name pattern: ^[a-z][a-z0-9]*(-[a-z0-9]+)+$
    (at least 2 hyphen-separated segments, starts with letter).
    """
    trigger = entry.get("trigger", "")
    # Strip surrounding quotes
    trigger = trigger.strip('"').strip("'")

    # Lowercase, replace non-alphanumeric with hyphens
    name = re.sub(r"[^a-z0-9]+", "-", trigger.lower())
    name = name.strip("-")

    # Split into segments and remove stop words
    segments = [s for s in name.split("-") if s and s not in _STOP_WORDS]

    # If fewer than 2 segments, append the engram kind
    kind = entry.get("kind", "preference")
    if len(segments) < 2:
        kind_segments = kind.replace("_", "-").split("-")
        segments.extend(kind_segments)

    # Truncate to first 5 segments
    segments = segments[:5]

    # Rejoin and enforce max 60 chars (break at hyphen boundary)
    name = "-".join(segments)
    if len(name) > 60:
        name = name[:60]
        # Break at last hyphen to avoid partial words
        if "-" in name:
            name = name.rsplit("-", 1)[0]

    # Ensure first char is alphabetic
    if name and not name[0].isalpha():
        kind_first = kind.replace("_", "-").split("-")[0]
        name = kind_first + "-" + name

    # Final validation
    if not _NAME_PATTERN.match(name):
        # Fallback to kind-based name
        name = kind.replace("_", "-") + "-skill"

    return name


def _build_plugin_json(skill_name, entry, frontmatter, body):
    """Build a plugin.json dict for the promoted skill.

    All 8 required fields per plugin.schema.json:
    name, description, author, repository, category, source, commit_date, source_hash
    """
    kind = entry.get("kind", "preference")
    trigger = entry.get("trigger", "").strip('"').strip("'")
    domain = entry.get("domain", "general")

    return {
        "name": skill_name,
        "description": _build_description(trigger, body, kind, domain),
        "author": _git_config("user.name"),
        "repository": _git_repo_name(),
        "category": _KIND_CATEGORY_MAP.get(kind, ["architecture"]),
        "source": "engram",
        "commit_date": date.today().strftime("%d-%m-%Y"),
        "source_hash": _git_short_hash(),
    }


def _build_description(trigger, body, kind, domain="general"):
    """Build a description that satisfies schema: >= 50 chars, contains 'TRIGGER when:'.

    Format: first sentence from body (or expanded trigger), then
    'TRIGGER when:' followed by scenario phrases from domain/kind.
    """
    # Extract first sentence from body for the lead
    lead = trigger
    if body:
        # Get the first non-empty, non-heading line from body
        for line in body.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("*"):
                lead = line.rstrip(".")
                break

    # Build trigger scenarios based on domain and kind
    scenarios = _build_scenarios(trigger, kind, domain)

    description = "{}. TRIGGER when: {}".format(lead, ", ".join(scenarios))

    # Ensure minimum 50 chars
    if len(description) < 50:
        description = description + " This applies broadly across the {} domain.".format(domain)

    return description


def _build_scenarios(trigger, kind, domain):
    """Generate 2-3 scenario phrases for the TRIGGER clause."""
    scenarios = []

    # Domain-based scenario
    if domain and domain != "general":
        scenarios.append("working in {} context".format(domain))

    # Kind-based scenarios
    kind_scenarios = {
        "preference": ["setting up project configuration", "reviewing code style decisions"],
        "correction": ["encountering the corrected pattern", "reviewing similar code"],
        "procedure": ["following established workflow steps", "executing multi-step processes"],
        "domain_fact": ["making architectural decisions", "evaluating technical trade-offs"],
        "tool_pattern": ["configuring development tools", "setting up tool integrations"],
        "error_recipe": ["debugging similar errors", "troubleshooting related failures"],
    }
    scenarios.extend(kind_scenarios.get(kind, ["making related decisions"]))

    # Trigger-derived scenario (use first few words as context)
    trigger_words = trigger.strip('"').strip("'").split()[:4]
    if len(trigger_words) >= 2:
        scenarios.append("dealing with {}".format(" ".join(trigger_words).lower()))

    # Return 2-3 scenarios
    return scenarios[:3]


def _git_config(key):
    """Read a git config value. Returns 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "config", key],
            capture_output=True, text=True, timeout=5,
        )
        value = result.stdout.strip()
        return value if value else "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "unknown"


def _git_repo_name():
    """Extract org/repo from git remote URL. Returns 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        url = result.stdout.strip()
        if not url:
            return "unknown"

        # Handle SSH URLs: git@github.com:org/repo.git
        match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
        if match:
            return match.group(1)
        return "unknown"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "unknown"


def _git_short_hash():
    """Get short git commit hash. Returns None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        h = result.stdout.strip()
        return h if h else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _build_skill_md(skill_name, entry, frontmatter, body):
    """Build SKILL.md in extract-skills format: Key Decisions, Anti-patterns, optional Structural Template."""
    trigger = entry.get("trigger", "").strip('"').strip("'")
    kind = entry.get("kind", "preference")
    domain = entry.get("domain", "general")

    description = _build_description(trigger, body, kind, domain)

    # Strip Evidence section — engram metadata, not skill content
    clean_body = _strip_evidence_section(body)

    lines = [
        "---",
        "name: {}".format(skill_name),
        'description: "{}"'.format(description.replace('"', '\\"')),
        "---",
        "",
        "## Key Decisions",
        "",
    ]

    if clean_body.strip():
        lines.append(clean_body.strip())
    else:
        lines.append("1. {}.".format(trigger[:200] if trigger else skill_name.replace("-", " ")))

    lines += [
        "",
        "## Anti-patterns",
        "",
        "- **What**: Deviating from this pattern inconsistently.",
        "  **Why**: Inconsistency creates confusion and increases review overhead.",
        "  **Symptom**: Code review comments flag the same issue repeatedly.",
        "",
    ]

    # Structural Template: only include for procedural/workflow kinds where structure adds value
    if kind in ("procedure", "tool_pattern", "error_recipe"):
        lines += [
            "## Structural Template",
            "",
            "```",
            "# Apply consistently across all relevant files.",
            "# Enforce via tooling (linter, editor config, CI check) where possible.",
            "```",
            "",
        ]

    return "\n".join(lines)


def _strip_evidence_section(body):
    """Remove ## Evidence section and everything after it from engram body."""
    if not body:
        return ""
    parts = re.split(r"\n##\s+Evidence\b.*", body, flags=re.IGNORECASE | re.DOTALL)
    return parts[0].strip()
