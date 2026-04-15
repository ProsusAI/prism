# Requirements: Prism

**Defined:** 2026-04-14
**Core Value:** Claude Code remembers what you've taught it across sessions, and teams share proven architectural knowledge through a queryable registry

## v1 Requirements

### Installation & Setup

- [x] **SETUP-01**: `install.sh` creates `~/.prism/` tree (lib, agents, hooks, skills, global/engrams, archive) and copies all components
- [x] **SETUP-02**: `install.sh` creates CLI wrapper at `~/.local/bin/prism`
- [x] **SETUP-03**: `install.sh` writes default `config.json` and empty `index.json`
- [x] **SETUP-04**: `install.sh` copies `constitution.md` template (only if not exists -- never overwrites)
- [x] **SETUP-05**: `install.sh` is idempotent -- re-running updates lib/agents/hooks/skills but preserves config, index, constitution, project data
- [x] **SETUP-06**: `install.sh` checks prerequisites (python3, git, claude) before proceeding
- [x] **SETUP-07**: `install.sh` works from both `curl | bash` (public) and `git clone` (private repo) paths
- [x] **SETUP-08**: `prism init` detects project ID from git remote (SHA256[:12] of origin URL)
- [x] **SETUP-09**: `prism init` configures hooks in `.claude/settings.local.json` (PreToolUse + PostToolUse)
- [x] **SETUP-10**: `prism init` registers MCP server in `.claude/settings.local.json`
- [x] **SETUP-11**: `prism init` symlinks slash commands from `~/.prism/skills/` to `.claude/skills/`
- [x] **SETUP-12**: `prism init` adds `.claude/skills/`, `.claude/prism.md`, `.claude/settings.local.json` to `.gitignore`
- [x] **SETUP-13**: `prism init` generates initial `.claude/prism.md` (push layer)
- [x] **SETUP-14**: `prism config [key] [value]` gets/sets configuration values

### Observation Capture

- [x] **OBS-01**: `capture.sh` hook receives JSON on stdin (`tool_name`, `tool_input`, `session_id`) from PreToolUse/PostToolUse
- [x] **OBS-02**: `capture.sh` scrubs secrets before writing (API keys, tokens, bearer, sk-*, ghp-*)
- [x] **OBS-03**: `capture.sh` truncates `input_summary` to 500 chars
- [x] **OBS-04**: `capture.sh` appends JSONL line to `~/.prism/projects/<hash>/observations.jsonl`
- [x] **OBS-05**: `capture.sh` never blocks Claude Code (exit 0 always, background spawns)
- [x] **OBS-06**: `capture.sh` spawns background extraction at 15 observations
- [x] **OBS-07**: `capture.sh` spawns background session review every 5 observations
- [x] **OBS-08**: `prism log [--last N] [--insights]` shows recent observations

### Knowledge Extraction

- [x] **EXT-01**: Two-phase extraction: Haiku proposes candidates from observations, writes to `candidates/`
- [x] **EXT-02**: Sonnet validates candidates through 4 gates: constitution, evidence, contradiction, safety
- [x] **EXT-03**: Approved candidates move to `engrams/` and are added to index; rejected are deleted with logged reason; modified are adjusted then moved
- [x] **EXT-04**: Extraction produces typed engrams: preference, correction, procedure, domain_fact, tool_pattern, error_recipe
- [x] **EXT-05**: Post-extraction: archive observations, regenerate `.claude/prism.md`
- [x] **EXT-06**: `prism extract [--project <id>]` triggers extraction pipeline manually
- [x] **EXT-07**: Constitution safety principles (`constitution.md`) are loaded during validation and never overwritten by updates
- [x] **EXT-08**: Background session reviewer (Haiku, no tools) scans session transcripts for corrections, preferences, design decisions, domain knowledge, non-obvious solutions
- [x] **EXT-09**: Session reviewer appends findings as observations feeding into next extraction cycle
- [x] **EXT-10**: `prism review --session <id>` triggers session review manually
- [x] **EXT-11**: `prism analyze-sessions [--all]` bootstraps engrams from past Claude Code session transcripts
- [x] **EXT-12**: Validation decisions logged to `validation-log.jsonl` for auditability

### Engram Management

- [x] **ENG-01**: Engrams stored as markdown files with YAML frontmatter (confidence, evidence count, timestamps, type, source)
- [x] **ENG-02**: Master engram index (`index.json`) tracks all engrams with CRUD operations
- [x] **ENG-03**: `prism learn "<text>" [--scope global]` creates engram at confidence 0.9, auto-syncs `.claude/prism.md`
- [x] **ENG-04**: `prism correct <id> "<text>"` supersedes engram with correction, auto-syncs
- [x] **ENG-05**: `prism forget <id>` archives engram (recoverable), auto-syncs
- [x] **ENG-06**: `prism status [--project <id>]` shows engrams, stats, and health
- [x] **ENG-07**: Confidence lifecycle: decay -0.02/week without reinforcement, bump on reoccurrence
- [x] **ENG-08**: Engrams archive at confidence threshold 0.2 (moved to `archive/`, recoverable)
- [x] **ENG-09**: `prism maintain` runs decay cycle and archives expired engrams
- [x] **ENG-10**: `prism procedures` lists procedures with success/failure stats
- [x] **ENG-11**: Global engrams stored in `~/.prism/global/engrams/`, project engrams in `~/.prism/projects/<hash>/engrams/`
- [x] **ENG-12**: Analyzed sessions tracked in `analyzed-sessions.json` to prevent re-processing

### Context Injection

- [x] **CTX-01**: Push layer: `prism sync` regenerates `.claude/prism.md` with priority ordering (corrections > pinned > top preferences > session-validated > publish-ready)
- [x] **CTX-02**: Push layer respects max context lines (default 100, configurable)
- [x] **CTX-03**: Push layer includes MCP nudge footer ("Use prism_search for relevant knowledge...")
- [x] **CTX-04**: `.claude/prism.md` auto-regenerated after: learn, correct, forget, extract, maintain
- [x] **CTX-05**: MCP server provides `prism_search` tool (natural language search across engrams)
- [x] **CTX-06**: MCP server provides `prism_get` tool (read full engram by ID)
- [x] **CTX-07**: MCP server provides `prism_relevant` tool (find engrams for current file/domain)
- [x] **CTX-08**: MCP server provides `prism_record` tool (create new engram mid-session at confidence 0.9)
- [x] **CTX-09**: MCP server communicates via stdio JSON-RPC (implements initialize, tools/list, tools/call, ping)

### Bridge (Engram to Skill)

- [x] **BRG-01**: `prism promote <id>` checks gates: confidence >= 0.7, evidence >= 3, source != "registry"
- [x] **BRG-02**: Promotion converts engram markdown to `plugin.json` + `SKILL.md` format
- [x] **BRG-03**: Promoted skills written to `_analysis/extracted_skills_codebase/<name>/`
- [x] **BRG-04**: Promotion is local-only (no network needed, works without registry)

### Slash Commands

- [x] **SKILL-01**: `/run-analysis-pipeline` — guided full codebase analysis (agentic or general)
- [x] **SKILL-02**: `/run-history-pipeline` — git history to failure pattern skills
- [x] **SKILL-03**: `/analyze-agent-codebase` — deep 6-cluster agentic analysis
- [x] **SKILL-04**: `/extract-skills` — analysis report to skills
- [x] **SKILL-05**: `/mine-history` — mine git log for incidents and decisions
- [x] **SKILL-06**: `/mine-design` — extract design decisions from current source
- [x] **SKILL-07**: `/synthesize` — incident clusters to skills
- [x] **SKILL-08**: `/synthesize-decisions` — design decisions to skills
- [x] **SKILL-09**: `/curate-skills` — quality pass: keep / delete / merge / rewrite
- [x] **SKILL-10**: `/publish-skills [--registry NAME] [--all]` — publish delta to registry, creates PR
- [x] **SKILL-11**: `/advise-skills <query>` — search all configured registries for matching skills
- [x] **SKILL-12**: `/audit-code` — proactive codebase check against all registries

### Registry

- [x] **REG-01**: `prism registry create` — interactive flow: create GitHub repo from template, deploy Cloudflare Worker, generate API tokens, configure local Prism
- [x] **REG-02**: `prism registry add NAME --url URL [--token T] [--read-only]` — add registry to config
- [x] **REG-03**: `prism registry remove NAME` — remove registry from config
- [x] **REG-04**: `prism registry list` — show configured registries
- [x] **REG-05**: `prism registry default NAME` — set default push target
- [x] **REG-06**: `prism registry token create NAME` — generate new API token
- [x] **REG-07**: `prism registry token revoke NAME TOKEN` — revoke an API token
- [x] **REG-08**: Registry template bundled in tool repo (Worker source, CI workflows, validation schema, build scripts)
- [x] **REG-09**: Multi-registry reads: merge `skill-registry.json` from all sources, cache locally with 24h TTL
- [x] **REG-10**: Multi-registry writes: publish delta only (tracked via `.published.json` with content hashes per registry)
- [x] **REG-11**: Query results tagged with source registry (e.g., `[team]`, `[community]`)
- [x] **REG-12**: `/publish-skills` resolves target registry, checks writable, diffs against `.published.json`, POSTs delta

## v2 Requirements

### Enhanced Scrubbing

- **SCRUB-01**: Expand secret patterns to cover AWS keys (AKIA*), connection strings, private keys, JWTs, high-entropy tokens
- **SCRUB-02**: Multi-layer scrubbing: capture-time, extraction-time, publish-time

### Performance Optimization

- **PERF-01**: Collapse hook to single Python invocation with cached project ID (from current 3 calls)
- **PERF-02**: Use `async: true` hook type for PostToolUse capture

### Observability

- **OBSV-01**: Extraction quality metrics (acceptance rate, gate failure distribution)
- **OBSV-02**: Hook latency monitoring

## Out of Scope

| Feature | Reason |
|---------|--------|
| GUI/web dashboard | CLI-native target audience; doubles maintenance burden with no competitive precedent |
| Non-Claude Code editor support | Each editor has fundamentally different hook/extension architecture; Claude Code hooks are uniquely suited |
| Real-time sync between team members | Async publish-merge-refresh is more predictable; registry is architectural knowledge that changes slowly |
| Vector/embedding-based semantic search | Adds vector DB dependency (breaks zero-dep constraint); keyword search sufficient for expected scale |
| OAuth/SSO for registry access | Token-based auth is simpler, works everywhere, sufficient for current use case |
| Full codebase indexing/RAG | Augment Code does this; Prism stores what codebase search cannot (preferences, conventions, decisions) |
| Engram import/export between users | Knowledge flows through registry via promote/publish; direct sharing creates trust/conflict issues |
| Memory consolidation/"dreaming" | Engram lifecycle (decay, archive, promote) already manages quality; structured storage doesn't need consolidation |
| Non-Claude Code registry template repo | Template files bundled in tool repo; not a separate development effort |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SETUP-01 | Phase 1 | Complete |
| SETUP-02 | Phase 1 | Complete |
| SETUP-03 | Phase 1 | Complete |
| SETUP-04 | Phase 1 | Complete |
| SETUP-05 | Phase 1 | Complete |
| SETUP-06 | Phase 1 | Complete |
| SETUP-07 | Phase 1 | Complete |
| SETUP-08 | Phase 1 | Complete |
| SETUP-09 | Phase 1 | Complete |
| SETUP-10 | Phase 1 | Complete |
| SETUP-11 | Phase 1 | Complete |
| SETUP-12 | Phase 1 | Complete |
| SETUP-13 | Phase 1 | Complete |
| SETUP-14 | Phase 1 | Complete |
| OBS-01 | Phase 1 | Complete |
| OBS-02 | Phase 1 | Complete |
| OBS-03 | Phase 1 | Complete |
| OBS-04 | Phase 1 | Complete |
| OBS-05 | Phase 1 | Complete |
| OBS-06 | Phase 1 | Complete |
| OBS-07 | Phase 1 | Complete |
| OBS-08 | Phase 1 | Complete |
| EXT-01 | Phase 2 | Complete |
| EXT-02 | Phase 2 | Complete |
| EXT-03 | Phase 2 | Complete |
| EXT-04 | Phase 2 | Complete |
| EXT-05 | Phase 2 | Complete |
| EXT-06 | Phase 2 | Complete |
| EXT-07 | Phase 2 | Complete |
| EXT-08 | Phase 2 | Complete |
| EXT-09 | Phase 2 | Complete |
| EXT-10 | Phase 2 | Complete |
| EXT-11 | Phase 2 | Complete |
| EXT-12 | Phase 2 | Complete |
| ENG-01 | Phase 2 | Complete |
| ENG-02 | Phase 2 | Complete |
| ENG-03 | Phase 2 | Complete |
| ENG-04 | Phase 2 | Complete |
| ENG-05 | Phase 2 | Complete |
| ENG-06 | Phase 2 | Complete |
| ENG-07 | Phase 2 | Complete |
| ENG-08 | Phase 2 | Complete |
| ENG-09 | Phase 2 | Complete |
| ENG-10 | Phase 2 | Complete |
| ENG-11 | Phase 2 | Complete |
| ENG-12 | Phase 2 | Complete |
| CTX-01 | Phase 2 | Complete |
| CTX-02 | Phase 2 | Complete |
| CTX-03 | Phase 2 | Complete |
| CTX-04 | Phase 2 | Complete |
| CTX-05 | Phase 2 | Complete |
| CTX-06 | Phase 2 | Complete |
| CTX-07 | Phase 2 | Complete |
| CTX-08 | Phase 2 | Complete |
| CTX-09 | Phase 2 | Complete |
| BRG-01 | Phase 3 | Complete |
| BRG-02 | Phase 3 | Complete |
| BRG-03 | Phase 3 | Complete |
| BRG-04 | Phase 3 | Complete |
| SKILL-01 | Phase 3 | Complete |
| SKILL-02 | Phase 3 | Complete |
| SKILL-03 | Phase 3 | Complete |
| SKILL-04 | Phase 3 | Complete |
| SKILL-05 | Phase 3 | Complete |
| SKILL-06 | Phase 3 | Complete |
| SKILL-07 | Phase 3 | Complete |
| SKILL-08 | Phase 3 | Complete |
| SKILL-09 | Phase 3 | Complete |
| SKILL-10 | Phase 5 | Complete |
| SKILL-11 | Phase 3 | Complete |
| SKILL-12 | Phase 3 | Complete |
| REG-01 | Phase 4 | Complete |
| REG-02 | Phase 4 | Complete |
| REG-03 | Phase 4 | Complete |
| REG-04 | Phase 4 | Complete |
| REG-05 | Phase 4 | Complete |
| REG-06 | Phase 4 | Complete |
| REG-07 | Phase 4 | Complete |
| REG-08 | Phase 4 | Complete |
| REG-09 | Phase 4 | Complete |
| REG-10 | Phase 5 | Complete |
| REG-11 | Phase 4 | Complete |
| REG-12 | Phase 4 | Complete |

**Coverage:**
- v1 requirements: 83 total
- Mapped to phases: 83
- Unmapped: 0

---
*Requirements defined: 2026-04-14*
*Last updated: 2026-04-15 after milestone audit gap closure planning*
