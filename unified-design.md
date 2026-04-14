# Prism: Design Document

## What is Prism?

Prism is a knowledge layer for Claude Code. It does two things:

1. **Learns your preferences** -- hooks observe how you work, extract patterns into *engrams* (living, decaying personal knowledge), and inject them into every session. Claude Code remembers what you've taught it.

2. **Shares team knowledge** -- pipelines extract architectural best practices from codebases and git history into *skills* (immutable, reviewed, team-wide knowledge), published to a shared registry. Anyone with access queries the registry.

When a personal engram proves robust enough, you *promote* it to a skill and publish it. Knowledge flows from individual to team.

### Derived from

Prism unifies two existing projects into a single coherent tool:

- **[Engram](https://github.com/ProsusAI/engram)** -- personal knowledge system for AI coding assistants. Zero-dependency Python, hook-based observation capture, two-phase extraction (Haiku proposes, Sonnet validates through 4 safety gates), hybrid push/pull context injection via `.claude/prism.md` + MCP server, confidence lifecycle with decay. Provides the entire personal layer: CLI commands, extraction pipeline, session reviewer, MCP tools, secret scrubbing, project detection.

- **[Lens](https://github.com/ProsusAI/Lens)** -- centralized registry of architectural skills for Claude Code. 12 slash commands for deep codebase analysis, git history mining, skill extraction and synthesis, quality curation, and registry publishing. Cloudflare Worker API for authenticated access. GitHub-backed skill registry with CI validation. Provides the entire team layer: slash commands, skill format (plugin.json + SKILL.md), Worker, registry template, validation schema.

Prism copies the bulk of both codebases with targeted modifications: Engram's Python library becomes `~/.prism/lib/`, Lens's slash commands become `~/.prism/skills/`, and new code bridges the two (unified CLI, multi-registry management, publish tracking, promotion from engram to skill).

### Two knowledge tiers

| | Engrams | Skills |
|---|---|---|
| **Nature** | Personal, living | Team, immutable |
| **Lifecycle** | Decays without reinforcement (-0.02/week) | Permanent once published |
| **Storage** | `~/.prism/projects/<hash>/engrams/` | Registry repo (`prism-registry`) |
| **Delivery** | System prompt (push) + MCP (pull) | Slash commands (`/advise-skills`, `/audit-code`) |
| **Creation** | Auto (hooks + extraction) or manual (`prism learn`) | Pipelines or promotion from engrams |
| **Confidence** | 0.0 -- 0.9 | N/A (binary: published or not) |

---

## Architecture

### Two repos

```
prism                    ← the tool (installed by developers)
prism-registry           ← the knowledge base (grown by teams via PRs)
```

**Tool repo** (`prism`): everything you install. CLI, hooks, extraction agents, Python library, slash command definitions. Changes when features are shipped. Eventually open-sourceable.

**Registry repo** (`prism-registry`): published skills, skill-registry.json index, validation schema, CI, Cloudflare Worker. Changes when teams publish skills. Each team runs their own registry. External collaborators get API keys without needing GitHub org membership.

The tool talks to the registry via the Cloudflare Worker API. The registry is a runtime dependency, not an install dependency. Personal learning works with no registry at all.

### Two concentric layers, one CLI

```
┌──────────────────────────────────────────────────────────┐
│  Team layer                                              │
│  Extraction pipelines, registry, publish/query           │
│  Activated by: prism registry add ...                    │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Personal layer                                    │  │
│  │  Hooks, extraction, context injection, MCP         │  │
│  │  Works immediately after install. No config.       │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Bridge: prism promote → /curate-skills → /publish-skills│
└──────────────────────────────────────────────────────────┘
```

One install. One CLI (`prism`). Team features activate when you configure a registry. No install modes, no flags.

---

## User stories

### Solo developer -- personal learning

> Sarah works alone on a Django project. She wants Claude Code to remember her preferences.

1. `curl -fsSL https://raw.githubusercontent.com/org/prism/main/install.sh | bash`
2. `cd ~/django-project && prism init`
3. Uses Claude Code normally. Hooks capture tool usage silently.
4. After 15 observations, extraction runs in the background (Haiku proposes, Sonnet validates with 4 safety gates).
5. Next session, `.claude/prism.md` has her top corrections and preferences. Claude follows them.
6. Mid-session, she tells Claude "remember to always use pytest-django" -- Claude calls `prism_record` MCP tool. Or she types `! prism learn "always use pytest-django, not unittest"` in Claude Code. Either way: engram created at confidence 0.9, `.claude/prism.md` updated immediately.
7. `prism status` -- 3 engrams active, 2 candidates pending.
8. An unused preference decays and archives after weeks of non-use.
9. She never configures a registry. Everything just works.

### Team lead -- setting up team knowledge sharing

> Marcus leads a team of 5. He wants to share architectural patterns.

1. Installs Prism, then creates a team registry:
   ```
   prism registry create
   ```
   This creates a GitHub repo from template, deploys the Cloudflare Worker, generates API tokens, and configures his local Prism -- one interactive command.
2. Shares with team: `prism registry add team --url https://acme-prism.workers.dev --token TOKEN`
3. Runs `/run-analysis-pipeline` in Claude Code on the main service. Extracts 12 skills.
4. `/curate-skills` -- quality pass. `/publish-skills` -- PR on registry.
5. Teammates query: `/advise-skills "how do we handle auth between services?"`
6. New hire runs `/audit-code` -- sees 7 relevant patterns.

### Experienced developer -- promoting personal knowledge

> Priya solved a CUDA OOM issue through trial and error. Prism captured the journey.

1. Session reviewer caught her debugging, created observations.
2. Extraction produced an `error_recipe` engram. Confidence 0.65 after first occurrence.
3. Happened again a month later. Prism bumped confidence to 0.8, evidence to 4.
4. `prism promote cuda-oom-batch-sizing`:
   - Gates pass: conf 0.8 >= 0.7, evidence 4 >= 3, source=local
   - Writes `plugin.json` + `SKILL.md` to `_analysis/extracted_skills_codebase/`
5. In Claude Code: `/curate-skills` then `/publish-skills --registry team`
6. Teammates find it via `/advise-skills "CUDA out of memory"`

### Multi-registry user -- team + community

> Alex's team has their own registry. He also reads from a public community registry.

1. `prism registry add team --url https://acme-prism.workers.dev --token TOKEN`
2. `prism registry add community --url https://community-prism.workers.dev --token TOKEN --read-only`
3. `/advise-skills "retry logic"` -- searches both registries, results tagged with source:
   ```
   retry-with-exponential-backoff [team]
   circuit-breaker-pattern [community]
   ```
4. `/publish-skills` -- pushes to `team` (the default writable registry). Community is read-only, so team skills stay private.

---

## Installation

### What you type

```bash
# Install (one-time, works offline after this)
curl -fsSL https://raw.githubusercontent.com/org/prism/main/install.sh | bash

# Set up a project
cd ~/my-project
prism init
```

Two commands. Personal learning works. No tokens, no config, no flags.

**While the repo is private** (pre-open-source), the `curl | bash` approach won't work without auth. Use the clone path instead:

```bash
git clone https://github.com/org/prism.git
cd prism && ./install.sh
```

Once the repo is public, both paths work identically. The installer detects whether it's running from a local clone or via curl and adjusts accordingly.

### What `install.sh` does

```
1. Check prerequisites: python3, git, claude
2. Create ~/.prism/ tree:
     ~/.prism/{lib,agents,hooks,skills,global/engrams,archive}
3. Download from GitHub raw (or copy from local clone):
   a. lib/*.py                                → ~/.prism/lib/
   b. agents/{extractor,validator,reviewer}.md → ~/.prism/agents/
   c. hooks/capture.sh                        → ~/.prism/hooks/
   d. skills/*/SKILL.md                       → ~/.prism/skills/
   e. templates/constitution.md               → ~/.prism/constitution.md (if not exists)
4. Create CLI wrapper                         → ~/.local/bin/prism
5. Write default config.json                  (no registry, just personal defaults)
6. Write empty index.json
7. Print: "Run `prism init` in your project directory"
```

Idempotent. Re-running updates `lib/`, `agents/`, `hooks/`, `skills/` but preserves `config.json`, `index.json`, `constitution.md`, and all project data.

### What `prism init` does

```
1. Detect project_id from git remote (SHA256[:12] of origin URL)
2. Create ~/.prism/projects/<hash>/project.json
3. Configure .claude/settings.local.json (gitignored, not committed):
   - PreToolUse hook  → ~/.prism/hooks/capture.sh
   - PostToolUse hook → ~/.prism/hooks/capture.sh
4. Register MCP server in .claude/settings.local.json:
   - command: python3 ~/.prism/lib/mcp_server.py
   - env: { PRISM_PROJECT: <project_id> }
5. Symlink slash commands:
   - .claude/skills/* → ~/.prism/skills/*
6. Add to .gitignore (if not already present):
   - .claude/skills/
   - .claude/prism.md
   - .claude/settings.local.json
7. Generate .claude/prism.md (push layer, initially sparse)
8. Print summary
```

---

## Interface

### CLI: `prism`

```
Usage: prism <command> [options]

Setup
  init [--global]                  Set up hooks + MCP for current project
  config [key] [value]             Get/set configuration

Personal learning
  status [--project <id>]          Show engrams, stats, health
  learn "<text>" [--scope global]  Manually teach (confidence 0.9, auto-syncs)
  correct <id> "<text>"            Supersede engram with correction (auto-syncs)
  forget <id>                      Archive an engram (auto-syncs)
  extract [--project <id>]         Run extraction pipeline manually
  review --session <id>            Review a session transcript
  sync                             Regenerate .claude/prism.md
  maintain                         Run decay, archive expired engrams
  log [--last N] [--insights]      Show recent observations
  analyze-sessions [--all]         Bootstrap from past session transcripts
  procedures                       List procedures with success/failure stats

Bridge
  promote <id>                     Promote engram to skill format
                                   Writes to _analysis/extracted_skills_codebase/
                                   Then: /curate-skills → /publish-skills

Registry management
  registry create                  Create new registry (repo + Worker + tokens)
  registry add NAME --url URL [--token T] [--read-only]
  registry remove NAME
  registry list                    Show configured registries
  registry default NAME            Set default push target
  registry token create NAME       Generate new API token for a registry
  registry token revoke NAME TOK   Revoke a token
```

### Slash commands (in Claude Code)

Installed by `prism init` as symlinks in `.claude/skills/`. All work in any project where Prism is initialized.

**Extraction pipelines** (produce skills from codebases)

| Command | Purpose |
|---|---|
| `/run-analysis-pipeline` | Guided full codebase analysis (agentic or general) |
| `/run-history-pipeline` | Git history → failure pattern skills |
| `/analyze-agent-codebase` | Deep 6-cluster agentic analysis |
| `/extract-skills` | Analysis report → skills |
| `/mine-history` | Mine git log for incidents and decisions |
| `/mine-design` | Extract design decisions from current source |
| `/synthesize` | Incident clusters → skills |
| `/synthesize-decisions` | Design decisions → skills |

**Quality and publishing**

| Command | Purpose |
|---|---|
| `/curate-skills` | Quality pass: keep / delete / merge / rewrite |
| `/publish-skills [--registry NAME]` | Publish delta to registry (creates PR) |

**Querying** (these 2 require at least one registry configured)

| Command | Purpose |
|---|---|
| `/advise-skills <query>` | Search all registries for matching skills |
| `/audit-code` | Proactive codebase check against all registries |

All other slash commands (extraction pipelines + `/curate-skills` + `/publish-skills`) work locally with no registry. `/publish-skills` only needs a registry at the final POST step -- curation and skill extraction are always local.

### MCP tools (available to Claude Code mid-session)

| Tool | Input | Purpose |
|---|---|---|
| `prism_search` | `query: string` | Search engrams by natural language |
| `prism_get` | `id: string` | Read full engram content |
| `prism_relevant` | `file_path` or `domain` | Find engrams for current context |
| `prism_record` | `text, kind` | Record new engram mid-session (conf 0.9) |

---

## Registry management

### Creating a registry

```bash
prism registry create
```

Interactive flow:

```
Checking prerequisites...
  ✓ gh (authenticated as gaurav)
  ✓ wrangler (authenticated)

GitHub registry repo
  Owner/org: myteam
  Name: prism-registry
  Visibility: private

  Creating github.com/myteam/prism-registry from template... done

Worker deployment
  Worker name: myteam-prism

  The Worker needs a GitHub token scoped to the registry repo.
  Create one at: https://github.com/settings/personal-access-tokens/new
    Repository: myteam/prism-registry
    Permissions: Contents (RW), Pull requests (RW)
  Paste token: ghp_••••••••

  Generating API tokens...
    admin:  prism_ak_7f3a9b2c...
    member: prism_ak_e1d4f8a2...
    member: prism_ak_9c2b5e7d...

  Deploying Worker... done
  ✓ https://myteam-prism.gaurav.workers.dev
  ✓ Health check passed

  Registry "team" added to ~/.prism/config.json

Share with your team:
  prism registry add team \
    --url https://myteam-prism.gaurav.workers.dev \
    --token prism_ak_e1d4f8a2...
```

Behind the scenes:
```bash
gh repo create ORG/NAME --template org/prism-registry-template --private --clone
# Generate wrangler.toml from template with repo coordinates
# Generate API tokens (openssl rand -hex 16)
# Set Worker secrets: GH_TOKEN, REGISTRY_TOKENS
# wrangler deploy
# prism registry add team --url WORKER_URL --token ADMIN_TOKEN
```

Prerequisites the user handles once: Cloudflare account, `wrangler login`, GitHub fine-grained PAT for the Worker. The script guides them through it.

### Multi-registry config

```json
// ~/.prism/config.json (registries section)
{
  "registries": [
    {
      "name": "team",
      "url": "https://myteam-prism.gaurav.workers.dev",
      "token": "prism_ak_7f3a9b2c...",
      "writable": true
    },
    {
      "name": "community",
      "url": "https://community-prism.workers.dev",
      "token": "prism_ak_public...",
      "writable": false
    }
  ],
  "default_registry": "team"
}
```

### How multi-registry reads work

```
/advise-skills "how to handle retries"

  For each registry in config:
    1. Check ~/.prism/registries/{name}/skill-registry.json
    2. If missing or stale (>24h): GET {url}/registry
    3. Cache locally

  Merge all indexes into unified search
  Each result tagged with source registry:
    "retry-with-exponential-backoff [team]"
    "circuit-breaker-pattern [community]"

  Fetch SKILL.md from the matching registry on demand
```

### How multi-registry writes work

```
/publish-skills                       → pushes to default_registry
/publish-skills --registry community  → pushes to "community"

  1. Resolve target registry, check it's writable
  2. Read _analysis/.published.json — what's already pushed to THIS registry?
  3. Diff: find new/changed skills in _analysis/extracted_skills_*/
  4. POST only the delta to {registry_url}/publish
  5. Update _analysis/.published.json with content hashes
```

### Publish tracking

```json
// _analysis/.published.json
{
  "cuda-oom-batch-sizing": {
    "team": { "published_at": "2026-04-14", "content_hash": "a1b2c3" }
  },
  "retry-with-backoff": {
    "team": { "published_at": "2026-04-14", "content_hash": "d4e5f6" },
    "community": { "published_at": "2026-04-15", "content_hash": "d4e5f6" }
  }
}
```

`/publish-skills --all` overrides tracking and re-publishes everything.

---

## Data flow

```
PERSONAL LAYER
==============

  Claude Code session
  ┌─────────────┐
  │ PreToolUse   │──── capture.sh ────┐
  │ PostToolUse  │                    │
  └─────────────┘                    ▼
                              observations.jsonl
  ┌─────────────┐                    │
  │ Session      │── reviewer.md ────┤  (background, every N obs)
  │ transcript   │   (Haiku)         │
  └─────────────┘                    │
                                     │  (auto at 15 obs)
  ┌─────────────┐                    ▼
  │ prism learn  │           ┌──────────────┐
  │ prism correct│           │   Extraction  │
  └──────┬──────┘           │  Haiku propose │
         │                   │  Sonnet validate│
         │  (direct,         │  (4 gates)     │
         │   conf 0.9)       └──────┬─────────┘
         │                          │
         ▼                          ▼
  ┌──────────────────────────────────────┐
  │            ENGRAMS                    │
  │  ~/.prism/projects/<hash>/engrams/    │
  └──────────────┬───────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
  .claude/prism.md      MCP server
  (PUSH: corrections,  (PULL: prism_search,
   pinned, top prefs)   prism_record)


BRIDGE
======

  prism promote <id>
    │ (conf >= 0.7, evidence >= 3, source != registry)
    │ format conversion: engram .md → plugin.json + SKILL.md
    ▼
  _analysis/extracted_skills_codebase/<name>/


TEAM LAYER
==========

  ┌──────────────────────┐   ┌──────────────────────┐
  │ /run-analysis-pipeline│   │ /run-history-pipeline │
  │ /mine-design          │   │ /mine-history         │
  │ /analyze-agent-codebase   │ /synthesize           │
  │ /extract-skills       │   │                       │
  │ /synthesize-decisions │   │                       │
  └──────────┬───────────┘   └──────────┬────────────┘
             │                          │
             ▼                          ▼
  ┌────────────────────────────────────────────┐
  │  _analysis/extracted_skills_*/              │
  │  (SKILL.md + plugin.json per skill)        │
  └──────────────────┬─────────────────────────┘
                     │
           /curate-skills
                     │
      /publish-skills [--registry NAME]
                     │  (POST only delta, tracked in .published.json)
                     ▼
          ┌──────────────────────┐
          │   PRISM REGISTRY     │
          │ (GitHub repo + Worker│
          │  per team)           │
          └────────┬─────────────┘
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
   /advise-skills  /audit   prism registry add
   (query all)     -code    (connect new teams)
```

---

## Key workflows

### 1. Observation capture

```
Claude Code triggers PreToolUse or PostToolUse
  → capture.sh receives JSON on stdin: { tool_name, tool_input, session_id }
  → Scrub secrets (API keys, tokens, bearer, sk-*, ghp-*)
  → Truncate input_summary to 500 chars
  → Append JSONL line to ~/.prism/projects/<hash>/observations.jsonl
  → If obs_count >= 15: spawn background extraction
  → If obs_count % 5 == 0: spawn background session review
  → Exit 0 (never blocks Claude Code)
```

### 2. Extraction (background, automatic)

```
Phase 1 — Haiku proposes
  → Read observations.jsonl
  → Run `claude --model haiku` with extractor.md prompt
  → Write candidate .md files to candidates/
  → Types: preference, correction, procedure, domain_fact, tool_pattern, error_recipe

Phase 2 — Sonnet validates (4 gates)
  → Read all candidates
  → Run `claude --model sonnet` with validator.md prompt
  → Gate 1: Constitution (no secrets, escalation, self-modification)
  → Gate 2: Evidence (min observations, session IDs cited)
  → Gate 3: Contradiction (no conflict with high-confidence existing engrams)
  → Gate 4: Safety (no permission expansion, bypass, obfuscation)
  → APPROVED → move to engrams/, add to index
  → REJECTED → delete, log reason
  → MODIFIED → adjust, then move to engrams/

Post: archive observations, regenerate .claude/prism.md
```

### 3. Session review (background, periodic)

```
Find session transcript: ~/.claude/projects/<folder>/<session>.jsonl
  → Pass 1: scan full transcript for corrections, preferences
  → Pass 2: last N lines for recent context
  → Run `claude --model haiku` with reviewer.md (no tools)
  → Extract: trial_and_error, user_correction, design_decision,
             domain_knowledge, non_obvious_solution
  → Append as observations → feed into next extraction cycle
```

### 4. Context injection

```
PUSH: .claude/prism.md (generated by `prism sync`)
  Auto-regenerated after: learn, correct, forget, extract, maintain
  Priority:
  1. Corrections (must push — can't rely on pull for past mistakes)
  2. Pinned engrams
  3. Top preferences by confidence
  4. Session-validated patterns
  5. Publish-ready (conf >= 0.7) — with "ready to promote" note
  Max: 100 lines (configurable)

  Footer: MCP nudge
    "Use prism_search for relevant knowledge before complex tasks"
    "Use prism_record to capture non-obvious solutions"

PULL: MCP server
  prism_search  — natural language search across all engrams
  prism_get     — full content by ID
  prism_relevant — engrams for current file/domain
  prism_record  — create new engram mid-session
```

### 5. Promotion (engram → skill)

```
prism promote <id>

  Gate check (local, no network):
    confidence >= 0.7?
    evidence_count >= 3?
    source != "registry"? (prevent circular publishing)

  Format conversion:
    engram .md (YAML frontmatter + body)
      →  plugin.json:
           { name, description (with TRIGGER when:), author,
             repository, category, source, commit_date, source_hash }
      →  SKILL.md:
           ---
           name: ...
           description: "... TRIGGER when: ..."
           ---
           # <trigger>
           *Learned from N session observations.*
           ## Key decisions
           <body>

  Write to: _analysis/extracted_skills_codebase/<name>/

  Print: "Next: /curate-skills then /publish-skills"
```

### 6. Publishing (skill → registry)

```
/publish-skills [--registry NAME] [--all]

  1. Resolve target registry (default or specified)
  2. Check writable
  3. Load _analysis/.published.json
  4. Scan _analysis/extracted_skills_codebase/ and extracted_skills_history/
  5. Compute content hash for each skill
  6. Filter: skip skills already in .published.json with same hash
     (unless --all, which re-publishes everything)
  7. POST delta to {registry_url}/publish:
     { "skills": [{name, skill_md, plugin_json}, ...], "description": "..." }
  8. Worker creates branch + PR on registry repo
  9. Update .published.json with hashes + timestamp
  10. Print PR URL
```

### 7. Team extraction pipelines

Unchanged from current Lens. Slash commands that run inside Claude Code.

**Agentic codebases:**
```
/run-analysis-pipeline
  1. /analyze-agent-codebase → _analysis/full_report.md
  2. /extract-skills → _analysis/extracted_skills_codebase/{name}/
  (optional: 3. /mine-design → _analysis/design.md)
  (optional: 4. /synthesize-decisions → more skills)
```

**Any codebase (git history):**
```
/run-history-pipeline
  1. /mine-history → _analysis/{incidents,directives,architecture}.md
  2. /synthesize → _analysis/extracted_skills_history/{name}/
```

**Any codebase (source snapshot):**
```
/mine-design → _analysis/design.md
/synthesize-decisions → _analysis/extracted_skills_codebase/{name}/
```

---

## Directory layout

### `~/.prism/` (user home)

```
~/.prism/
├── config.json                 ← settings + registries array
├── constitution.md             ← safety principles (never overwritten)
├── index.json                  ← master engram index
├── validation-log.jsonl        ← extraction decision history
├── analyzed-sessions.json      ← session import tracker
│
├── agents/
│   ├── extractor.md            ← Haiku: propose candidates
│   ├── validator.md            ← Sonnet: 4-gate validation
│   └── reviewer.md             ← Haiku: session review
│
├── hooks/
│   └── capture.sh              ← PreToolUse/PostToolUse capture
│
├── skills/                     ← slash command definitions
│   ├── advise-skills/SKILL.md
│   ├── audit-code/SKILL.md
│   ├── mine-history/SKILL.md
│   ├── publish-skills/SKILL.md
│   ├── curate-skills/SKILL.md
│   ├── analyze-agent-codebase/
│   │   ├── SKILL.md
│   │   └── questions_cluster_{a..f}.md
│   └── ... (12 total)
│
├── lib/
│   ├── cli.py                  ← command router
│   ├── commands.py             ← learn, correct, forget, status, maintain
│   ├── config.py               ← config + defaults
│   ├── extract.py              ← Haiku → Sonnet pipeline
│   ├── index.py                ← engram index CRUD
│   ├── bridge.py               ← promote: engram → skill format
│   ├── mcp_server.py           ← prism_search, prism_get, etc.
│   ├── project.py              ← project detection (git hash)
│   ├── registry.py             ← registry create, add, token management
│   ├── review.py               ← background session review
│   ├── scrub.py                ← secret redaction
│   ├── sessions.py             ← bootstrap from past transcripts
│   ├── sync.py                 ← generate .claude/prism.md
│   └── trigger.py              ← auto-extraction after N observations
│
├── registries/                 ← cached per-registry data
│   ├── team/
│   │   ├── skill-registry.json ← cached, refreshed on 24h TTL
│   │   └── worker.json         ← worker name + repo (for token management)
│   └── community/
│       └── skill-registry.json
│
├── global/engrams/             ← global engrams (scope: global)
├── archive/                    ← decayed/forgotten (recoverable)
│
└── projects/<hash12>/
    ├── project.json            ← { name, root, remote, project_id }
    ├── observations.jsonl      ← current buffer
    ├── observations.archive/   ← rotated after extraction
    ├── engrams/                ← project-scoped engrams
    └── candidates/             ← staging during extraction
```

### Per-project `.claude/`

```
.claude/
├── settings.json               ← project settings (committed to git)
├── settings.local.json         ← hooks + MCP (written by `prism init`, gitignored)
├── prism.md                    ← generated system prompt (push layer, gitignored)
└── skills/                     ← symlinks → ~/.prism/skills/ (gitignored)
    ├── advise-skills → ~/.prism/skills/advise-skills
    ├── mine-history → ~/.prism/skills/mine-history
    └── ...
```

Note: `prism init` writes hooks and MCP config to `.claude/settings.local.json` (not `settings.json`) because local settings are gitignored by default. This prevents Prism-specific machine paths from leaking into committed project settings.

### Per-project `_analysis/` (working directory)

```
_analysis/
├── .analysis-pipeline-state    ← analysis pipeline progress tracker
├── .history-pipeline-state     ← history pipeline progress tracker
├── .meta                       ← cached metadata (author, repository, source_hash)
├── .published.json             ← publish tracking (per-registry content hashes)
├── report.md                   ← summary table of all extracted skills
├── full_report.md              ← from /analyze-agent-codebase
├── design.md                   ← from /mine-design
├── incidents.md                ← from /mine-history
├── directives.md               ← from /mine-history (actionable rules from commits)
├── architecture.md             ← from /mine-history (tech decisions + evolution)
│
├── extracted_skills_codebase/  ← from /extract-skills, /synthesize-decisions, prism promote
│   └── <skill-name>/
│       ├── plugin.json
│       └── SKILL.md
│
└── extracted_skills_history/   ← from /synthesize
    └── <skill-name>/
        ├── plugin.json
        └── SKILL.md
```

---

## Configuration

`~/.prism/config.json`:

```json
{
  "registries": [
    {
      "name": "team",
      "url": "https://myteam-prism.gaurav.workers.dev",
      "token": "prism_ak_7f3a9b2c...",
      "writable": true
    }
  ],
  "default_registry": "team",

  "extract_threshold": 15,
  "review_interval": 5,
  "review_timeout": 60,
  "decay_rate_per_week": 0.02,
  "archive_threshold": 0.2,
  "max_context_lines": 100,
  "publish_min_confidence": 0.7,
  "publish_min_evidence": 3,

  "scrub_patterns": ["..."],
  "block_patterns": ["..."]
}
```

---

## Source repo structures

### Tool repo: `prism`

```
prism/
├── README.md
├── CLAUDE.md
├── install.sh                      ← unified installer
├── prism                           ← CLI entry point
│
├── skills/                         ← slash command definitions (source of truth)
│   ├── advise-skills/SKILL.md
│   ├── audit-code/SKILL.md
│   ├── analyze-agent-codebase/     (SKILL.md + 7 question files)
│   ├── extract-skills/SKILL.md
│   ├── mine-history/SKILL.md
│   ├── mine-design/SKILL.md
│   ├── synthesize/SKILL.md
│   ├── synthesize-decisions/SKILL.md
│   ├── curate-skills/SKILL.md
│   ├── publish-skills/SKILL.md
│   ├── run-analysis-pipeline/SKILL.md
│   └── run-history-pipeline/SKILL.md
│
├── agents/
│   ├── extractor.md
│   ├── validator.md
│   └── reviewer.md
│
├── hooks/
│   └── capture.sh
│
├── lib/
│   ├── __init__.py
│   ├── cli.py
│   ├── commands.py
│   ├── config.py
│   ├── extract.py
│   ├── index.py
│   ├── bridge.py
│   ├── mcp_server.py
│   ├── project.py
│   ├── registry.py                 ← NEW: registry create/add/token management
│   ├── review.py
│   ├── scrub.py
│   ├── sessions.py
│   ├── sync.py
│   └── trigger.py
│
└── templates/
    └── constitution.md
```

### Registry template repo: `prism-registry-template`

Teams fork this to create their own registry.

```
prism-registry-template/
├── README.md                       ← "How to deploy your Prism registry"
├── skills/                         ← empty (teams populate via /publish-skills)
├── skill-registry.json             ← {"skills": [], "skill_count": 0, "updated_at": ""}
│
├── schemas/
│   └── plugin.schema.json          ← skill validation schema
│
├── scripts/
│   ├── validate.py                 ← CI: validate skill structure on PR
│   └── build_registry.py           ← CI: rebuild skill-registry.json on merge
│
├── worker/
│   ├── src/index.ts                ← Cloudflare Worker source
│   ├── wrangler.toml.template      ← filled in by `prism registry create`
│   └── package.json
│
└── .github/workflows/
    ├── validate-pr.yml             ← runs validate.py on incoming PRs
    └── rebuild-registry.yml        ← runs build_registry.py after merge
```

---

## What's new vs. carried over

### From Engram (carried over)

Python library -- copied with renames (`engram` → `prism`, `ENGRAM_HOME` → `PRISM_HOME`, etc.):

- `lib/cli.py` -- command router (add `promote`, `registry` subcommands; drop `publish`, `pull`, `import-lens`, `publish-to-lens`)
- `lib/commands.py` -- learn, correct, forget, status, maintain, procedures, log
- `lib/config.py` -- config + defaults (add registries schema)
- `lib/extract.py` -- Haiku → Sonnet two-phase extraction pipeline
- `lib/index.py` -- engram index CRUD
- `lib/mcp_server.py` -- MCP tools (renamed to `prism_search`, `prism_get`, `prism_relevant`, `prism_record`)
- `lib/project.py` -- project detection (SHA256[:12] of git remote)
- `lib/review.py` -- background session review (Haiku, no tools)
- `lib/scrub.py` -- secret redaction patterns
- `lib/sessions.py` -- bootstrap from past Claude Code transcripts
- `lib/sync.py` -- generate `.claude/prism.md` (priority ordering, max lines)
- `lib/trigger.py` -- auto-extraction after N observations
- `hooks/capture.sh` -- PreToolUse/PostToolUse hook
- `agents/{extractor,validator,reviewer}.md` -- agent prompts
- `templates/constitution.md` -- safety principles

Also carried over: confidence lifecycle (0.3 → 0.85 → decay → archive at 0.2), hybrid push/pull context injection, 4 validation gates (constitution, evidence, contradiction, safety).

### From Engram (dropped)
- `lib/team.py` (git-based registry) → replaced by Prism registry
- `lib/lens.py` (Lens bridge) → replaced by `lib/bridge.py` (promotion logic kept, import/export dropped)
- `hooks/cursor-capture.sh` → Claude Code only
- `engram publish` / `engram pull` → replaced by `prism promote` + `/publish-skills`

### From Lens (carried over)

Slash commands (SKILL.md files) -- the bulk are copied as-is or with minor edits:

- **Copied as-is (4 commands):** `/analyze-agent-codebase` (+ 7 question cluster files), `/mine-history`, `/mine-design`, `/curate-skills`
- **Minor edits (5 commands):** `/run-analysis-pipeline`, `/run-history-pipeline` (update publish command reference), `/extract-skills`, `/synthesize`, `/synthesize-decisions` (remove Prosus-specific references)
- **Rewritten (3 commands → 2):** `/publish-skills` (new unified, replaces both `publish-skills-cloudflare` and `publish-skills-github` -- reads registry config from `~/.prism/config.json`, adds delta tracking via `.published.json`), `/advise-skills` and `/audit-code` (rewritten for multi-registry reads from `~/.prism/config.json` instead of single `.claude/skill-registry.json`)

Also carried over:
- Skill format (plugin.json + SKILL.md)
- Cloudflare Worker source
- skill-registry.json format
- Validation schema (`plugin.schema.json`) + CI scripts (`validate.py`, `build_registry.py`)
- Pipeline state tracking (`.analysis-pipeline-state`, `.history-pipeline-state`)
- GitHub Actions workflows (`validate-pr.yml`, `rebuild-registry.yml`)

### From Lens (dropped)
- Separate `publish-skills-cloudflare` and `publish-skills-github` → unified `/publish-skills`
- `install.sh` modes (--core, --all, advise-and-audit) → single install, features gate on config
- GitHub-direct platform detection (`ghp_*` token sniffing) → Worker-only, always
- `.claude/skill-registry.json` installed locally → `~/.prism/registries/{name}/skill-registry.json` cached with 24h TTL

### New in Prism
- Unified CLI (`prism`) for both layers
- `prism registry create` (automated repo + Worker setup)
- `prism registry add/remove/list/default` (multi-registry)
- `prism registry token create/revoke` (token management)
- Multi-registry read (merge skill-registry.json from all sources)
- Multi-registry write (publish delta to specific registry)
- Publish tracking (`.published.json` with content hashes, per-registry)
- `lib/registry.py` (registry management module)
- Runtime registry fetch (cached with 24h TTL, not installed)
- `prism promote` (replaces `engram publish-to-lens`)

---

## README outline

```markdown
# Prism

A knowledge layer for Claude Code.
Personal learning + team skill sharing.

Built on [Engram](https://github.com/ProsusAI/engram) (personal learning)
and [Lens](https://github.com/ProsusAI/Lens) (team skill registry).

## Quick start

  curl -fsSL https://raw.githubusercontent.com/org/prism/main/install.sh | bash
  cd ~/my-project && prism init

## Personal learning

Claude Code learns your preferences across sessions. No setup beyond install.

### How it works
[hooks → observations → extraction (Haiku+Sonnet, 4 gates) → engrams → .claude/prism.md + MCP]

### Commands
  prism learn "always use ruff"
  prism correct <id> "actually use uv run ruff"
  prism forget <id>
  prism status

## Team knowledge

Extract and share architectural best practices.

### Set up a team registry
  prism registry create

### Share with your team
  prism registry add team --url URL --token TOKEN

### Extract skills from a codebase
  /run-analysis-pipeline
  /curate-skills
  /publish-skills

### Query the registry
  /advise-skills "how to handle retries"
  /audit-code

## Promoting personal knowledge to team

When an engram reaches confidence >= 0.7 with 3+ observations:
  prism promote <id>       → writes skill to _analysis/
  /curate-skills           → quality review
  /publish-skills          → PR on registry

## Multiple registries

  prism registry add community --url URL --token TOKEN --read-only
  /advise-skills searches all. /publish-skills pushes to default.

## Configuration

  ~/.prism/config.json

## How it works

[architecture diagram, directory layout]
```

---

## Open decisions

1. **When Prism is open-sourced**: tool repo goes public. `prism-registry-template` goes public. Each team's actual registry stays private. The install curl just works (public repo, no auth). No architectural changes needed.

2. **Promote without registry**: `prism promote` is a local operation (format conversion). It works even with no registry configured. The user could email the resulting `plugin.json` + `SKILL.md` if they wanted. `/publish-skills` is what needs the registry.
