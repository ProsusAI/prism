# Roadmap: Prism

## Overview

Prism unifies Engram (personal learning) and Lens (team skill registry) into a single CLI knowledge layer for Claude Code. The roadmap follows the natural dependency chain: first establish the foundation and observation capture, then build the complete personal knowledge loop (extraction, management, context injection, lifecycle), then bridge personal knowledge to team skill format with slash commands, and finally deliver the team registry layer. This is a copy-and-modify project from two working codebases, not a greenfield build.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation + Observation** - Installer, project init, CLI skeleton, and hook-based observation capture with secret scrubbing
- [ ] **Phase 2: Personal Knowledge Loop** - Extraction pipeline, engram management, confidence lifecycle, and dual-channel context injection (push + pull)
- [ ] **Phase 3: Bridge + Slash Commands** - Engram-to-skill promotion and the full suite of 12 Lens slash commands for analysis, curation, and publishing
- [ ] **Phase 4: Registry** - Registry creation, multi-registry management, template bundling, and cross-registry queries
- [ ] **Phase 5: Integration Fixes + Hardening** - Fix publish-skills token bug, project ID cache, install.sh cleanups, stale doc updates (gap closure)

## Phase Details

### Phase 1: Foundation + Observation
**Goal**: User can install Prism, initialize any project for learning, and Claude Code tool usage flows into observation logs
**Depends on**: Nothing (first phase)
**Requirements**: SETUP-01, SETUP-02, SETUP-03, SETUP-04, SETUP-05, SETUP-06, SETUP-07, SETUP-08, SETUP-09, SETUP-10, SETUP-11, SETUP-12, SETUP-13, SETUP-14, OBS-01, OBS-02, OBS-03, OBS-04, OBS-05, OBS-06, OBS-07, OBS-08
**Success Criteria** (what must be TRUE):
  1. User can run `install.sh` and get a working `~/.prism/` tree with CLI at `~/.local/bin/prism`, and re-running preserves existing config/data
  2. User can run `prism init` in any git project and have hooks, MCP server, slash command symlinks, and `.claude/prism.md` configured automatically
  3. Claude Code tool usage is captured as JSONL observations with secrets scrubbed, without any perceptible delay to the user's Claude Code session
  4. User can run `prism log` to see recent observations and `prism config` to manage settings
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Repo scaffold: copy and rename all Engram lib/*.py, create install.sh, CLI wrapper, capture.sh shell, agents, templates
- [x] 01-02-PLAN.md — CLI commands: prism init (JSON merge into settings.local.json), prism config, prism log with --json, wire CLI router
- [x] 01-03-PLAN.md — Observation pipeline: lib/capture.py (stdin JSON processing, scrubbing, JSONL append, triggers), expanded scrub patterns

### Phase 2: Personal Knowledge Loop
**Goal**: Prism extracts validated knowledge from observations, user can manage engrams manually, knowledge flows back into Claude Code sessions through push and pull channels, and knowledge stays fresh through confidence decay and reinforcement
**Depends on**: Phase 1
**Requirements**: EXT-01, EXT-02, EXT-03, EXT-04, EXT-05, EXT-06, EXT-07, EXT-08, EXT-09, EXT-10, EXT-11, EXT-12, ENG-01, ENG-02, ENG-03, ENG-04, ENG-05, ENG-06, ENG-07, ENG-08, ENG-09, ENG-10, ENG-11, ENG-12, CTX-01, CTX-02, CTX-03, CTX-04, CTX-05, CTX-06, CTX-07, CTX-08, CTX-09
**Success Criteria** (what must be TRUE):
  1. Observations are automatically extracted into typed engrams through a two-phase pipeline (Haiku proposes, Sonnet validates through 4 safety gates), with extraction triggering automatically at 15 observations and manually via `prism extract`
  2. User can run `prism learn`, `prism correct`, and `prism forget` to manually manage engrams, with changes immediately reflected in `.claude/prism.md`
  3. `.claude/prism.md` is auto-generated with priority ordering (corrections > pinned > top preferences) and stays in sync after every knowledge change, so Claude Code reads current knowledge at session start
  4. MCP server exposes `prism_search`, `prism_get`, `prism_relevant`, and `prism_record` tools for mid-session knowledge access via stdio JSON-RPC
  5. Engrams decay in confidence without reinforcement (-0.02/week), get reinforced on reoccurrence, and archive at 0.2 threshold -- `prism maintain` runs the lifecycle and `prism status` shows current state
**Plans**: 5 plans

Plans:
- [x] 02-01-PLAN.md — Agent prompt refinement for Prism ecosystem context, session analysis --since/--last flags
- [x] 02-02-PLAN.md — Auto-sync wiring for learn/correct/forget/maintain/extract, post-extraction sync
- [x] 02-03-PLAN.md — Unified scope-tagged status display, lifecycle decay/archive verification
- [x] 02-04-PLAN.md — MCP server scope tagging, batch reinforcement, record auto-sync
- [x] 02-05-PLAN.md — Integration verification suite and human end-to-end checkpoint

### Phase 3: Bridge + Slash Commands
**Goal**: High-quality personal engrams can be promoted to publishable team skill format, and the full suite of slash commands for codebase analysis, skill extraction, curation, publishing, and querying is available
**Depends on**: Phase 2
**Requirements**: BRG-01, BRG-02, BRG-03, BRG-04, SKILL-01, SKILL-02, SKILL-03, SKILL-04, SKILL-05, SKILL-06, SKILL-07, SKILL-08, SKILL-09, SKILL-10, SKILL-11, SKILL-12
**Success Criteria** (what must be TRUE):
  1. User can run `prism promote <id>` to convert a high-confidence engram (>=0.7, evidence >=3) into `plugin.json` + `SKILL.md` skill format, with promotion working fully offline
  2. All 12 slash commands from Lens are available in any initialized project: analysis pipelines (`/run-analysis-pipeline`, `/run-history-pipeline`, `/analyze-agent-codebase`), extraction (`/extract-skills`, `/mine-history`, `/mine-design`, `/synthesize`, `/synthesize-decisions`), curation (`/curate-skills`), and publishing/querying (`/publish-skills`, `/advise-skills`, `/audit-code`)
  3. `/publish-skills` publishes only changed skills (delta tracking via `.published.json`) and supports targeting a specific registry
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md — Promotion bridge: lib/bridge.py cmd_promote, CLI wiring, config update, schema + install.sh skills copy
- [x] 03-02-PLAN.md — Tier 1 + Tier 2 slash commands: 9 commands copied/adapted from Lens (analysis, extraction, mining, curation)
- [x] 03-03-PLAN.md — Tier 3 slash commands: unified /publish-skills with delta tracking, /advise-skills and /audit-code for Prism config

### Phase 4: Registry
**Goal**: Teams can create, configure, and manage shared skill registries backed by GitHub repos and Cloudflare Workers, with full multi-registry support for reading, writing, and querying across organizational boundaries
**Depends on**: Phase 3
**Requirements**: REG-01, REG-02, REG-03, REG-04, REG-05, REG-06, REG-07, REG-08, REG-09, REG-10, REG-11, REG-12
**Success Criteria** (what must be TRUE):
  1. User can run `prism registry create` to set up a new team registry (GitHub repo from template + Cloudflare Worker deployment + API tokens), and the registry template is bundled in the tool repo
  2. User can manage multiple registries with `prism registry add/remove/list/default` and manage API tokens with `prism registry token create/revoke`
  3. Multi-registry reads merge `skill-registry.json` from all configured sources with 24h TTL cache, and query results are tagged with source registry (e.g., `[team]`, `[community]`)
  4. `/advise-skills` and `/audit-code` search across all configured registries, and `/publish-skills` tracks deltas per-registry via `.published.json` with content hashes
**Plans**: 3 plans

Plans:
- [x] 04-01-PLAN.md — Registry config layer: lib/registry.py CRUD, CLI subcommand group, token management
- [x] 04-02-PLAN.md — Registry template bundle: Cloudflare Worker, CI workflows, scripts, schema, install.sh update
- [x] 04-03-PLAN.md — Multi-registry reads/writes: fetch+cache+merge, create wizard, slash command updates

### Phase 5: Integration Fixes + Hardening
**Goal**: Fix integration bugs found during milestone audit (publish-skills token resolution, project ID cache, install.sh cleanups) and update stale documentation
**Depends on**: Phase 4
**Requirements**: SKILL-10, REG-10, OBS-05, SETUP-01, SETUP-03
**Gap Closure**: Closes gaps from v1.0 milestone audit
**Success Criteria** (what must be TRUE):
  1. `/publish-skills` works with per-registry tokens from registries.json (no REGISTRY_TOKEN env var required)
  2. `prism init` writes `.claude/.prism_project_id` cache file and hook/MCP env var names are consistent
  3. `install.sh` excludes test files from `~/.prism/lib/` and config.json heredoc includes all DEFAULT_CONFIG keys
  4. REQUIREMENTS.md checkboxes updated for BRG-01-04, SKILL-01-09; 04-02-SUMMARY.md frontmatter corrected
**Plans**: 2 plans

Plans:
- [ ] 05-01-PLAN.md — Fix /publish-skills token resolution from registries.json (no env var required)
- [ ] 05-02-PLAN.md — Project ID cache, env var standardization, install.sh hardening, doc fixes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation + Observation | 3/3 | Complete | 2026-04-14 |
| 2. Personal Knowledge Loop | 0/5 | Planning complete | - |
| 3. Bridge + Slash Commands | 0/3 | Planning complete | - |
| 4. Registry | 0/2 | Not started | - |
| 5. Integration Fixes + Hardening | 0/2 | Planning complete | - |
