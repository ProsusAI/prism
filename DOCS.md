# Prism Technical Documentation

Comprehensive reference for Prism's architecture, data formats, pipelines, and configuration.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Installation](#installation)
- [Project Initialization](#project-initialization)
- [Observation Pipeline](#observation-pipeline)
- [Extraction Pipeline](#extraction-pipeline)
- [Engram Lifecycle](#engram-lifecycle)
- [Context Injection](#context-injection)
- [MCP Server](#mcp-server)
- [CLI Reference](#cli-reference)
- [Slash Commands](#slash-commands)
- [Engram-to-Skill Promotion](#engram-to-skill-promotion)
- [Team Registry](#team-registry)
- [Data Formats](#data-formats)
- [Configuration Reference](#configuration-reference)
- [Security](#security)
- [File System Layout](#file-system-layout)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

Prism sits between Claude Code and a knowledge store. It has three layers:

```
Claude Code Session
  |                    |
  | hooks (observe)    | MCP (query)
  v                    v
+----------------------------------+
|            Prism                  |
|                                  |
|  Observations -> Extraction ->   |
|  Engrams -> Context Injection    |
|                                  |
|  Engrams -> Promotion -> Skills  |
|  Skills -> Registry (team)       |
+----------------------------------+
  |
  v
~/.prism/  (file-based storage)
```

**Personal layer**: Hooks capture tool usage as observations. An extraction pipeline (Haiku proposes, Sonnet validates) converts patterns into engrams. Engrams flow back into Claude Code through `.claude/prism.md` (push) and MCP tools (pull).

**Team layer**: High-confidence engrams can be promoted to skill format. Slash commands mine codebases and git history for additional skills. Skills are published to a Cloudflare Worker-backed registry that teams query.

**Key constraints**:
- Zero runtime Python dependencies (stdlib only)
- Hooks never block Claude Code (exit 0 always, background processing)
- AI calls go through the `claude` CLI, not the Anthropic SDK
- All data is files on disk (JSON, JSONL, Markdown) -- no database

---

## Installation

### Prerequisites

| Requirement | Version | Required |
|-------------|---------|----------|
| Python | 3.12+ | Yes |
| git | any | Yes |
| Claude Code | current | Yes |
| claude CLI | latest | Yes (for extraction) |

### Install

```bash
git clone <repo-url> && cd prism
./install.sh
```

### What `install.sh` does

1. **Checks prerequisites**: python3 (hard fail), git (hard fail), claude CLI (soft warning), Python 3.12+ (recommended warning)
2. **Creates directory tree**: `~/.prism/{global/engrams, archive, hooks, agents, lib, skills, projects, schemas}`
3. **Copies source files**: hooks/, agents/, lib/*.py, skills/*/, schemas/*.json, templates/
4. **Writes defaults** (only if missing):
   - `config.json` with default thresholds
   - `index.json` with empty engram list
   - `constitution.md` from template (never overwritten on upgrades)
5. **Creates CLI symlink**: `~/.local/bin/prism` -> `~/.prism/prism`
6. **Verifies PATH**: warns if `~/.local/bin` is not in `$PATH`

The installer is idempotent. Re-running updates code but preserves config, index, constitution, and project data.

### Verify

```bash
prism --help
```

---

## Project Initialization

```bash
cd your-project
prism init
```

`prism init` configures four integration points:

### 1. Hooks

Adds PreToolUse and PostToolUse hooks to `~/.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "type": "command",
      "command": "~/.prism/hooks/capture.sh pre"
    }],
    "PostToolUse": [{
      "type": "command",
      "command": "~/.prism/hooks/capture.sh post",
      "async": true
    }]
  }
}
```

PostToolUse runs async to avoid blocking Claude Code.

### 2. MCP Server

Registers the Prism MCP server so Claude Code can query knowledge mid-session:

```json
{
  "mcpServers": {
    "prism": {
      "type": "stdio",
      "command": "python3",
      "args": ["~/.prism/lib/mcp_server.py"]
    }
  }
}
```

### 3. Slash Commands

Symlinks `~/.prism/skills/` into the project's `.claude/skills/` directory, making all Prism slash commands available.

### 4. Context File

Creates an initial `.claude/prism.md` with any existing knowledge for the project.

### Project Detection

Prism identifies projects by a stable hash derived from git metadata. Detection order:

1. `PRISM_PROJECT_ID` environment variable
2. `.prism_project_id` file in project root (written by `prism init`)
3. SHA256 of git remote URL (first 12 hex chars)
4. SHA256 of git repo root path
5. `"global"` (fallback)

---

## Observation Pipeline

### Flow

```
Claude Code tool call
  -> Hook fires (capture.sh)
    -> Reads JSON from stdin
    -> Pipes to python3 capture.py
      -> Scrubs secrets
      -> Truncates to safe length
      -> Appends to observations.jsonl
      -> Checks extraction trigger threshold
```

### What gets captured

Every PreToolUse and PostToolUse event produces an observation:

```json
{
  "timestamp": "2026-04-14T12:00:00Z",
  "event": "tool_start",
  "tool": "Write",
  "input_summary": "Write to src/config.ts: export const ...",
  "session": "abc123",
  "project_id": "f4a3b2c1d0e9",
  "source": "claude_code"
}
```

Observations are appended to `~/.prism/projects/<project_id>/observations.jsonl` using atomic `O_APPEND` writes.

### Hook safety

- `capture.sh` always exits 0, even on errors
- Processing happens in the background (no user-perceived delay)
- Stdin piped directly to a single Python process (avoids spawning multiple interpreters)
- Secret scrubbing runs before any data is written to disk

---

## Extraction Pipeline

Extraction converts raw observations into structured engrams using a two-phase AI pipeline.

### Trigger

Extraction runs when:
- Observation count crosses `extract_threshold` (default: 15) -- triggered automatically
- User runs `prism extract` manually

### Phase 1: Proposal (Haiku)

The extractor agent (`agents/extractor.md`) reads recent observations and proposes candidate engrams:

```
Observations (JSONL) -> claude --model haiku -> Candidate engrams (JSON)
```

Each candidate has: kind, trigger, tags, domain, confidence (initial), content.

**Engram kinds**:
| Kind | Description |
|------|-------------|
| `preference` | User consistently chooses a specific approach |
| `correction` | User explicitly corrected a behavior |
| `procedure` | Multi-step workflow the user follows |
| `domain_fact` | Domain-specific knowledge relevant to the project |
| `tool_pattern` | Specific way the user uses a tool |
| `error_recipe` | Known solution to a recurring error |

### Phase 2: Validation (Sonnet)

The validator agent (`agents/validator.md`) reviews each candidate through 4 safety gates:

1. **Constitution check** -- Does this violate any safety principle in `constitution.md`?
2. **Evidence check** -- Is there enough observation evidence to support this?
3. **Contradiction check** -- Does this conflict with existing engrams?
4. **Safety check** -- Could this cause harm if applied broadly?

Only candidates passing all 4 gates are written as engrams.

### Session Review

A separate reviewer agent (`agents/reviewer.md`) scans Claude Code session transcripts for conversational insights (corrections, preferences, decisions) that hooks might miss:

```bash
prism review --session <session-id>
```

The review interval is configurable (`review_interval`, default: every 5 observations).

---

## Engram Lifecycle

Engrams are living knowledge units with confidence scores that change over time.

### Confidence model

- **Initial confidence**: Set by the extraction pipeline (typically 0.4-0.7)
- **Reinforcement**: When the same pattern is observed again, confidence increases. MCP queries also provide a small boost (0.02 per query, capped at 0.95)
- **Decay**: Without reinforcement, confidence drops by `decay_rate_per_week` (default: 0.02) per week
- **Archive**: Engrams below `archive_threshold` (default: 0.2) are moved to `~/.prism/archive/`
- **Pinning**: Pinned engrams never decay

### Manual management

```bash
prism learn "Always use pnpm in this project"          # Create engram (project scope)
prism learn "Prefer functional components" --scope global  # Create engram (global scope)
prism correct <id> "Use vitest, not jest"               # Supersede with correction
prism forget <id>                                        # Archive immediately
prism maintain                                           # Run decay cycle
```

All manual operations auto-sync `.claude/prism.md` so changes take effect in the next Claude Code session.

### Bootstrapping from history

```bash
prism analyze-sessions --last 10        # Analyze last 10 sessions
prism analyze-sessions --since 2026-04-01  # Analyze sessions since date
prism analyze-sessions --all --extract  # Analyze all and run extraction
prism analyze-sessions --list           # Just list available sessions
```

This scans existing Claude Code session transcripts and creates observations from them, which can then be extracted into engrams.

---

## Context Injection

Prism uses two channels to get knowledge into Claude Code sessions.

### Push: `.claude/prism.md`

Generated by `prism sync`. Claude Code reads this file as project instructions at session start.

**Content priority order**:
1. Corrections (highest priority -- Claude must not repeat mistakes)
2. Pinned entries
3. Session-validated imports
4. Top preferences (sorted by confidence)

**Format**:

```markdown
<!-- Updated: 2026-04-14T12:00:00Z | 8 pushed, 24 via MCP -->

## Corrections (do NOT repeat these)
- [global] When asked about testing: Use vitest, not jest (0.85)

## Pinned
- [project] Deploy procedure: always run migrations first (0.90)

## Key Preferences
- [project] Use pnpm for package management (0.75)
- [global] Prefer TypeScript strict mode (0.72)

---
*24 additional entries available via prism_search MCP tool*
```

Size is controlled by `max_context_lines` (default: 100).

### Pull: MCP Server

For mid-session queries. Claude calls MCP tools when it needs specific knowledge beyond what's in `prism.md`. See [MCP Server](#mcp-server).

---

## MCP Server

The MCP server runs as a stdio subprocess of Claude Code, speaking JSON-RPC 2.0 (protocol version `2025-03-26`).

### Tools

#### `prism_search`

Full-text search across all engrams using token-based Jaccard similarity scoring.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Search query |
| `project_id` | string | auto-detect | Filter by project |
| `limit` | number | 5 | Max results |

Returns scored results with trigger, tags, confidence, and relevance score. Boosts error-related queries toward `error_recipe` entries.

#### `prism_get`

Retrieve a specific engram by ID.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `entry_id` | string | required | Engram ID |

Returns full entry with all metadata and content.

#### `prism_relevant`

Find entries relevant to the current context (file being edited, tool being used).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `context` | string | required | Current context description |
| `project_id` | string | auto-detect | Filter by project |
| `limit` | number | 5 | Max results |

#### `prism_record`

Record an observation directly from the Claude Code conversation.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | string | required | Observation text |
| `project_id` | string | auto-detect | Target project |

Appends to observations.jsonl and triggers sync if thresholds are met.

### Implementation notes

- stdout is exclusively for JSON-RPC messages (no stray prints)
- All logging goes to stderr
- stdout buffering is explicitly handled (flush after every write)
- Each MCP query provides a small confidence reinforcement (0.02) to matched entries

---

## CLI Reference

### Commands

| Command | Description |
|---------|-------------|
| `prism init` | Initialize Prism for current project |
| `prism status [--project ID]` | Show active knowledge and project info |
| `prism learn <text> [--scope project\|global]` | Manually create an engram |
| `prism correct <id> <text>` | Supersede engram with correction |
| `prism forget <id>` | Archive an engram |
| `prism extract [--project ID]` | Run extraction pipeline on observations |
| `prism review --session ID [--project ID]` | Analyze a session transcript |
| `prism analyze-sessions [flags]` | Bootstrap from existing Claude Code sessions |
| `prism sync [--project ID] [--output-dir DIR]` | Generate .claude/prism.md |
| `prism maintain` | Run confidence decay and archive expired engrams |
| `prism promote <id> [--name NAME]` | Convert engram to publishable skill format |
| `prism log [--last N] [--extractions] [--insights] [--json]` | Show recent observations |
| `prism procedures [--project ID]` | List procedure engrams with statistics |
| `prism config [key [value]]` | Get or set configuration |

### `prism analyze-sessions` flags

| Flag | Description |
|------|-------------|
| `--all` | Analyze all available sessions |
| `--extract` | Run extraction after analysis |
| `--dry-run` | Show what would be analyzed without doing it |
| `--list` | List available sessions |
| `--since DATE` | Only sessions after this date |
| `--last N` | Only the N most recent sessions |

### `prism log` flags

| Flag | Description |
|------|-------------|
| `--last N` | Show last N entries (default: 10) |
| `--extractions` | Show extraction events only |
| `--insights` | Show session review insights only |
| `--json` | Output as JSON |

---

## Slash Commands

Prism includes 12 slash commands available in Claude Code after `prism init`. These are Claude Code skills (SKILL.md files) that Claude follows as step-by-step instructions.

### Analysis & Mining

| Command | Description |
|---------|-------------|
| `/analyze-agent-codebase` | Deep 6-cluster analysis of an agentic codebase (architecture, state, tools, error handling, coordination, evaluation) |
| `/mine-history` | Extract incident patterns from git history |
| `/mine-design` | Extract architectural design decisions from code |

### Extraction & Synthesis

| Command | Description |
|---------|-------------|
| `/extract-skills` | Transform codebase analysis reports into framework-agnostic skills |
| `/synthesize` | Promote incident clusters into publishable skills |
| `/synthesize-decisions` | Convert design decision reports into skills |

### Quality & Curation

| Command | Description |
|---------|-------------|
| `/curate-skills` | Quality review pass on extracted skills (dedup, accuracy, formatting) |

### Publishing & Querying

| Command | Description |
|---------|-------------|
| `/publish-skills` | Publish skills to team registry with delta tracking |
| `/advise-skills` | Query registries for skills relevant to a question |
| `/audit-code` | Audit current codebase against registry skill patterns |

### Pipelines (orchestrate multiple steps)

| Command | Description |
|---------|-------------|
| `/run-analysis-pipeline` | Full pipeline: mine -> analyze -> extract -> curate -> publish |
| `/run-history-pipeline` | History pipeline: mine-history -> synthesize -> publish |

### Output

All extraction and analysis commands write to `_analysis/` in the project root:
- `_analysis/extracted_skills_codebase/` -- Skill directories with `plugin.json` + `SKILL.md`
- `_analysis/.published.json` -- Delta tracking for published skills

---

## Engram-to-Skill Promotion

`prism promote` bridges personal knowledge (engrams) to team knowledge (skills).

### Gate checks

Promotion requires:
- Confidence >= `publish_min_confidence` (default: 0.7)
- Evidence count >= `publish_min_evidence` (default: 3)
- Source is not `"registry"` (can't re-promote imported skills)

### What it produces

For an engram about TypeScript strict mode:

```
_analysis/extracted_skills_codebase/typescript-strict-mode/
  plugin.json    # Metadata (name, description, author, category, source: "engram")
  SKILL.md       # Instructions with frontmatter
```

**plugin.json** fields:
- `name`: Auto-generated kebab-case (or `--name` override)
- `description`: Includes `TRIGGER when:` clause (required by schema)
- `author`: From `git config user.name`
- `repository`: From `git remote get-url origin`
- `category`: Mapped from engram kind (preference -> architecture, procedure -> execution-control, etc.)
- `source`: `"engram"` (distinguishes promoted personal knowledge from other sources)
- `commit_date`: DD-MM-YYYY format
- `source_hash`: Current git short hash

### After promotion

```bash
/curate-skills     # Quality review
/publish-skills    # Publish to registry
```

---

## Team Registry

> Phase 4 (not yet implemented). This section describes the planned design.

Teams share skills through registries backed by GitHub repos and Cloudflare Workers.

### Architecture

```
prism CLI  ->  Cloudflare Worker  ->  GitHub Repo
  (publish)     (API proxy)          (storage, PRs, CI)
  (query)       (auth, cache)        (skill-registry.json)
```

### Planned commands

```bash
prism registry create          # Set up new registry (GitHub repo + Worker)
prism registry add <url>       # Add a registry
prism registry remove <name>   # Remove a registry
prism registry list            # List configured registries
prism registry default <name>  # Set default registry
prism registry token create    # Generate API token
prism registry token revoke    # Revoke API token
```

### Multi-registry support

- Read from all configured registries (merged results, tagged by source)
- Write to a specific registry (delta tracked per-registry)
- 24h TTL cache for fetched `skill-registry.json`

---

## Data Formats

### Observations (JSONL)

Location: `~/.prism/projects/<project_id>/observations.jsonl`

One JSON object per line:

```json
{"timestamp":"2026-04-14T12:00:00Z","event":"tool_end","tool":"Write","input_summary":"Write to src/index.ts: ...","session":"abc123","project_id":"f4a3b2c1d0e9","source":"claude_code"}
```

### Engram files (Markdown + YAML frontmatter)

Location: `~/.prism/global/engrams/<id>.md` or `~/.prism/projects/<project_id>/engrams/<id>.md`

```markdown
---
id: prism-1713100800-a1b2c3
kind: preference
trigger: "Always use pnpm for package management"
tags:
  - nodejs
  - package-manager
domain: javascript
confidence: 0.75
evidence_count: 5
scope: project
project_id: f4a3b2c1d0e9
---

Use pnpm instead of npm for all Node.js projects. It's faster,
uses less disk space through hard linking, and has stricter
dependency resolution that prevents phantom dependencies.
```

### Index (JSON)

Location: `~/.prism/global/engrams/index.json`

```json
{
  "engrams": [
    {
      "id": "prism-1713100800-a1b2c3",
      "kind": "preference",
      "trigger": "Always use pnpm for package management",
      "tags": ["nodejs", "package-manager"],
      "domain": "javascript",
      "confidence": 0.75,
      "evidence_count": 5,
      "success_count": 4,
      "failure_count": 0,
      "source": "hook",
      "scope": "project",
      "project_id": "f4a3b2c1d0e9",
      "path": "projects/f4a3b2c1d0e9/engrams/prism-1713100800-a1b2c3.md",
      "last_observed": "2026-04-14",
      "decay_applied": "2026-04-14",
      "pinned": false
    }
  ]
}
```

The index is protected by file locking (`fcntl.flock`) with atomic writes (write to temp file, then `os.rename`). A `.bak` backup is created on every write. Stale locks older than 10 minutes are automatically broken.

### Skill plugin.json

```json
{
  "name": "typescript-strict-mode",
  "description": "Always enable TypeScript strict mode for full type safety. TRIGGER when: setting up a new TypeScript project, configuring tsconfig.json, reviewing type safety settings.",
  "author": "Your Name",
  "repository": "org/repo",
  "category": ["architecture"],
  "source": "engram",
  "commit_date": "14-04-2026",
  "source_hash": "a1b2c3d"
}
```

### Published delta tracking

Location: `_analysis/.published.json`

```json
{
  "typescript-strict-mode": {
    "default": {
      "published_at": "2026-04-14T12:00:00Z",
      "content_hash": "a1b2c3d4e5f6"
    }
  }
}
```

Content hash is SHA256 of plugin.json + SKILL.md concatenated, first 12 hex chars.

---

## Configuration Reference

Location: `~/.prism/config.json`

| Key | Default | Description |
|-----|---------|-------------|
| `extract_threshold` | 15 | Number of observations before auto-extraction triggers |
| `decay_rate_per_week` | 0.02 | Confidence reduction per week without observation |
| `archive_threshold` | 0.2 | Archive engrams below this confidence |
| `publish_min_confidence` | 0.7 | Minimum confidence for skill promotion |
| `publish_min_evidence` | 3 | Minimum evidence count for skill promotion |
| `max_context_lines` | 100 | Maximum lines in generated .claude/prism.md |
| `review_interval` | 5 | Observations between automatic session reviews (0 = disabled) |
| `review_timeout` | 60 | Seconds before review subprocess is killed |
| `registry_url` | `""` | Team registry Worker URL |
| `scrub_patterns` | (see below) | Additional secret detection regex patterns |
| `block_patterns` | (see below) | Adversarial prompt detection patterns |

### Secret scrub patterns (built-in)

These are hardcoded as a security baseline and cannot be disabled:

- API keys, secrets, tokens, passwords, credentials (`key=value` patterns)
- Bearer tokens
- OpenAI keys (`sk-*`)
- GitHub PATs (`ghp_*`, `gho_*`, `ghs_*`, `github_pat_*`)
- Slack tokens (`xoxb-*`)
- AWS access keys (`AKIA*`)
- URLs with embedded credentials
- Private keys (PEM format)
- JWTs (`eyJ*`)

Additional patterns can be added via `scrub_patterns` in config.

### Environment variables

| Variable | Description |
|----------|-------------|
| `PRISM_HOME` | Override default `~/.prism` location |
| `PRISM_PROJECT_ID` | Override auto-detected project ID |
| `REGISTRY_TOKEN` | Bearer token for registry API authentication |

---

## Security

### Observation scrubbing

All captured observations are scrubbed before writing to disk. The scrubber runs a set of hardcoded baseline patterns (cannot be disabled) plus any user-configured patterns. Matched content is replaced with `[REDACTED]`.

### Adversarial prompt detection

Block patterns detect attempts to manipulate the extraction pipeline (e.g., "expand access", "grant permissions"). Observations matching these patterns are discarded.

### Constitution

`~/.prism/constitution.md` defines safety principles that the validation pipeline checks against. It is created from a template on first install and never overwritten by upgrades.

### File safety

- Index writes use file locking + atomic rename (no partial writes)
- Hooks never block Claude Code (exit 0 always)
- Subprocess calls use timeouts (default: 5s for git, 60s for reviews)
- No network calls in the personal layer (extraction uses local `claude` CLI)

---

## File System Layout

```
~/.prism/
  prism                          # CLI entry point
  config.json                    # User configuration
  constitution.md                # Safety principles (never overwritten)
  lib/                           # Python library
    cli.py                       # Command router
    commands.py                  # Command implementations
    config.py                    # Config management
    capture.py                   # Observation processor
    extract.py                   # Extraction pipeline
    index.py                     # Index management (load/save/lock)
    mcp_server.py                # MCP server (stdio, JSON-RPC)
    sync.py                      # Context sync (.claude/prism.md)
    review.py                    # Session review
    sessions.py                  # Session analysis
    project.py                   # Project detection
    trigger.py                   # Auto-extraction trigger
    bridge.py                    # Engram-to-skill promotion
    scrub.py                     # Secret scrubbing
  hooks/
    capture.sh                   # Claude Code hook (PreToolUse/PostToolUse)
  agents/
    extractor.md                 # Phase 1 extraction prompt (Haiku)
    validator.md                 # Phase 2 validation prompt (Sonnet)
    reviewer.md                  # Session review prompt
  skills/                        # 12 slash commands
    analyze-agent-codebase/      # (8 files: SKILL.md + 7 question clusters)
    mine-history/
    mine-design/
    extract-skills/
    synthesize/
    synthesize-decisions/
    curate-skills/
    publish-skills/
    advise-skills/
    audit-code/
    run-analysis-pipeline/
    run-history-pipeline/
  schemas/
    plugin.schema.json           # Skill validation schema
  global/
    engrams/
      index.json                 # Master engram index
      *.md                       # Global engram files
  projects/
    <project-hash>/
      observations.jsonl         # Raw observations
      engrams/
        *.md                     # Project-scoped engrams
  archive/                       # Archived (decayed) engrams
```

---

## Troubleshooting

### `prism: command not found`

Ensure `~/.local/bin` is in your PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Hooks not firing

Check that hooks are registered:

```bash
cat ~/.claude/settings.local.json | python3 -m json.tool
```

Look for `PreToolUse` and `PostToolUse` entries pointing to `~/.prism/hooks/capture.sh`. If missing, run `prism init` again.

### MCP server not connecting

Check stderr output:

```bash
python3 ~/.prism/lib/mcp_server.py 2>/tmp/prism-mcp.log
# Then check /tmp/prism-mcp.log
```

Common issue: stray `print()` statements in lib code corrupt the JSON-RPC stream. All output must go to stderr.

### Extraction not triggering

Check observation count:

```bash
prism log --last 5
wc -l ~/.prism/projects/<your-project>/observations.jsonl
```

Extraction triggers at `extract_threshold` observations (default: 15). Run manually with `prism extract`.

### Engrams not appearing in Claude Code

Run sync manually and check the output:

```bash
prism sync
cat .claude/prism.md
```

If `.claude/prism.md` is empty, check `prism status` to verify engrams exist for the current project.

### Stale lock on index.json

If a process crashed while writing, you may see lock errors. Prism auto-breaks locks older than 10 minutes. To force:

```bash
rm ~/.prism/global/engrams/index.json.lock 2>/dev/null
```
