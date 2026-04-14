# Prism

## What This Is

Prism is a knowledge layer for Claude Code that does two things: learns personal preferences through hook-based observation and extraction into "engrams" (living, decaying knowledge), and shares team architectural knowledge through "skills" published to a shared registry. It unifies two existing projects — [Engram](https://github.com/ProsusAI/engram) (personal learning) and [Lens](https://github.com/ProsusAI/Lens) (team skill registry) — into a single CLI tool with a coherent interface.

## Core Value

Claude Code remembers what you've taught it across sessions, and teams share proven architectural knowledge through a queryable registry — one install, zero-config for personal use, registry-config for team use.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Installer (`install.sh`) sets up `~/.prism/` tree, copies lib/agents/hooks/skills, creates CLI wrapper
- [ ] `prism init` configures hooks, MCP server, slash command symlinks, and `.claude/prism.md` for any project
- [ ] Hook-based observation capture (`capture.sh`) records tool usage to `observations.jsonl` without blocking Claude Code
- [ ] Two-phase extraction pipeline: Haiku proposes candidates, Sonnet validates through 4 safety gates (constitution, evidence, contradiction, safety)
- [ ] Background session reviewer (Haiku) scans transcripts for corrections, preferences, decisions
- [ ] Engram lifecycle: confidence scoring (0.0-0.9), reinforcement on reoccurrence, decay without use (-0.02/week), archive at threshold (0.2)
- [ ] `prism learn` / `prism correct` / `prism forget` for manual engram management (auto-syncs `.claude/prism.md`)
- [ ] `prism status` shows engrams, stats, and health for current or specified project
- [ ] Context injection — push: `.claude/prism.md` (priority-ordered: corrections > pinned > top preferences); pull: MCP server (`prism_search`, `prism_get`, `prism_relevant`, `prism_record`)
- [ ] MCP server provides 4 tools for mid-session knowledge access and recording
- [ ] Secret scrubbing on all captured observations (API keys, tokens, bearer, sk-*, ghp-*)
- [ ] `prism promote` converts high-confidence engrams (>=0.7, evidence >=3) to skill format (`plugin.json` + `SKILL.md`)
- [ ] 12 slash commands carried from Lens: extraction pipelines, quality/publishing, and querying
- [ ] `/publish-skills` unified command with delta tracking (`.published.json`), multi-registry support
- [ ] `/advise-skills` and `/audit-code` query across all configured registries with source tagging
- [ ] `prism registry create` orchestrates GitHub repo from template + Cloudflare Worker deployment + token generation
- [ ] `prism registry add/remove/list/default` for multi-registry management
- [ ] `prism registry token create/revoke` for API token management
- [ ] Multi-registry reads: merge `skill-registry.json` from all sources, cached with 24h TTL
- [ ] Multi-registry writes: publish delta to specific registry, tracked per-registry in `.published.json`
- [ ] Registry template bundled in tool repo (Worker source, CI workflows, validation schema, build scripts)
- [ ] `prism maintain` runs decay cycle and archives expired engrams
- [ ] `prism analyze-sessions` bootstraps engrams from past Claude Code session transcripts
- [ ] Global vs project-scoped engrams (`--scope global` on `prism learn`)
- [ ] Constitution safety principles (never overwritten by updates)
- [ ] Idempotent installer (re-run updates code but preserves config, index, constitution, project data)

### Out of Scope

- Prism-registry-template as a separate development effort — the template files are bundled in the tool repo
- Non-Claude Code editors (Cursor, etc.) — Claude Code only
- OAuth/SSO for registry access — token-based auth only
- Real-time sync between team members — registry is async (publish PR, merge, cache refresh)
- GUI/web dashboard — CLI and slash commands only
- Engram import/export between users — knowledge flows through the registry

## Context

**Source codebases:** Engram (`/Users/gaurav/codes/engram`) provides the entire personal layer: Python library, hooks, extraction agents, MCP server, session reviewer, CLI commands. Lens (`/Users/gaurav/codes/Lens`) provides the entire team layer: 12 slash commands, Cloudflare Worker, skill format, registry schema, CI validation. Both are working codebases with production-level code.

**Approach:** Copy bulk of both codebases with targeted modifications. Engram's Python library becomes `~/.prism/lib/`, Lens's slash commands become `~/.prism/skills/`. New bridging code unifies them: single CLI (`prism`), multi-registry management, publish tracking, promotion from engram to skill.

**Key renames:** `engram` -> `prism`, `ENGRAM_HOME` -> `PRISM_HOME`, MCP tools renamed (`engram_search` -> `prism_search`, etc.).

**Dropped from Engram:** `lib/team.py` (git-based registry), `lib/lens.py` (Lens bridge), `hooks/cursor-capture.sh`, `engram publish`/`engram pull`.

**Dropped from Lens:** Separate `publish-skills-cloudflare`/`publish-skills-github` (unified), install modes, GitHub-direct platform detection, locally-installed `skill-registry.json`.

**New in Prism:** Unified CLI, `prism registry create/add/remove/list/default`, `prism registry token create/revoke`, multi-registry read/write, publish tracking with content hashes, `prism promote`, runtime registry fetch with 24h TTL cache.

## Constraints

- **Language**: Python (zero-dependency for lib), shell for hooks and installer — carried from Engram
- **AI models**: Haiku for proposal/review (cheap, fast), Sonnet for validation (thorough) — via `claude` CLI
- **Registry hosting**: Cloudflare Workers + GitHub repos — carried from Lens
- **No runtime dependencies**: Personal learning works offline with no registry configured
- **Installation**: Single `install.sh` or `git clone && ./install.sh` — must work pre-open-source (private repo)
- **Hook contract**: `capture.sh` must never block Claude Code (exit 0 always, background spawns)
- **Safety**: 4 validation gates on all extracted engrams, constitution.md never overwritten

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Copy and modify from Engram + Lens, not build from scratch | Design doc doesn't capture all implementation detail; source code is the ground truth | -- Pending |
| Tool repo only (registry template bundled inside) | Registry template files ship as part of the tool, not a separate project | -- Pending |
| Python + shell, no new language dependencies | Carried from Engram; zero-dependency is a feature | -- Pending |
| Worker-only registry access (no GitHub-direct) | Simplifies auth model, one API surface | -- Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check -- still the right priority?
3. Audit Out of Scope -- reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-14 after initialization*
