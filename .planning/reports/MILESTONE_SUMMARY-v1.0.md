# Milestone v1.0 — Project Summary

**Generated:** 2026-04-15
**Purpose:** Team onboarding and project review

---

## 1. Project Overview

**Prism** is a knowledge layer for Claude Code that does two things:
1. **Learns personal preferences** through hook-based observation and extraction into "engrams" (living, decaying knowledge units)
2. **Shares team architectural knowledge** through "skills" published to a shared registry

It unifies two existing projects — [Engram](https://github.com/ProsusAI/engram) (personal learning) and [Lens](https://github.com/ProsusAI/Lens) (team skill registry) — into a single CLI tool with a coherent interface.

**Core Value:** Claude Code remembers what you've taught it across sessions, and teams share proven architectural knowledge through a queryable registry — one install, zero-config for personal use, registry-config for team use.

**Target Users:**
- Individual developers who want Claude Code to remember their preferences, conventions, and domain knowledge across sessions
- Teams who want to share proven architectural patterns through a queryable skill registry

**Tech Stack:** Python 3.12+ (zero external dependencies), Bash for hooks/installer, TypeScript for Cloudflare Worker (registry API), Claude CLI for AI model calls (Haiku/Sonnet)

## 2. Architecture & Technical Decisions

### Core Architecture

- **Decision:** Copy-and-modify from Engram + Lens, not build from scratch
  - **Why:** Design docs don't capture all implementation detail; source code is the ground truth. Both codebases are production-quality.
  - **Phase:** Project-level

- **Decision:** Zero external Python dependencies — stdlib only
  - **Why:** Users should never need `pip install`. Every runtime import must be from Python stdlib (`json`, `argparse`, `pathlib`, `re`, `subprocess`, `datetime`).
  - **Phase:** Project-level constraint

- **Decision:** Worker-only registry access (no GitHub-direct publishing)
  - **Why:** Simplifies auth model to one API surface. Worker handles GitHub API interaction.
  - **Phase:** Project-level

### Data & Storage

- **Decision:** Flat `lib/*.py` file structure, no subdirectories
  - **Why:** Simplicity; 13 modules don't warrant packages. Matches Engram's proven layout.
  - **Phase:** 1

- **Decision:** Atomic file operations using `fcntl.flock()` + temp file + `os.rename()` + `.bak` backup
  - **Why:** Concurrent hook invocations and MCP server access can race on `index.json`. Flock prevents corruption.
  - **Phase:** 1

- **Decision:** Registry config in separate `~/.prism/registries.json` (not in `config.json`)
  - **Why:** Clean separation of concerns; registries have their own lifecycle (tokens, URLs, writable flags).
  - **Phase:** 4

- **Decision:** Per-registry cache at `~/.prism/cache/{name}.json` with 24h mtime-based TTL
  - **Why:** Avoids repeated HTTP fetches; mtime check is zero-dependency (no datetime parsing needed).
  - **Phase:** 4

### Knowledge Pipeline

- **Decision:** Two-phase extraction: Haiku proposes, Sonnet validates through 4 safety gates
  - **Why:** Haiku is cheap/fast for candidate generation; Sonnet is thorough for validation. Constitution, evidence, contradiction, and safety gates prevent bad knowledge from entering the system.
  - **Phase:** 2

- **Decision:** Time-proportional confidence decay (-0.02/week) with reinforcement on reoccurrence
  - **Why:** Knowledge that isn't reinforced fades naturally. 2.5 weeks without use = 0.05 decay. Archive at 0.2 threshold. MCP queries and observation matches both reinforce.
  - **Phase:** 2

- **Decision:** Dual-channel context injection: push (`.claude/prism.md`) + pull (MCP server)
  - **Why:** Push ensures knowledge is always available at session start. Pull enables mid-session search and recording. Priority ordering: corrections > pinned > top preferences.
  - **Phase:** 2

- **Decision:** Global and project-scoped engrams merge with `[global]`/`[project]` tags
  - **Why:** Users need both universal preferences and project-specific knowledge. Tags prevent confusion about scope.
  - **Phase:** 2

### Integration Points

- **Decision:** Single Python invocation hook with stdin pipe (no temp files)
  - **Why:** Hook performance is critical — 3 separate Python calls collapsed to 1. Stdin pipe avoids filesystem overhead. Exit 0 always.
  - **Phase:** 1

- **Decision:** Settings merge into `.claude/settings.local.json`, never clobber other tools
  - **Why:** Users may have other Claude Code tools configured. JSON merge preserves existing entries.
  - **Phase:** 1

- **Decision:** Flat-field publish payload for Worker API
  - **Why:** Worker reconstructs `plugin.json` from individual fields. Simpler than nested JSON payloads. DoS limits: 50 skills/batch, 500KB/skill content.
  - **Phase:** 4

## 3. Phases Delivered

| Phase | Name | Status | One-Liner |
|-------|------|--------|-----------|
| 1 | Foundation + Observation | Complete | Installer, CLI, hooks, and observation capture with 12-pattern secret scrubbing |
| 2 | Personal Knowledge Loop | Complete | Extraction pipeline, engram lifecycle, dual-channel context injection (push + pull) |
| 3 | Bridge + Slash Commands | Complete | Engram promotion to skill format + 12 slash commands from Lens |
| 4 | Registry | Complete | Multi-registry CRUD, template bundle, fetch/cache/merge, delta publishing |
| 5 | Integration Fixes + Hardening | Complete | Token resolution fix, project ID cache, install.sh hardening, doc fixes |

### Phase Details

**Phase 1: Foundation + Observation** (3 plans)
- Repo scaffold: 13 renamed Python modules from Engram, idempotent installer, CLI wrapper, capture hook, agent prompts, constitution template
- CLI commands: `prism init` with JSON-merge settings, `.gitignore` management, `prism.md` generation; `prism config` with dotted keys; `prism log` with `--json`
- Observation pipeline: stdin JSON processing, 12-pattern secret scrubbing, atomic JSONL append, background extraction/review triggers

**Phase 2: Personal Knowledge Loop** (5 plans)
- Agent prompt refinement for Prism ecosystem context, session analysis `--since`/`--last` flags
- Auto-sync `.claude/prism.md` after all knowledge-modifying commands
- Unified `[global]`/`[project]` scope-tagged status display with decay/archive lifecycle
- MCP server scope tagging, batch reinforcement, record auto-sync
- Integration verification: all 13 modules import cleanly, MCP protocol correct, learn/sync pipeline end-to-end

**Phase 3: Bridge + Slash Commands** (3 plans)
- `cmd_promote()` with gate checks (confidence >= 0.7, evidence >= 3), plugin.json + SKILL.md output
- 9 slash commands bridged from Lens: 4 Tier 1 verbatim copies, 5 Tier 2 with Prism adaptations
- Unified `/publish-skills` with Worker API delta tracking, `/advise-skills` and `/audit-code` with 3-tier registry fallback

**Phase 4: Registry** (3 plans)
- `lib/registry.py` with 10 CRUD functions, CLI subcommand group with nested token management, auto-migration from `config.json`
- Registry template: Cloudflare Worker, CI workflows, validation scripts, JSON Schema bundled for `prism registry create`
- Multi-registry fetch with 24h per-registry mtime cache, source-tagged merge, per-registry publish delta tracking

**Phase 5: Integration Fixes + Hardening** (2 plans)
- Fixed `/publish-skills` token resolution from `registries.json` (no `REGISTRY_TOKEN` env var required)
- Project ID cache (`.claude/.prism_project_id`), `PRISM_PROJECT_ID` env var standardization, install.sh test-file exclusion

## 4. Requirements Coverage

**83/83 v1 requirements complete (100%)**

- **SETUP (14):** SETUP-01 through SETUP-14 -- installer, init, config, CLI wrapper
- **OBS (8):** OBS-01 through OBS-08 -- hook capture, scrubbing, background triggers, log command
- **EXT (12):** EXT-01 through EXT-12 -- two-phase extraction, validation gates, session reviewer
- **ENG (12):** ENG-01 through ENG-12 -- engram CRUD, lifecycle, procedures, scope separation
- **CTX (9):** CTX-01 through CTX-09 -- push layer (.claude/prism.md), pull layer (MCP 4 tools)
- **BRG (4):** BRG-01 through BRG-04 -- promotion gates, format conversion, local-only operation
- **SKILL (12):** SKILL-01 through SKILL-12 -- 12 slash commands for analysis, curation, publishing, querying
- **REG (12):** REG-01 through REG-12 -- registry CRUD, token management, template, multi-registry reads/writes

No requirements were dropped or deferred to v2. All map to completed phases in the traceability table.

## 5. Key Decisions Log

| # | Decision | Phase | Rationale |
|---|----------|-------|-----------|
| 1 | Copy-and-modify from Engram + Lens | Project | Source code is ground truth; both codebases are production-quality |
| 2 | Zero Python dependencies (stdlib only) | Project | One install, no pip; `json`, `argparse`, `pathlib`, `re`, `subprocess` |
| 3 | Worker-only registry access | Project | Single auth surface; Worker handles GitHub API |
| 4 | Fork and forget — Prism is canonical | Phase 1 | No backporting to Engram/Lens |
| 5 | Preserve "engrams" as data format name | Phase 1 | Renaming would break data model compatibility |
| 6 | `fcntl.flock()` + temp + `os.rename()` for atomic writes | Phase 1 | Concurrent hook/MCP access races on index.json |
| 7 | Single Python invocation hook, stdin pipe | Phase 1 | Collapse 3 calls to 1; no temp files |
| 8 | Settings merge, never clobber other tools | Phase 1 | Users may have other Claude Code extensions |
| 9 | Haiku proposes, Sonnet validates (4 gates) | Phase 2 | Cheap/fast candidate gen, thorough validation |
| 10 | Time-proportional decay (-0.02/week) | Phase 2 | Natural knowledge freshness; archive at 0.2 |
| 11 | Dual-channel: push (prism.md) + pull (MCP) | Phase 2 | Session-start coverage + mid-session access |
| 12 | Global + project engrams merge with scope tags | Phase 2 | Both universal and project-specific knowledge |
| 13 | MCP reinforcement boost 0.02 per query | Phase 2 | Smaller than observation match (0.05), capped at 0.95 |
| 14 | stdout suppression via io.StringIO in MCP | Phase 2 | Prevents JSON-RPC protocol corruption |
| 15 | Promoted skills to `_analysis/extracted_skills_codebase/` | Phase 3 | Matches Lens convention; source field distinguishes from extracted |
| 16 | 3-tier registry fallback: remote > local cache > local analysis | Phase 3 | Graceful degradation from online to offline |
| 17 | Separate `registries.json` (not in config.json) | Phase 4 | Clean lifecycle separation; tokens, URLs, writable flags |
| 18 | Per-registry mtime-based 24h TTL cache | Phase 4 | Zero-dependency; avoids repeated HTTP fetches |
| 19 | Template files bundled under `templates/registry/` | Phase 4 | Single repo; `prism registry create` copies them |
| 20 | Flat-field publish payload with DoS limits | Phase 4 | Worker reconstructs plugin.json; 50 skills/batch, 500KB/skill |

## 6. Tech Debt & Deferred Items

### Known Items from Code Review (Phase 5)

The Phase 5 code review found 10 issues. All 6 critical/warning items were auto-fixed:
- Path traversal guard added to MCP `_get_entry_content`
- Race condition fixed in `_update_gitignore`
- Server-side `kind` validation added to MCP `_record`
- Empty path guard in `cmd_forget`
- Batched index modifications in `cmd_maintain`

4 info-level items remain (unused imports, bare `except: pass` in template code).

### Human Verification Pending

Phase 1 VERIFICATION.md identified 3 human integration tests:
1. Run `install.sh` on clean machine, verify idempotent re-run
2. Run `prism init` with existing `.claude/settings.local.json`, verify merge preserves other entries
3. Use Claude Code with hooks, verify `prism log` shows observations without perceptible delay

### v2 Requirements (Deferred)

- **SCRUB-01/02:** Expanded secret patterns (AWS, JWTs, private keys) + multi-layer scrubbing
- **PERF-01/02:** Single Python invocation hook optimization + `async: true` PostToolUse
- **OBSV-01/02:** Extraction quality metrics + hook latency monitoring

### Architectural Notes

- ROADMAP.md progress table has stale counts for phases 2-5 (shows "0/N" for plans in completed phases) — cosmetic only, checkboxes are correct
- `config.json` heredoc in install.sh intentionally omits `scrub_patterns` and `block_patterns` (large arrays merged from DEFAULT_CONFIG at runtime)

## 7. Getting Started

### Run the Project

```bash
# Install Prism
git clone <repo-url>
cd prism
./install.sh

# Initialize in any project
cd /path/to/your/project
prism init

# Verify installation
prism status
prism log
```

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `lib/` | Python library (13 modules) — commands, config, capture, extraction, MCP server, bridge, registry |
| `hooks/` | Shell hooks for Claude Code integration (`capture.sh`) |
| `agents/` | AI agent prompts for extraction (`extractor.md`) and review (`reviewer.md`) |
| `skills/` | 12 slash commands for analysis, extraction, curation, publishing, querying |
| `templates/` | Registry template (Cloudflare Worker, CI, schema) and file templates |
| `~/.prism/` | User's installed Prism (created by `install.sh`) |

### Core Modules

| Module | Purpose |
|--------|---------|
| `lib/commands.py` | All CLI commands (init, learn, correct, forget, status, maintain, promote, registry) |
| `lib/capture.py` | Hook observation processing (stdin JSON, scrubbing, JSONL append) |
| `lib/extraction.py` | Two-phase extraction pipeline (Haiku propose, Sonnet validate) |
| `lib/mcp_server.py` | MCP server (stdio JSON-RPC, 4 tools: search, get, relevant, record) |
| `lib/registry.py` | Multi-registry CRUD, token management, fetch/cache/merge |
| `lib/bridge.py` | Engram-to-skill promotion |
| `lib/scrub.py` | Secret scrubbing (12 baseline patterns + configurable) |
| `lib/sync.py` | `.claude/prism.md` generation with priority ordering |
| `lib/config.py` | Configuration management with dotted key access |
| `lib/index.py` | Engram index CRUD with atomic file operations |

### Tests

No automated test suite yet (deferred to v2). Manual testing via:
```bash
prism status          # Check engram health
prism log             # Verify observation capture
prism init            # Verify hook/MCP setup
```

### Where to Look First

1. **`lib/commands.py`** — Entry point for all CLI commands; start here to understand what Prism does
2. **`lib/capture.py`** — How observations flow in (hook -> scrub -> JSONL)
3. **`lib/mcp_server.py`** — How Claude Code queries knowledge mid-session
4. **`lib/sync.py`** — How knowledge flows back (engrams -> prioritized .claude/prism.md)
5. **`install.sh`** — How everything gets deployed to `~/.prism/`

---

## Stats

- **Timeline:** 2026-04-14 -> 2026-04-15 (2 days)
- **Phases:** 5/5 complete
- **Plans:** 16/16 executed
- **Requirements:** 83/83 met (100%)
- **Commits:** 104
- **Files changed:** 394 (+94,715 / -197)
- **Contributors:** Gaurav
