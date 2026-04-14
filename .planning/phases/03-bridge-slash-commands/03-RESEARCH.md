# Phase 3: Bridge + Slash Commands - Research

**Researched:** 2026-04-14
**Domain:** Engram-to-skill promotion (Python CLI), Claude Code slash commands (SKILL.md adaptation)
**Confidence:** HIGH

## Summary

Phase 3 has two distinct workstreams: (1) a Python `prism promote` command that converts high-confidence engrams into the `plugin.json` + `SKILL.md` skill format, and (2) copying + adapting 13 Lens slash commands into 12 Prism slash commands (unifying two publish commands into one). Both workstreams are primarily copy-and-modify operations with well-defined source material.

The promotion bridge is a local-only Python stdlib operation: read an engram from the index, check gates (confidence >= 0.7, evidence >= 3, source != "registry"), generate a kebab-case skill name, create `plugin.json` and `SKILL.md` files in `_analysis/extracted_skills_codebase/<name>/`. The main complexity is format mapping -- engram fields to plugin.json fields -- and auto-generating a valid TRIGGER clause from engram content.

The slash command work is 13 Lens SKILL.md files adapted into 12. Based on source inspection: 4 commands can be copied as-is (analyze-agent-codebase with 7 question files, mine-history, mine-design, curate-skills), 5 need minor edits (removing Prosus-specific references), and 3 need heavier rewriting (two publish commands merged into one, advise-skills and audit-code adapted for Prism's config-based registry instead of `.claude/skill-registry.json`).

**Primary recommendation:** Build the promote command first (new Python code), then batch-copy slash commands by modification level -- as-is first, then minor edits, then rewrites. Install.sh needs a new step to copy skills into `~/.prism/skills/`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Promoted engrams are written to `_analysis/extracted_skills_codebase/<name>/` -- same directory as extraction pipeline output. The `source` field in plugin.json distinguishes promoted engrams (`"engram"`) from extracted skills (`"external"`). This way `/curate-skills` and `/publish-skills` see everything in one place without scanning multiple directories.
- **D-02:** `prism promote` auto-creates `_analysis/extracted_skills_codebase/` on demand if it doesn't exist. No prior extraction pipeline run required. BRG-04 requires promotion to work fully offline and standalone.
- **D-03:** Skill names are auto-generated from engram content -- extract key terms from engram title/content, generate kebab-case name matching the `^[a-z][a-z0-9]*(-[a-z0-9]+)+$` pattern required by plugin.schema.json. User can override with `--name` flag.

### Claude's Discretion
- Promotion format mapping: how engram fields map to plugin.json fields. Follow plugin.schema.json and generate TRIGGER clause from engram content.
- Slash command adaptation scope: how much to modify the 13 Lens commands into Prism's 12. Follow copy-and-modify approach.
- Registry readiness boundary: `/advise-skills` and `/audit-code` should work with local `skill-registry.json` if available. Full multi-registry support comes in Phase 4.
- `.published.json` delta tracking structure and content hash algorithm for `/publish-skills`
- Exact kebab-case name generation algorithm from engram content
- Which Lens command files need heavy rewriting vs light rename-and-ship

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BRG-01 | `prism promote <id>` checks gates: confidence >= 0.7, evidence >= 3, source != "registry" | Gate values from config.py (`publish_min_confidence: 0.7`); evidence gate needs `publish_min_evidence: 3` added to config; `source` field absent in current index entries -- treat absent as "not registry" |
| BRG-02 | Promotion converts engram markdown to `plugin.json` + `SKILL.md` format | Schema at `/Users/gaurav/codes/Lens/schemas/plugin.schema.json`; required fields: name, description, author, repository, category, source, commit_date, source_hash; SKILL.md needs YAML frontmatter with name+description |
| BRG-03 | Promoted skills written to `_analysis/extracted_skills_codebase/<name>/` | Per D-01; directory auto-created per D-02 |
| BRG-04 | Promotion is local-only (no network needed, works without registry) | All data available locally: engram in index.json + .md file, git metadata via subprocess |
| SKILL-01 | `/run-analysis-pipeline` | Copy from Lens with minor edits: update publish command references from `publish-skills-cloudflare`/`publish-skills-github` to `publish-skills` |
| SKILL-02 | `/run-history-pipeline` | Copy from Lens with minor edits: same publish reference update |
| SKILL-03 | `/analyze-agent-codebase` | Copy as-is from Lens including all 7 question cluster files + synthesis questions |
| SKILL-04 | `/extract-skills` | Copy with minor edits: remove Prosus-specific "internal/external" prompt language |
| SKILL-05 | `/mine-history` | Copy as-is from Lens |
| SKILL-06 | `/mine-design` | Copy as-is from Lens |
| SKILL-07 | `/synthesize` | Copy with minor edits: remove Prosus-specific "internal/external" prompt language |
| SKILL-08 | `/synthesize-decisions` | Copy with minor edits: remove Prosus-specific references |
| SKILL-09 | `/curate-skills` | Copy as-is from Lens |
| SKILL-10 | `/publish-skills` unified with delta tracking | Heavy rewrite: merge publish-skills-cloudflare + publish-skills-github into one command; add `.published.json` delta tracking; use config-based registry URL from `~/.prism/config.json` |
| SKILL-11 | `/advise-skills` | Heavy rewrite: use Prism config-based registry instead of `.claude/skill-registry.json`; remove Lens install.sh references; support local skill-registry.json as fallback |
| SKILL-12 | `/audit-code` | Heavy rewrite: same changes as advise-skills |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (json, pathlib, re, hashlib, subprocess, datetime) | 3.12+ | promote command, format conversion, hash computation | Zero-dependency constraint from CLAUDE.md |
| SKILL.md (markdown with YAML frontmatter) | N/A | Slash command format | Claude Code skills standard since v2.1.3 |
| plugin.schema.json (JSON Schema draft 2020-12) | N/A | Skill metadata validation | Carried from Lens, used by CI validation |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| hashlib (stdlib) | N/A | Content hashing for `.published.json` delta tracking | SHA256 of `plugin.json` + `SKILL.md` content |
| subprocess (stdlib) | N/A | Auto-detect git user, remote, commit hash for plugin.json fields | Only in promote command for metadata collection |

**No installation needed** -- all Python components are stdlib. Slash commands are SKILL.md files (no dependencies).

## Architecture Patterns

### Recommended Project Structure

```
lib/
  bridge.py              # NEW: prism promote logic (BRG-01 through BRG-04)
  cli.py                 # MODIFIED: add promote subcommand
  commands.py            # UNCHANGED
  config.py              # MODIFIED: add publish_min_evidence default

skills/                  # NEW directory in repo root
  analyze-agent-codebase/
    SKILL.md
    questions_cluster_a.md ... questions_synthesis.md   # 8 files total
  extract-skills/
    SKILL.md
  mine-history/
    SKILL.md
  mine-design/
    SKILL.md
  synthesize/
    SKILL.md
  synthesize-decisions/
    SKILL.md
  curate-skills/
    SKILL.md
  publish-skills/        # NEW unified command
    SKILL.md
  run-analysis-pipeline/
    SKILL.md
  run-history-pipeline/
    SKILL.md
  advise-skills/
    SKILL.md
  audit-code/
    SKILL.md

schemas/                 # NEW directory in repo root
  plugin.schema.json     # Copied from Lens with source pattern updated

install.sh               # MODIFIED: add skills + schemas copy step
```

### Pattern 1: Promotion Bridge (lib/bridge.py)

**What:** A standalone module implementing `cmd_promote(entry_id, name_override=None)` that:
1. Loads the engram from index via `get_entry(entry_id)`
2. Validates gates (confidence, evidence, source)
3. Reads the engram markdown file for full content
4. Generates skill name (from engram trigger/content, kebab-case)
5. Builds plugin.json dict with all required schema fields
6. Builds SKILL.md with frontmatter + content
7. Creates output directory and writes both files
8. Prints next-step guidance

**When to use:** This is the sole pattern for BRG-01 through BRG-04.

**Example:**
```python
# Source: unified-design.md promote spec + plugin.schema.json analysis
import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path

from .config import PRISM_HOME, get_config
from .index import get_entry

def cmd_promote(entry_id: str, name_override: str = None) -> None:
    """Promote a high-confidence engram to skill format."""
    entry = get_entry(entry_id)
    if not entry:
        print(f"Entry not found: {entry_id}")
        return

    config = get_config()

    # Gate checks (BRG-01)
    min_conf = config.get("publish_min_confidence", 0.7)
    min_evidence = config.get("publish_min_evidence", 3)

    if entry.get("confidence", 0) < min_conf:
        print(f"Gate failed: confidence {entry['confidence']:.2f} < {min_conf}")
        return
    if entry.get("evidence_count", 0) < min_evidence:
        print(f"Gate failed: evidence {entry['evidence_count']} < {min_evidence}")
        return
    if entry.get("source") == "registry":
        print("Gate failed: cannot promote registry-sourced engrams")
        return

    # Read full engram content
    engram_path = PRISM_HOME / entry.get("path", "")
    if not engram_path.exists():
        print(f"Engram file not found: {engram_path}")
        return

    engram_content = engram_path.read_text()
    # Parse frontmatter and body...
    frontmatter, body = _parse_frontmatter(engram_content)

    # Generate skill name (D-03)
    skill_name = name_override or _generate_skill_name(entry, frontmatter)

    # Build output (BRG-02, BRG-03)
    output_dir = Path.cwd() / "_analysis" / "extracted_skills_codebase" / skill_name
    output_dir.mkdir(parents=True, exist_ok=True)  # D-02

    plugin = _build_plugin_json(skill_name, entry, frontmatter, body)
    skill_md = _build_skill_md(skill_name, entry, frontmatter, body)

    (output_dir / "plugin.json").write_text(json.dumps(plugin, indent=2) + "\n")
    (output_dir / "SKILL.md").write_text(skill_md)

    print(f"Promoted: {entry_id} -> {skill_name}")
    print(f"  Output: {output_dir}")
    print(f"\nNext: /curate-skills then /publish-skills")
```
[VERIFIED: Prism codebase lib/index.py, lib/config.py, lib/commands.py patterns]

### Pattern 2: Slash Command Adaptation Classification

**What:** Three tiers of modification for Lens commands.

**Tier 1 - Copy as-is (4 commands, 11 files):**
- `analyze-agent-codebase/` (SKILL.md + 7 question files = 8 files)
- `mine-history/` (SKILL.md = 1 file)
- `mine-design/` (SKILL.md = 1 file)
- `curate-skills/` (SKILL.md = 1 file)

These commands contain no Lens-specific paths, no Prosus references, no registry-specific logic. They operate entirely on `_analysis/` directory contents.
[VERIFIED: read all 4 SKILL.md files from Lens source]

**Tier 2 - Minor edits (5 commands, 5 files):**
- `run-analysis-pipeline/` -- update references from `publish-skills-cloudflare`/`publish-skills-github` to `publish-skills`
- `run-history-pipeline/` -- same publish reference update
- `extract-skills/` -- remove "Prosus / portfolio company" language from internal/external prompt
- `synthesize/` -- same Prosus reference removal
- `synthesize-decisions/` -- same Prosus reference removal

Changes are textual find-and-replace, minimal risk.
[VERIFIED: read all 5 SKILL.md files, identified specific lines needing change]

**Tier 3 - Heavy rewrite (3 Lens commands -> 2 Prism commands):**
- `publish-skills/` (NEW, replaces publish-skills-cloudflare + publish-skills-github):
  - Worker-only publishing (per PROJECT.md: "Worker-only registry access")
  - Delta tracking via `_analysis/.published.json`
  - Content hash computation: SHA256 of `plugin.json` + `SKILL.md` concatenated
  - Registry URL + token from config, not env vars
  - `--registry NAME` flag for targeting specific registry
  - `--all` flag to republish everything
- `advise-skills/` (rewrite):
  - Use Prism config-based registries instead of `.claude/skill-registry.json`
  - Fall back to local `skill-registry.json` if available (Phase 3 scope)
  - Remove Lens install.sh references
  - Remove GitHub-direct platform detection
- `audit-code/` (rewrite):
  - Same changes as advise-skills
  - Remove Lens install.sh references

[VERIFIED: read publish-skills-cloudflare, publish-skills-github, advise-skills, audit-code SKILL.md files]

### Pattern 3: Install.sh Skills Copy

**What:** Add a step to install.sh that copies the `skills/` directory from repo into `~/.prism/skills/`.

```bash
# Copy slash commands (overwrite on upgrade)
if [ -d "$PRISM_REPO/skills" ]; then
    for skill_dir in "$PRISM_REPO/skills"/*/; do
        [ -d "$skill_dir" ] || continue
        skill_name=$(basename "$skill_dir")
        mkdir -p "$PRISM_HOME/skills/$skill_name"
        cp "$skill_dir"* "$PRISM_HOME/skills/$skill_name/" 2>/dev/null
    done
fi
```

This integrates with the existing `_setup_slash_commands()` in commands.py which symlinks `~/.prism/skills/<name>/` to `.claude/skills/<name>/` during `prism init`.
[VERIFIED: install.sh line 45, commands.py _setup_slash_commands()]

### Pattern 4: Schema Adaptation for "engram" Source Type

**What:** The Lens `plugin.schema.json` source field pattern is `^(internal|external(\s+\(?https?://.+\)?)?)$` which only allows "internal" or "external [URL]". Per D-01, promoted engrams need `source: "engram"`. Prism's copy of the schema must update this pattern to: `^(internal|external(\s+\(?https?://.+\)?)?|engram)$`.

This is Prism's own schema -- it diverges intentionally from Lens here. The `source` field distinguishes provenance: `"internal"` (internal team extraction), `"external [URL]"` (open-source extraction), `"engram"` (promoted from personal learning).
[VERIFIED: plugin.schema.json source pattern at line 50-53]

### Anti-Patterns to Avoid

- **Building promotion AI-powered:** `prism promote` must be deterministic, local-only, no Claude CLI calls. The TRIGGER clause and plugin.json fields are generated from engram metadata, not by asking an LLM. This is a format conversion, not a creative act.
- **Modifying Lens commands beyond what's needed:** Many commands are long (200+ lines). The temptation is to "improve" them. Don't -- copy-and-modify means minimal changes for traceability back to Lens source.
- **Publishing to GitHub directly in Phase 3:** Per PROJECT.md, Prism uses "Worker-only registry access". The unified `/publish-skills` should only implement the Cloudflare Worker API path. GitHub-direct CI workflow generation (what `publish-skills-github` does) is out of scope.
- **Full multi-registry in Phase 3:** `/advise-skills` and `/audit-code` should gracefully handle available local `skill-registry.json`. Full multi-registry config resolution is Phase 4.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML frontmatter parsing | Full YAML parser | Simple `---` split + `key: value` line parser | Zero-dependency constraint; engram frontmatter is simple key-value pairs; existing pattern in codebase |
| JSON Schema validation | Runtime validator | Copy schema file for CI use; promote command does structural checks directly | `jsonschema` is CI-only dependency; promote command validates required fields in Python code |
| Content hashing | Custom hash | `hashlib.sha256()` on file contents | Stdlib, deterministic, fast |
| Kebab-case generation | Custom NLP | Regex-based: lowercase, strip non-alphanumeric, collapse hyphens, ensure 2+ word minimum | Plugin.schema.json requires `^[a-z][a-z0-9]*(-[a-z0-9]+)+$` -- at least 2 hyphenated segments |
| Git metadata collection | Custom git parsing | `subprocess.run(["git", ...])` for user.name, remote URL, rev-parse | Existing pattern in codebase (see extract-skills SKILL.md); handles absence gracefully |

**Key insight:** The promote command is a format converter, not an AI feature. Every field in plugin.json can be derived deterministically from engram metadata + git state + current date. No Claude CLI calls needed.

## Common Pitfalls

### Pitfall 1: Kebab-Case Name Validation
**What goes wrong:** Auto-generated skill names don't match `^[a-z][a-z0-9]*(-[a-z0-9]+)+$` pattern -- they might be single-word, start with a digit, or contain invalid characters.
**Why it happens:** Engram triggers/titles are free-form text. A trigger like "always use TypeScript" would naively become `always-use-typescript` (valid) but "React" would become `react` (invalid -- needs 2+ segments).
**How to avoid:** The name generator must guarantee at least 2 hyphen-separated segments. If the natural name is single-word, append the engram type (e.g., `react-preference`) or domain (e.g., `react-pattern`). Always validate the generated name against the regex before use.
**Warning signs:** `json.loads()` of plugin.json at publish time fails schema validation on the `name` field.

### Pitfall 2: Missing publish_min_evidence Config Key
**What goes wrong:** The gate check for evidence >= 3 uses a config key `publish_min_evidence` that doesn't exist in the current DEFAULT_CONFIG dict.
**Why it happens:** `config.py` has `publish_min_confidence: 0.7` but not `publish_min_evidence`. The unified-design.md specifies it but it was never added in Phases 1-2.
**How to avoid:** Add `publish_min_evidence: 3` to DEFAULT_CONFIG in config.py as part of the promote implementation.
**Warning signs:** Gate check always uses hardcoded fallback value instead of config.

### Pitfall 3: Engram Index Missing Source Field
**What goes wrong:** BRG-01 requires checking `source != "registry"` but the current `build_index_entry()` function doesn't include a `source` field.
**Why it happens:** Registry-sourced engrams don't exist yet (Phase 4). Current engrams have no source field.
**How to avoid:** The gate check should treat missing/None source as "not registry" -- i.e., `entry.get("source") == "registry"` returns False when source is absent. This is safe because only Phase 4 would introduce registry-sourced engrams.
**Warning signs:** Users can't promote any engrams because the source check fails on missing field.

### Pitfall 4: analyze-agent-codebase Question Files
**What goes wrong:** `/analyze-agent-codebase` skill references 7 question cluster files and 1 synthesis file. If these aren't copied alongside SKILL.md, the command silently produces empty/wrong analysis.
**Why it happens:** Other skills are single-file (just SKILL.md). This skill has 8 files total and the install script must copy all of them.
**How to avoid:** The install.sh skills copy step must use wildcard (`cp "$skill_dir"* ...`) not just copy SKILL.md.
**Warning signs:** `/analyze-agent-codebase` runs but clusters produce empty output because question files are missing.

### Pitfall 5: SKILL.md Description Must Contain TRIGGER Clause
**What goes wrong:** Promoted engram's SKILL.md has a description field that doesn't contain the required `TRIGGER when` substring.
**Why it happens:** The plugin.schema.json `description` field has a pattern `TRIGGER when:?` (regex) and minLength of 50. Engram triggers are typically short phrases that don't naturally include this pattern.
**How to avoid:** The promote command must construct the description by combining engram content into a descriptive sentence, then appending `TRIGGER when: <derived scenarios>`. Example: `"Batch sizing for CUDA OOM prevention in ML training pipelines. TRIGGER when: configuring batch sizes for GPU training, debugging CUDA out-of-memory errors, optimizing GPU memory usage."`
**Warning signs:** Schema validation fails on description field during publish.

### Pitfall 6: Plugin.json commit_date Format
**What goes wrong:** Date is written as `2026-04-14` (ISO) but schema requires `DD-MM-YYYY` format (pattern `^\d{2}-\d{2}-\d{4}$`).
**Why it happens:** Python's `date.today().isoformat()` produces `YYYY-MM-DD`. The Lens schema uses European date format.
**How to avoid:** Use `date.today().strftime("%d-%m-%Y")` explicitly.
**Warning signs:** Schema validation fails on commit_date field.

## Code Examples

### Engram-to-Plugin.json Field Mapping
```python
# Source: plugin.schema.json required fields + engram index structure
def _build_plugin_json(skill_name, entry, frontmatter, body):
    """Map engram fields to plugin.json schema fields."""
    trigger = entry.get("trigger", "")
    kind = entry.get("kind", "preference")
    domain = entry.get("domain", "general")
    evidence_count = entry.get("evidence_count", 1)

    # Description: short summary + TRIGGER clause (schema requires both)
    description = _build_description(trigger, body, kind)

    # Category mapping from engram type
    category_map = {
        "preference": ["architecture"],
        "correction": ["architecture"],
        "procedure": ["execution-control"],
        "domain_fact": ["architecture"],
        "tool_pattern": ["tools"],
        "error_recipe": ["execution-control"],
    }
    category = category_map.get(kind, ["architecture"])

    # Git metadata (auto-detect, handle missing gracefully)
    author = _git_config("user.name") or "unknown"
    repository = _git_repo_name() or "unknown"
    source_hash = _git_short_hash()  # None if not a git repo

    return {
        "name": skill_name,
        "description": description,
        "author": author,
        "repository": repository,
        "category": category,
        "source": "engram",  # D-01: distinguishes promoted engrams
        "commit_date": date.today().strftime("%d-%m-%Y"),
        "source_hash": source_hash,
    }
```
[VERIFIED: plugin.schema.json required fields, engram index fields from lib/index.py build_index_entry()]

### Kebab-Case Name Generation
```python
# Source: plugin.schema.json name pattern + D-03 requirements
def _generate_skill_name(entry, frontmatter):
    """Generate a valid kebab-case skill name from engram content.

    Must match: ^[a-z][a-z0-9]*(-[a-z0-9]+)+$
    i.e., at least 2 hyphen-separated segments, starting with letter.
    """
    trigger = entry.get("trigger", "")
    kind = entry.get("kind", "preference")
    domain = entry.get("domain", "general")

    # Start with trigger text
    raw = trigger.strip().strip('"')

    # Lowercase, replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower())
    slug = slug.strip("-")

    # Remove stop words to shorten
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be",
                  "to", "of", "in", "for", "on", "with", "at", "by",
                  "and", "or", "but", "not", "it", "this", "that"}
    parts = [p for p in slug.split("-") if p and p not in stop_words]

    # Ensure at least 2 segments
    if len(parts) < 2:
        parts.append(kind.replace("_", "-"))  # e.g., "react" -> "react-preference"

    # Truncate to reasonable length (keep first 5 meaningful segments)
    parts = parts[:5]

    # Ensure first char is a letter
    if parts and parts[0] and not parts[0][0].isalpha():
        parts.insert(0, kind.split("_")[0])  # prepend kind prefix

    slug = "-".join(parts)

    # Truncate to 60 chars at word boundary
    if len(slug) > 60:
        slug = slug[:60].rsplit("-", 1)[0]

    return slug
```
[VERIFIED: plugin.schema.json name pattern `^[a-z][a-z0-9]*(-[a-z0-9]+)+$`]

### Published.json Delta Tracking Structure
```python
# Source: unified-design.md publish tracking spec
# _analysis/.published.json format:
{
    "skill-name": {
        "registry-name": {
            "published_at": "2026-04-14T12:00:00Z",
            "content_hash": "sha256-hex-string"
        }
    }
}

def _compute_content_hash(skill_dir):
    """Compute SHA256 hash of plugin.json + SKILL.md for delta tracking."""
    h = hashlib.sha256()
    for filename in ["plugin.json", "SKILL.md"]:
        filepath = skill_dir / filename
        if filepath.exists():
            h.update(filepath.read_bytes())
    return h.hexdigest()[:12]  # Short hash for readability
```
[VERIFIED: unified-design.md lines 396-405 for .published.json format]

### Frontmatter Parser (Existing Pattern)
```python
# Source: existing Prism codebase pattern (zero-dependency YAML frontmatter)
def _parse_frontmatter(content):
    """Parse markdown with YAML frontmatter. Returns (dict, body_string)."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            frontmatter[key.strip()] = value.strip().strip('"').strip("'")

    return frontmatter, parts[2].strip()
```
[VERIFIED: CLAUDE.md "Custom YAML frontmatter parser" pattern; existing use in engram format]

## Slash Command Modification Details

### Commands Copied As-Is (Tier 1)

| Command | Files | Reason No Changes Needed |
|---------|-------|--------------------------|
| analyze-agent-codebase | SKILL.md + 7 question files + 1 synthesis file | No Lens/Prosus references; operates on `_analysis/` only |
| mine-history | SKILL.md | No Lens/Prosus references; operates on git history + `_analysis/` |
| mine-design | SKILL.md | No Lens/Prosus references; operates on source code + `_analysis/` |
| curate-skills | SKILL.md | No Lens/Prosus references; operates on `_analysis/extracted_skills_*/` |

### Commands with Minor Edits (Tier 2)

| Command | Changes Needed |
|---------|----------------|
| run-analysis-pipeline | Line ~68: change `publish-skills-github` or `publish-skills-cloudflare` to `publish-skills` |
| run-history-pipeline | Line ~41: same publish reference change |
| extract-skills | Line ~129: change "Prosus / portfolio company" to "your organization"; line ~134: keep internal/external source logic as-is (Lens pattern, matches schema) |
| synthesize | Line ~143: same Prosus reference removal |
| synthesize-decisions | Line ~154: same Prosus reference removal |

### Commands Requiring Heavy Rewrite (Tier 3)

| Command | Source Commands | Key Changes |
|---------|----------------|-------------|
| publish-skills | publish-skills-cloudflare + publish-skills-github | Worker-only API path; registry URL from config not env vars; delta tracking via `.published.json`; `--registry NAME` and `--all` flags; no GitHub CI workflow generation |
| advise-skills | advise-skills | Use local `skill-registry.json` if available; remove Lens install.sh references; remove GitHub-direct platform detection; graceful "no registry configured" message |
| audit-code | audit-code | Same as advise-skills changes |

## State of the Art

| Old Approach (Lens) | Current Approach (Prism) | Impact |
|---------------------|--------------------------|--------|
| Two separate publish commands (cloudflare + github) | One unified `/publish-skills` | Simpler UX; Worker-only per PROJECT.md |
| `.claude/skill-registry.json` installed by Lens install.sh | Local `skill-registry.json` from cache; full registry config in Phase 4 | Phase 3: local fallback; Phase 4: multi-registry |
| Env vars for registry config (`REGISTRY_API_URL`, `REGISTRY_TOKEN`) | Config-based (`~/.prism/config.json` registry settings) | More discoverable, persists across sessions |
| No engram-to-skill bridge | `prism promote` command | Knowledge flows from personal to team |
| `source` field: "internal" or "external [URL]" | Added "engram" source type | Provenance tracking for promoted knowledge |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Content hash using SHA256 of plugin.json + SKILL.md concatenated is sufficient for delta tracking | Code Examples / Published.json | Low -- any deterministic hash works; SHA256 is standard |
| A2 | The Prosus-specific "internal/external" source prompt in extract-skills, synthesize, and synthesize-decisions should be generalized but the internal/external choice itself should remain | Slash Command Modification Details | Low -- the source field schema still requires internal/external for extracted skills; only promoted engrams use "engram" |
| A3 | 4 Lens commands can be copied completely as-is without any modifications | Tier 1 classification | Medium -- may discover minor issues during implementation; verified by reading all SKILL.md files |
| A4 | The `_analysis/.published.json` short hash (12 chars) is sufficient to detect changes | Code Examples | Low -- 12 hex chars = 48 bits of entropy; collision probability negligible for this use case |

## Open Questions

1. **Registry URL configuration key name**
   - What we know: `config.py` has `registry_url: ""` as default; unified-design.md describes multi-registry in `~/.prism/registries.json`
   - What's unclear: For Phase 3, should `/publish-skills` read from `config.json`'s `registry_url` key, or from a separate `registries.json`?
   - Recommendation: Use `config.json` `registry_url` for Phase 3 (single registry). Phase 4 introduces `registries.json` for multi-registry. The publish command in Phase 3 should check `config.json` and if empty, tell user to configure with `prism config registry_url <URL>`.

2. **Registry token storage**
   - What we know: Lens uses `REGISTRY_TOKEN` env var; Prism config has no token field
   - What's unclear: Where does the API token live in Phase 3?
   - Recommendation: Keep `REGISTRY_TOKEN` env var for Phase 3 (consistent with Lens pattern, avoids storing secrets in config.json). Phase 4's `prism registry add` can handle token storage.

3. **SKILL.md body content for promoted engrams**
   - What we know: Regular extraction commands produce rich SKILL.md with Key Decisions, Anti-patterns, Structural Template sections
   - What's unclear: How rich should a promoted engram's SKILL.md be? Engrams have simpler structure (trigger + body + evidence).
   - Recommendation: Keep it simple -- the engram body becomes the content. Format: title from trigger, "Learned from N observations" subtitle, body content as-is. The user can enhance it via `/curate-skills` before publishing.

## Sources

### Primary (HIGH confidence)
- `/Users/gaurav/codes/Lens/schemas/plugin.schema.json` -- Full schema with required fields, patterns, valid categories
- `/Users/gaurav/codes/Lens/.claude/skills/` -- All 13 SKILL.md files read in full, classified by modification level
- `/Users/gaurav/codes/Lens/CLAUDE.md` -- Complete Lens project structure and conventions
- `/Users/gaurav/codes/Lens/skills/claude-code/anthropic-api-prompt-cache-preservation/` -- Example plugin.json + SKILL.md format
- `/Users/gaurav/codes/prism/lib/commands.py` -- Current command patterns, _setup_slash_commands()
- `/Users/gaurav/codes/prism/lib/cli.py` -- Current CLI router structure
- `/Users/gaurav/codes/prism/lib/index.py` -- Engram index API (load_index, get_entry, build_index_entry)
- `/Users/gaurav/codes/prism/lib/config.py` -- Config defaults, PRISM_HOME path
- `/Users/gaurav/codes/prism/lib/sync.py` -- Push layer with publish-ready section (lines 98-107)
- `/Users/gaurav/codes/prism/install.sh` -- Current install steps, skills directory creation
- `/Users/gaurav/codes/prism/unified-design.md` -- Promote command spec (lines 573-601), publish flow (lines 603-620), .published.json format (lines 396-405)
- `/Users/gaurav/codes/prism/.planning/phases/03-bridge-slash-commands/03-CONTEXT.md` -- Locked decisions D-01, D-02, D-03

### Secondary (MEDIUM confidence)
- `/Users/gaurav/codes/Lens/skill-registry.json` -- Registry index format (first 30 lines verified)
- `/Users/gaurav/codes/prism/unified-design.md` -- Overall design intent for bridge and slash commands

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib Python, all verified against codebase
- Architecture: HIGH -- patterns derived from reading actual source files, schema, and design docs
- Pitfalls: HIGH -- derived from concrete findings (missing config key, schema pattern mismatch, date format)
- Slash command classification: HIGH -- all 13 Lens SKILL.md files read and classified

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (stable -- all source material is local, no external API dependencies)
