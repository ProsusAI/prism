# Architecture Research

**Domain:** Knowledge layer / memory system for AI coding assistants
**Researched:** 2026-04-14
**Confidence:** HIGH

## System Overview

Prism is a two-layer knowledge system (personal engrams + team skills) unified behind a single CLI. The architecture has six major subsystems that form a pipeline from raw observation to actionable context injection, plus a bridge that promotes personal knowledge into team knowledge.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INTERFACE LAYER                                  │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │ CLI      │  │ Slash        │  │ MCP Server   │  │ Hook          │   │
│  │ (prism)  │  │ Commands     │  │ (4 tools)    │  │ (capture.sh)  │   │
│  └────┬─────┘  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘   │
├───────┴──────────────┴──────────────────┴───────────────────┴───────────┤
│                         PROCESSING LAYER                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ Extraction   │  │ Session      │  │ Sync Engine  │                   │
│  │ Pipeline     │  │ Reviewer     │  │ (push layer) │                   │
│  │ (Haiku+      │  │ (Haiku)      │  │              │                   │
│  │  Sonnet)     │  │              │  │              │                   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                   │
├─────────┴────────────────┴──────────────────┴──────────────────────────┤
│                         BRIDGE LAYER                                     │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ Promote: engram (personal) --> skill (team)                      │   │
│  │ Format conversion: .md engram --> plugin.json + SKILL.md         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
├────────────────────────────────────────────────────────────────────────┤
│                         TEAM LAYER                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ Analysis     │  │ Curation +   │  │ Registry     │                   │
│  │ Pipelines    │  │ Publishing   │  │ Module       │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
├────────────────────────────────────────────────────────────────────────┤
│                         DATA LAYER                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ ~/.prism/    │  │ index.json   │  │ Registry     │                   │
│  │ projects/    │  │ (master      │  │ Cache        │                   │
│  │ engrams/     │  │  index)      │  │ (24h TTL)    │                   │
│  │ obs.jsonl    │  │              │  │              │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    EXTERNAL: PRISM REGISTRY                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ GitHub Repo  │  │ Cloudflare   │  │ CI/CD        │                   │
│  │ (skills,     │  │ Worker (API  │  │ (validation  │                   │
│  │  registry    │  │  proxy)      │  │  on PR)      │                   │
│  │  .json)      │  │              │  │              │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| **CLI (`prism`)** | Command router for all user-facing operations | Python argparse, dispatches to `lib/commands.py` functions. Shell wrapper at `~/.local/bin/prism` |
| **Hook (`capture.sh`)** | Observe Claude Code tool calls, write observations without blocking | Bash script receiving JSON on stdin from PreToolUse/PostToolUse events. Must always exit 0. |
| **Extraction Pipeline** | Transform raw observations into validated engrams | Two-phase LLM pipeline: Haiku proposes candidates, Sonnet validates through 4 gates (constitution, evidence, contradiction, safety) |
| **Session Reviewer** | Scan live session transcripts for insights hooks miss | Background Haiku agent. Finds corrections, preferences, decisions in conversation text. Outputs enriched observations. |
| **MCP Server** | Expose engram knowledge to Claude Code mid-session | Python stdio MCP server. 4 tools: `prism_search`, `prism_get`, `prism_relevant`, `prism_record` |
| **Sync Engine** | Generate `.claude/prism.md` push context | Python. Priority-orders engrams (corrections > pinned > top preferences). Respects max_context_lines. |
| **Bridge (Promote)** | Convert high-confidence engrams to skill format | Python. Gates: confidence >= 0.7, evidence >= 3, source = local. Outputs plugin.json + SKILL.md. |
| **Slash Commands (12)** | Codebase analysis, skill extraction, curation, publishing, querying | Markdown instruction files in `.claude/skills/`. Claude Code executes them as agentic workflows. |
| **Registry Module** | Create/manage team registries, multi-registry read/write | Python CLI commands orchestrating `gh`, `wrangler`, and HTTP calls to Worker API |
| **Index** | Master catalog of all engrams with metadata | Single `~/.prism/index.json` file. JSON with id, kind, trigger, confidence, domain, scope, tags. |
| **Config** | User settings, registry list, thresholds | `~/.prism/config.json`. Merged with hardcoded defaults. |
| **Installer** | Set up `~/.prism/` tree, symlink CLI, copy assets | Bash `install.sh`. Idempotent: re-run updates code, preserves user data. |

## Recommended Project Structure

```
prism/                              # Tool repo (what gets installed)
├── install.sh                      # Installer (entry point)
├── prism                           # CLI entry point (thin shell wrapper)
├── lib/                            # Python library (zero dependencies)
│   ├── __init__.py
│   ├── cli.py                      # Argparse command router
│   ├── commands.py                 # User-facing command implementations
│   ├── config.py                   # Config management, path helpers
│   ├── index.py                    # Master index CRUD
│   ├── extract.py                  # Two-phase extraction pipeline
│   ├── review.py                   # Session reviewer
│   ├── sync.py                     # Push layer (.claude/prism.md) generator
│   ├── mcp_server.py               # MCP stdio server (4 tools)
│   ├── trigger.py                  # Auto-extraction trigger logic
│   ├── scrub.py                    # Secret scrubbing
│   ├── project.py                  # Project detection (git remote hash)
│   ├── sessions.py                 # Session transcript analysis (bootstrap)
│   ├── promote.py                  # Engram -> skill format conversion (NEW)
│   └── registry.py                 # Multi-registry management (NEW)
├── hooks/
│   └── capture.sh                  # PreToolUse/PostToolUse observer
├── agents/                         # LLM prompt templates
│   ├── extractor.md                # Haiku extraction prompt
│   ├── validator.md                # Sonnet validation prompt (4 gates)
│   └── reviewer.md                 # Haiku session review prompt
├── skills/                         # Slash command definitions (from Lens)
│   ├── advise-skills/SKILL.md
│   ├── audit-code/SKILL.md
│   ├── curate-skills/SKILL.md
│   ├── extract-skills/SKILL.md
│   ├── mine-design/SKILL.md
│   ├── mine-history/SKILL.md
│   ├── publish-skills/SKILL.md     # Unified (was split cloudflare/github)
│   ├── run-analysis-pipeline/SKILL.md
│   ├── run-history-pipeline/SKILL.md
│   ├── synthesize/SKILL.md
│   ├── synthesize-decisions/SKILL.md
│   └── analyze-agent-codebase/     # Multi-file (questions clusters)
├── templates/
│   ├── constitution.md             # Safety principles (never overwritten)
│   └── registry/                   # Registry template files (bundled)
│       ├── worker/
│       │   ├── src/index.ts        # Cloudflare Worker source
│       │   ├── package.json
│       │   └── wrangler.toml.tmpl  # Template with placeholders
│       ├── scripts/
│       │   ├── build_registry.py
│       │   └── validate.py
│       ├── schemas/
│       │   └── plugin-schema.json
│       ├── .github/workflows/      # CI for PR validation
│       └── README.md
└── scripts/                        # Development/build scripts
    └── validate.py                 # Local skill validation
```

### Installed Layout (Runtime)

```
~/.prism/                           # PRISM_HOME
├── config.json                     # User config + registry list
├── index.json                      # Master engram index
├── constitution.md                 # Safety principles (preserved on update)
├── lib/                            # Copied from repo lib/
│   └── *.py
├── agents/                         # Copied from repo agents/
│   └── *.md
├── hooks/
│   └── capture.sh
├── skills/                         # Copied from repo skills/
│   └── */SKILL.md
├── global/
│   └── engrams/                    # Global-scope engrams
├── projects/
│   └── <hash>/                     # Per-project data
│       ├── project.json            # Project metadata
│       ├── observations.jsonl      # Raw observations
│       ├── candidates/             # Extraction staging
│       └── engrams/                # Validated engrams
├── registries/
│   └── <name>/
│       └── skill-registry.json     # Cached registry index (24h TTL)
├── archive/                        # Archived (decayed) engrams
└── analyzed-sessions.json          # Tracker for session bootstrap
```

### Structure Rationale

- **`lib/` as flat module directory:** Python with zero dependencies. No package manager, no virtualenv. Installed by copying files. Each module has a clear single responsibility. This matches Engram's proven approach.
- **`skills/` as SKILL.md files:** Slash commands are Claude Code skill definitions (markdown instruction files). They are not Python code. They execute inside Claude Code's agentic loop. Symlinking them into `.claude/skills/` makes them available per-project.
- **`templates/registry/` bundled in tool repo:** The registry template is not a separate project. It ships with the tool. `prism registry create` copies these files to create a new GitHub repo. This avoids a separate template repo dependency.
- **`~/.prism/projects/<hash>/` per-project isolation:** Each project gets its own observation log, candidates staging, and engrams directory. The hash comes from SHA256 of the git remote URL (12-char prefix). Global engrams live in `~/.prism/global/`.
- **Single `index.json` for all engrams:** Flat file, not database. All engrams from all projects indexed in one place. Supports filtering by project_id, scope, kind, confidence. This keeps the MCP server and sync engine simple.

## Architectural Patterns

### Pattern 1: Non-Blocking Hook Observer

**What:** The hook script (`capture.sh`) receives tool call data from Claude Code on stdin, writes it to a JSONL file, and optionally spawns background processes. It must never block the IDE.

**When to use:** Any integration point where Claude Code sends events to external systems.

**Trade-offs:**
- Pro: Zero impact on IDE responsiveness. Claude Code's tool execution is never delayed.
- Pro: Crash-safe -- `exit 0` always, even on errors. Lock files with stale-lock detection (10 min).
- Con: Background spawns (extraction, review) are fire-and-forget. No feedback loop to the user during the session.
- Con: Shell parsing of JSON via Python one-liners is fragile. Input validation is minimal.

**Example:**
```bash
# Core pattern: read stdin, append JSONL, spawn background work, exit 0
INPUT=$(cat)
python3 -c "import json,sys; obs={...}; print(json.dumps(obs))" >> "$OBSERVATIONS_FILE" 2>/dev/null
if [ "$OBS_COUNT" -ge "$THRESHOLD" ]; then
    nohup "$CLI" extract --project "$PROJECT_ID" >/dev/null 2>&1 &
fi
exit 0
```

### Pattern 2: Two-Phase LLM Pipeline (Propose + Validate)

**What:** A cheap, fast model (Haiku) generates candidates liberally, then a thorough model (Sonnet) applies strict validation gates. This is a generate-and-filter pattern optimized for cost and quality.

**When to use:** Any knowledge extraction where you need both coverage (finding all patterns) and precision (rejecting false positives).

**Trade-offs:**
- Pro: Haiku is cheap and fast for broad pattern scanning. Sonnet is expensive but thorough for validation.
- Pro: 4-gate validation (constitution, evidence, contradiction, safety) catches different failure modes independently.
- Pro: Approved/rejected/modified outcomes give clear audit trail.
- Con: Requires two API calls per extraction batch. Cost accumulates with active codebases.
- Con: Both phases use the `claude` CLI subprocess -- requires Claude CLI installed and authenticated.

**Example:**
```python
# Phase 1: Haiku proposes
subprocess.run(["claude", "--model", "haiku", "-p", prompt], ...)
# -> writes candidate .md files to candidates/

# Phase 2: Sonnet validates
subprocess.run(["claude", "--model", "sonnet", "-p", validate_prompt], ...)
# -> APPROVED: move to engrams/, add to index
# -> REJECTED: delete, log reason
# -> MODIFIED: adjust fields, then approve
```

### Pattern 3: Push + Pull Context Injection

**What:** Knowledge reaches Claude Code through two complementary channels. Push: a generated markdown file (`.claude/prism.md`) included in the system prompt automatically. Pull: an MCP server that Claude Code queries on demand.

**When to use:** When you have both critical knowledge (corrections that must always be visible) and a large knowledge base (too big for the system prompt).

**Trade-offs:**
- Pro: Push guarantees corrections and top preferences are always in context. No reliance on Claude deciding to search.
- Pro: Pull allows full knowledge base access without bloating the system prompt. Claude searches when relevant.
- Pro: MCP nudge in the push file ("Use prism_search for relevant knowledge") bridges the two channels.
- Con: Push has a line budget (default 100 lines). Priority ordering matters -- wrong priorities mean important knowledge is excluded.
- Con: Pull requires Claude to proactively search. It may not for unfamiliar topics.

### Pattern 4: Confidence Lifecycle with Decay

**What:** Every engram has a confidence score (0.0-0.9) that increases with reinforcing observations and decays without use (-0.02/week). Below a threshold (0.2), engrams are archived. This creates organic knowledge curation.

**When to use:** Any system where knowledge needs to stay fresh and self-curate. Prevents stale knowledge from accumulating indefinitely.

**Trade-offs:**
- Pro: Self-maintaining. Unused knowledge fades naturally. No manual cleanup needed.
- Pro: Confidence scoring enables priority ordering in the push layer.
- Con: Decay rate is a tuning challenge. Too fast = useful knowledge archives prematurely. Too slow = stale knowledge persists.
- Con: Evidence count and confidence are separate dimensions that should correlate but might not.

### Pattern 5: Registry as GitHub Repo + Cloudflare Worker Proxy

**What:** Team knowledge (skills) is stored in a GitHub repository. A Cloudflare Worker acts as an authenticated API proxy between consumers and the private repo. Publishing creates PRs via the GitHub API. Reading fetches raw files.

**When to use:** When you need a shared, versioned knowledge base with review workflows (PRs) and external access (API keys for non-GitHub-org members).

**Trade-offs:**
- Pro: GitHub provides versioning, review (PRs), CI validation, and access control for free.
- Pro: Worker provides a stable API surface. Consumers don't need GitHub access.
- Pro: Token-based auth is simple. No OAuth complexity.
- Con: Worker is a deployment dependency. Each team deploys their own.
- Con: Publish flow is async (PR -> review -> merge -> cache refresh). Not instant.

## Data Flow

### Personal Learning Flow (Automated)

```
Claude Code Session
    │
    ├── PreToolUse event ─────────────────────┐
    │                                          │
    ├── PostToolUse event ────────────────────┤
    │                                          ▼
    │                                   capture.sh
    │                                          │
    │                                  ┌───────┴───────┐
    │                                  │  scrub secrets │
    │                                  │  truncate 500c │
    │                                  └───────┬───────┘
    │                                          │
    │                                          ▼
    │                             observations.jsonl
    │                                          │
    │                           ┌──────────────┼──────────────┐
    │                           │              │              │
    │                  (every 5 obs)    (at 15 obs)          │
    │                           │              │              │
    │                           ▼              ▼              │
    │                     Session         Extraction          │
    │                     Reviewer        Pipeline            │
    │                     (Haiku)     (Haiku + Sonnet)       │
    │                           │              │              │
    │                           │         4 Validation        │
    │                           │           Gates             │
    │                           │              │              │
    │                           ▼              ▼              │
    │                  enriched obs       engrams/*.md        │
    │                  (feed back ──→ observations.jsonl)     │
    │                                      │                  │
    │                              index.json updated        │
    │                                      │                  │
    │                           ┌──────────┴──────────┐      │
    │                           │                     │      │
    │                           ▼                     ▼      │
    │                   .claude/prism.md       MCP Server     │
    │                   (PUSH: auto-           (PULL: on-     │
    ├── reads prism.md ◄ regenerated)          demand)       │
    │                                                │      │
    └── calls prism_search ──────────────────────────┘      │
```

### Manual Learning Flow

```
User: prism learn "always use pytest-django"
    │
    ▼
commands.py:cmd_learn()
    │
    ├── Write engram .md file (confidence 0.9, kind=preference)
    ├── Add to index.json
    └── Auto-run sync → regenerate .claude/prism.md
```

### Team Knowledge Flow

```
                    Slash Command                    Slash Command
                    /run-analysis-pipeline           /run-history-pipeline
                            │                               │
                            ▼                               ▼
                    Codebase analysis              Git history analysis
                    (6-cluster deep dive)          (incident mining)
                            │                               │
                            ▼                               ▼
              _analysis/extracted_skills_codebase/  _analysis/extracted_skills_history/
                            │                               │
                            └──────────┬────────────────────┘
                                       │
                              /curate-skills
                              (quality pass)
                                       │
                            /publish-skills [--registry NAME]
                                       │
                              ┌────────┴────────┐
                              │ Delta detection │
                              │ (.published.json)│
                              └────────┬────────┘
                                       │
                              POST to Worker API
                                       │
                              ┌────────┴────────┐
                              │ Worker creates  │
                              │ branch + PR     │
                              └────────┬────────┘
                                       │
                              CI validates on PR
                                       │
                              Merge → registry updated
                                       │
                              ┌────────┴────────┐
                              │ Cache refresh   │
                              │ (24h TTL)       │
                              └────────┬────────┘
                                       │
                        /advise-skills or /audit-code
                        (query across all registries)
```

### Bridge Flow (Personal -> Team)

```
prism promote <engram-id>
    │
    ├── Gate check: confidence >= 0.7?
    ├── Gate check: evidence_count >= 3?
    ├── Gate check: source != "registry"?
    │
    ▼ (all pass)
    │
    ├── Read engram .md
    ├── Convert to plugin.json + SKILL.md format
    └── Write to _analysis/extracted_skills_codebase/<name>/
            │
            ▼
    Then: /curate-skills → /publish-skills (normal team flow)
```

### Key Data Flows

1. **Observation capture (hot path):** Claude Code event -> capture.sh -> observations.jsonl. Must be non-blocking. Sub-100ms. No Python import delay (uses inline python3 -c).
2. **Extraction (background, cold path):** observations.jsonl -> Haiku proposal -> candidates/ -> Sonnet validation -> engrams/ + index.json -> sync -> .claude/prism.md. Minutes. Lock-file guarded.
3. **Context injection (read path):** .claude/prism.md read by Claude Code at session start (push). MCP tools called mid-session (pull). Both read from index.json + engram .md files.
4. **Registry publish (team write path):** _analysis/ skills -> delta detection -> POST to Worker -> Worker creates branch + commits + PR on GitHub. Async, minutes to hours (includes review).
5. **Registry query (team read path):** Slash command -> check cached skill-registry.json (24h TTL) -> fetch from Worker if stale -> merge all registries -> semantic match -> fetch SKILL.md on demand.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 developer, 1 project | Default config works. Single flat index.json. No registry. |
| 1 developer, 10 projects | index.json grows but remains manageable (hundreds of entries). Project isolation via hash directories keeps observations separate. |
| 5 developers, 1 registry | Registry Worker handles concurrent reads fine (Cloudflare edge). Publishing is serialized by PR workflow (one at a time). |
| 20+ developers, multiple registries | Multi-registry merge in /advise-skills gets slow with large registries. Cache TTL becomes important. Consider registry-side search. |

### Scaling Priorities

1. **First bottleneck: index.json size.** A flat JSON file read on every MCP query. At ~1000 engrams across all projects, JSON parse time becomes noticeable. Mitigation: project-scoped index files, or SQLite (but breaks zero-dependency constraint). Likely not an issue for years of typical use.
2. **Second bottleneck: extraction cost.** Two LLM API calls per extraction batch. With frequent commits (active development), extraction could trigger multiple times per hour. Mitigation: increase extract_threshold, debounce triggers, batch observations more aggressively.
3. **Third bottleneck: registry query latency.** Fetching skill-registry.json from multiple Workers sequentially. Mitigation: parallel fetches, longer cache TTL, or Worker-side search endpoint.

## Anti-Patterns

### Anti-Pattern 1: Blocking the Hook

**What people do:** Adding complex processing (LLM calls, HTTP requests, disk I/O beyond append) inside `capture.sh`.
**Why it's wrong:** Claude Code waits for hook completion before proceeding with the tool call. Any delay is felt by the user in real-time. A crash or timeout blocks the entire IDE session.
**Do this instead:** Append one line to JSONL (fast disk I/O). Spawn any heavy work with `nohup ... &`. Always `exit 0`.

### Anti-Pattern 2: Treating the Index as a Database

**What people do:** Adding complex queries, joins, or transactions to `index.json`. Building multiple secondary indexes. Using it for write-heavy operations.
**Why it's wrong:** `index.json` is a flat JSON file. Every read deserializes the entire file. Every write serializes and overwrites it. No concurrent write safety (file-level locking only via extraction lock).
**Do this instead:** Keep the index as a simple catalog (metadata only). Store engram content in separate `.md` files. Use the index for listing/filtering, not full-text search. Accept that search is O(n) Jaccard similarity.

### Anti-Pattern 3: Putting Team Logic in the Personal Layer

**What people do:** Having the hook or extraction pipeline directly publish to a registry. Mixing engram lifecycle with skill lifecycle.
**Why it's wrong:** Personal knowledge (engrams) and team knowledge (skills) have different lifecycles, formats, and quality bars. Engrams are mutable, decaying, personal. Skills are immutable, reviewed, team-wide. Mixing them creates confused data ownership.
**Do this instead:** Keep the bridge explicit. `prism promote` is the single crossing point. It has gates (confidence, evidence). The team flow (curate, publish) is always a separate conscious step.

### Anti-Pattern 4: Over-Stuffing the Push Layer

**What people do:** Including all engrams in `.claude/prism.md`. Or including long-form content instead of trigger summaries.
**Why it's wrong:** System prompt tokens are expensive. Every token in the push file is processed on every LLM call. A 500-line push file noticeably increases latency and cost.
**Do this instead:** Hard cap at 100 lines (configurable). Priority ordering: corrections first, then pinned, then top-by-confidence. One-liner summaries, not full content. Use MCP pull for details.

### Anti-Pattern 5: Synchronous Registry Operations in Slash Commands

**What people do:** Making `/advise-skills` fetch SKILL.md files from the Worker for every query, even when cached locally.
**Why it's wrong:** Each Worker fetch is an HTTP round-trip. Fetching 10 skills = 10 sequential HTTP calls. This makes the slash command feel slow.
**Do this instead:** Cache `skill-registry.json` with 24h TTL. Cache individual SKILL.md files after first fetch. Only hit the network when cache is stale or a skill is missing locally.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Claude Code (IDE)** | Hook events on stdin (JSON). MCP server via stdio. Skills via `.claude/skills/` symlinks. Push via `.claude/prism.md`. | All integration is file-based or stdio-based. No network required for personal layer. |
| **Claude CLI (`claude`)** | Subprocess calls for extraction/review/session analysis. `claude --model haiku -p ...` | Must be installed and authenticated. Used for LLM inference, not IDE integration. |
| **GitHub API** | Used by Worker (server-side) to read/write registry repo. Used by `prism registry create` via `gh` CLI. | Fine-grained PAT scoped to registry repo. Worker uses it for branch/commit/PR creation. |
| **Cloudflare Workers** | Worker deployed per-team. Exposes `/registry`, `/file/*`, `/publish` endpoints. Token auth. | Consumers never touch GitHub directly. Worker is the sole API surface for registry access. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| **Hook -> Extraction** | File-based (observations.jsonl) + background spawn | No direct function call. Hook writes file, spawns CLI command. Decoupled by design. |
| **Hook -> Session Reviewer** | Background spawn with session ID | Reviewer reads Claude Code's transcript files independently. |
| **Extraction -> Index** | Direct Python function call (`add_engram`) | Same process. Extraction pipeline calls index module directly. |
| **Extraction -> Sync** | Direct Python function call after extraction completes | Sync regenerates `.claude/prism.md` from updated index. |
| **MCP Server -> Index** | Direct Python import (`from lib.index import ...`) | MCP server runs as a long-lived process. Reads index on every query (file might have changed). |
| **CLI -> All Modules** | Direct Python imports from `lib/` | CLI is the orchestrator. Each command function lives in `lib/commands.py` and calls other modules. |
| **Slash Commands -> CLI** | Shell commands (`! prism ...`) or file operations | Slash commands are markdown instructions for Claude Code. They invoke CLI commands or read/write files. |
| **Slash Commands -> Worker** | HTTP via `curl` | Publishing and fetching skills goes through the Worker API. Token in env vars. |
| **Promote -> Slash Commands** | File-based handoff | `prism promote` writes to `_analysis/extracted_skills_codebase/`. Then user runs `/curate-skills` and `/publish-skills` manually. |

## Build Order (Dependency-Driven)

The components have clear dependencies that dictate build order. Components earlier in the list are depended on by later ones.

### Phase 1: Foundation (No Dependencies)

Build first because everything else depends on these:

1. **Config module** (`lib/config.py`) -- path helpers, config load/save, defaults
2. **Index module** (`lib/index.py`) -- engram CRUD, listing, filtering
3. **Scrub module** (`lib/scrub.py`) -- secret pattern matching
4. **Project module** (`lib/project.py`) -- git-based project detection
5. **Installer** (`install.sh`) -- creates `~/.prism/` tree

### Phase 2: Observation Layer (Depends on: Foundation)

Build second because extraction and review depend on observations existing:

6. **Hook** (`hooks/capture.sh`) -- write observations to JSONL
7. **CLI skeleton** (`lib/cli.py`) -- argparse router, `prism init`
8. **Init command** (`lib/commands.py:cmd_init`) -- hook registration, MCP registration

### Phase 3: Knowledge Processing (Depends on: Foundation + Observations)

Build third because context injection depends on engrams existing:

9. **Extraction pipeline** (`lib/extract.py`) -- two-phase LLM pipeline
10. **Agent prompts** (`agents/extractor.md`, `agents/validator.md`)
11. **Trigger logic** (`lib/trigger.py`) -- auto-extraction threshold
12. **Session reviewer** (`lib/review.py` + `agents/reviewer.md`)
13. **Manual commands** (`learn`, `correct`, `forget`, `maintain`)

### Phase 4: Context Injection (Depends on: Foundation + Knowledge Processing)

Build fourth because this is the value delivery mechanism:

14. **Sync engine** (`lib/sync.py`) -- generate `.claude/prism.md`
15. **MCP server** (`lib/mcp_server.py`) -- 4 tools for mid-session access

### Phase 5: Team Layer (Depends on: Foundation, parallel to Phases 2-4)

Can be built in parallel with personal layer since slash commands are independent markdown files:

16. **Slash commands** (copy from Lens, rename/unify)
17. **Promote bridge** (`lib/promote.py`) -- engram to skill conversion
18. **Registry module** (`lib/registry.py`) -- multi-registry management
19. **Registry template** (`templates/registry/`) -- Worker, CI, schemas

### Phase 6: Session Bootstrap (Depends on: Phase 3)

Build last because it's a convenience feature:

20. **Session analyzer** (`lib/sessions.py`) -- retroactive transcript analysis

### Dependency Graph (Simplified)

```
config, index, scrub, project     (Phase 1: Foundation)
        │
        ▼
capture.sh, CLI skeleton          (Phase 2: Observation)
        │
        ▼
extraction, review, manual cmds   (Phase 3: Knowledge Processing)
        │
        ├─────────────────────────────┐
        ▼                             ▼
sync, MCP server                  promote, slash cmds, registry
(Phase 4: Context Injection)      (Phase 5: Team Layer)
        │
        ▼
session analyzer                  (Phase 6: Bootstrap)
```

**Key insight for roadmap:** The personal layer (Phases 1-4) and team layer (Phase 5) share only the foundation. They can be developed largely in parallel. The bridge (`prism promote`) is the single connection point and can be built last within Phase 5.

## Sources

- Engram source code: `/Users/gaurav/codes/engram/` (direct examination of all modules)
- Lens source code: `/Users/gaurav/codes/Lens/` (direct examination of skills, Worker, scripts)
- Prism unified design document: `/Users/gaurav/codes/prism/unified-design.md`
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) -- hook event types, handler contracts
- [MCP Architecture Overview](https://modelcontextprotocol.io/docs/learn/architecture) -- stdio transport, tool registration patterns
- [Mem0 Architecture](https://mem0.ai/blog/ai-memory-layer-guide) -- two-phase extraction+update pattern, hybrid datastore, dynamic forgetting (validates Prism's confidence decay approach)
- [The Agent Memory Race of 2026](https://ossinsight.io/blog/agent-memory-race-2026) -- ecosystem survey of memory architectures, push/pull patterns

---
*Architecture research for: Prism knowledge layer for AI coding assistants*
*Researched: 2026-04-14*
