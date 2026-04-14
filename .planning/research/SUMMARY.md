# Project Research Summary

**Project:** Prism
**Domain:** CLI-driven knowledge layer for AI coding assistants (Claude Code integration)
**Researched:** 2026-04-14
**Confidence:** HIGH

## Executive Summary

Prism is a knowledge layer for Claude Code that merges two existing, production-quality codebases: Engram (personal learning through hook-based observation and AI extraction) and Lens (team skill registry via Cloudflare Workers and GitHub). The research confirms that this domain -- persistent memory for AI coding assistants -- is actively contested by Claude Code's native auto-memory, Windsurf Memories, Copilot Memory, and Cursor rules. Every competitor offers basic cross-session persistence, but none offer validated extraction (multi-gate quality pipelines), confidence-based knowledge decay, or team knowledge federation across organizational boundaries. These three capabilities are Prism's strongest differentiators and should drive roadmap priorities.

The recommended approach is to build the personal learning loop first (hooks, extraction, engrams, push context injection), then layer on enrichment features (MCP pull injection, session review, decay lifecycle), and finally add the team layer (skill promotion, slash commands, registry). This ordering follows strict dependency chains identified in the architecture research: context injection requires engrams, engrams require extraction, extraction requires observations. The team layer shares only the foundation with the personal layer and can be developed largely in parallel once the foundation is solid. The entire personal tier runs offline with zero dependencies beyond Python 3.12+ and the Claude CLI -- this zero-config experience is a core adoption advantage.

The primary risks are: (1) hook performance degrading Claude Code responsiveness (the existing Engram hook makes three synchronous Python calls per event -- this must be collapsed to one), (2) extraction quality drift where the AI extractor hallucinates preferences from behavior rather than explicit user statements, and (3) index.json corruption from concurrent writes by the hook, extraction pipeline, MCP server, and CLI. All three are addressable with known techniques identified in the pitfalls research, but all three must be fixed in the first phase -- they are not deferrable.

## Key Findings

### Recommended Stack

The stack is Python 3.12+ (stdlib only, zero runtime dependencies) for the library, CLI, MCP server, and extraction pipeline. Bash for hooks and installer. TypeScript for the Cloudflare Worker (registry API). The `claude` CLI is the sole interface for AI model calls (Haiku for extraction/review, Sonnet for validation). No pip installs, no virtualenvs, no package managers at runtime. This zero-dependency constraint is carried from Engram and is a core feature -- users run `install.sh` and everything works.

**Core technologies:**
- **Python 3.12+ (stdlib only):** Library, CLI, MCP server, extraction -- zero-dependency constraint is non-negotiable
- **Bash 5.x (POSIX-ish):** Hook capture, installer -- must exit 0 always, background spawns for heavy work
- **Claude CLI (`claude --print`):** All AI inference -- Haiku proposes, Sonnet validates, no direct API key management needed
- **TypeScript + Wrangler 4.x:** Cloudflare Worker for registry API -- zero cold start, global edge, already built in Lens
- **MCP protocol 2025-03-26 over stdio:** Knowledge pull channel -- 4 tools, no HTTP, Python stdout reserved for JSON-RPC only

**Critical version notes:** Python 3.11 likely works but is untested. macOS ships Bash 3.2 -- avoid Bash 4+ features (associative arrays, `${var,,}`). MCP protocol 2025-11-25 adds complexity Prism does not need.

### Expected Features

**Must have (table stakes -- users expect these from any memory tool):**
- Cross-session persistence (engrams + `.claude/prism.md`)
- Automatic learning from interactions (hook-based observation + extraction)
- Manual knowledge management (`prism learn/correct/forget`)
- Project-scoped and global-scoped context
- Context injection into sessions (push via generated markdown)
- Secret scrubbing on all captured observations
- Non-blocking capture (hook must never slow down Claude Code)

**Should have (differentiators -- Prism's competitive edge):**
- Two-phase extraction with 4-gate validation (no competitor validates extracted knowledge)
- Confidence lifecycle with Ebbinghaus-inspired decay (no competitor has this)
- Team knowledge registry with multi-registry federation (blue ocean -- nobody else does this)
- Engram-to-skill promotion bridge (`prism promote`)
- Session transcript analysis for retroactive knowledge extraction
- MCP server for mid-session pull-based knowledge access

**Defer to v2+:**
- 12 slash commands from Lens (complex, needs personal tier stable first)
- Registry template + `prism registry create` (needs skill production working first)
- Multi-registry management, publish tracking, cross-registry queries

### Architecture Approach

The system is a six-layer pipeline: Interface (CLI, hooks, MCP, slash commands) feeds a Processing layer (extraction, session review, sync engine), which connects through a Bridge layer (`prism promote`) to a Team layer (analysis, curation, registry). Data lives in a flat file store (`~/.prism/`) with a single `index.json` catalog and markdown engram files with custom frontmatter. The personal and team layers share only the foundation (config, index, scrub, project detection) and can be developed in parallel. All cross-component communication uses files or stdio -- no databases, no network for the personal tier.

**Major components:**
1. **Hook (`capture.sh`)** -- Non-blocking observer of Claude Code tool calls, writes JSONL observations
2. **Extraction Pipeline** -- Two-phase LLM pipeline (Haiku proposes, Sonnet validates through 4 gates)
3. **Sync Engine** -- Generates priority-ordered `.claude/prism.md` for push context injection
4. **MCP Server** -- stdio JSON-RPC server exposing 4 tools for mid-session knowledge pull
5. **Promote Bridge** -- Converts high-confidence engrams to skill format for team publishing
6. **Registry Module** -- Multi-registry management, Cloudflare Worker proxy to GitHub repos

### Critical Pitfalls

1. **Shell injection in capture hook** -- Current Engram code interpolates untrusted shell variables into Python string literals. Rewrite to pipe all data through stdin to a single Python process. Fix in Phase 1; this is the critical path for all observation capture.

2. **Hook blocking Claude Code** -- Three synchronous `python3 -c` calls per hook event adds 300-450ms latency. Collapse to a single Python invocation, cache the project ID, use async mode for PostToolUse. Fix in Phase 1; a slow hook means immediate uninstall.

3. **Index.json corruption from concurrent writes** -- No locking, no atomic writes, no backup. A crash during save loses the entire index. Use atomic write-rename, add `fcntl.flock()`, keep `.bak` copy, add `prism repair` command. Fix in Phase 1.

4. **Extraction quality drift** -- AI extractor hallucinates preferences from behavior (absence of alternatives is not a preference). Start extracted engrams at low confidence (0.4), add human confirmation state, instruct extractor to only capture explicit statements. Address in Phase 2.

5. **MCP stdout contamination** -- Any `print()` statement corrupts the JSON-RPC stream and disconnects the server. Redirect stdout to stderr at startup, use dedicated fd for protocol output. Fix in Phase 1.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation + Observation Layer
**Rationale:** Everything depends on config, index, project detection, and observation capture. The architecture dependency graph is clear: nothing works without these. This phase also addresses 6 of 10 critical pitfalls (shell injection, hook blocking, JSONL corruption, index corruption, merge naming collisions, MCP stdout contamination, frontmatter parser hardening).
**Delivers:** Working installer, `prism init`, hook-based observation capture with secret scrubbing, core data model (config, index, project detection), atomic index writes with backup, and the CLI skeleton.
**Addresses features:** Installer + `prism init`, hook-based observation, secret scrubbing, project-scoped data isolation, constitution safety, non-blocking capture.
**Avoids pitfalls:** Shell injection (single Python invocation), hook blocking (async mode + cached project ID), JSONL corruption (atomic appends), index corruption (atomic writes + backup), merge naming (exhaustive rename verification), MCP stdout (redirect at startup), frontmatter parser (strict subset definition + tests).

### Phase 2: Knowledge Processing (Extraction + Manual Commands)
**Rationale:** With observations flowing in, the extraction pipeline is the core value proposition. This is what makes Prism's knowledge trustworthy vs. competitors' single-pass memory writes. Manual commands (`learn/correct/forget`) give users immediate control. The extraction pipeline is HIGH complexity and quality-critical -- it deserves its own phase.
**Delivers:** Two-phase extraction (Haiku + Sonnet), agent prompts, auto-extraction triggers, manual commands (`learn`, `correct`, `forget`, `maintain`), `prism status`.
**Addresses features:** Two-phase extraction with 4-gate validation, engram storage with confidence scoring, manual management, status visibility.
**Avoids pitfalls:** Extraction quality drift (low initial confidence, explicit-only extraction instructions, negative examples in prompts). Validator safety gate for secret re-scrubbing. Remove `Bash` from Sonnet validator's allowed tools.

### Phase 3: Context Injection (Push + Pull)
**Rationale:** This is the value delivery mechanism -- where users actually see Prism working. Push injection (`.claude/prism.md`) makes knowledge visible at session start. Pull injection (MCP server) enables mid-session access. Requires engrams to exist (Phase 2). This is where users go from "it's learning" to "it's helping."
**Delivers:** Sync engine generating `.claude/prism.md` with priority ordering, MCP server with 4 tools (`prism_search`, `prism_get`, `prism_relevant`, `prism_record`), auto-sync after extraction and manual commands.
**Addresses features:** Push context injection, pull context injection via MCP, dual-channel delivery (always-on push + on-demand pull).
**Avoids pitfalls:** System prompt bloat (hard cap at 100 lines, ruthless priority ordering). MCP stdout contamination (already addressed in Phase 1 foundation).

### Phase 4: Knowledge Lifecycle + Enrichment
**Rationale:** With the core learn-and-inject loop working, this phase adds long-term quality: confidence decay prevents stale knowledge accumulation, session review catches knowledge hooks miss, and session analysis enables onboarding from history. These are P2 features that enrich the personal tier.
**Delivers:** Confidence decay (-0.02/week) + reinforcement, `prism maintain` for decay cycles, background session reviewer (Haiku), `prism analyze-sessions` for bootstrapping from history, global vs project scope refinement.
**Addresses features:** Confidence lifecycle with decay, background session reviewer, session transcript analysis, global engrams.
**Avoids pitfalls:** Invisible decay (show decaying engrams in `prism status` with time-until-archive). Cold start problem (analyze-sessions bootstraps from existing history).

### Phase 5: Team Layer (Skills + Registry)
**Rationale:** The team layer is Prism's blue ocean -- no competitor has cross-team knowledge federation. But it depends on the personal tier being stable. This phase builds the bridge (promote) and the destination (registry). Can be partially developed in parallel with Phase 4 since it shares only the foundation.
**Delivers:** `prism promote` (engram to skill conversion), 12 slash commands (carried from Lens), registry template (Worker + CI + schemas), `prism registry create`, single-registry publish flow with delta tracking.
**Addresses features:** Skill format + promotion, analysis slash commands, registry template + deployment, publish tracking with delta detection.
**Avoids pitfalls:** Registry token security (constant-time comparison, hashed storage, per-token revocation). Secret re-scrub on promotion. Synchronous registry operations (cache with 24h TTL).

### Phase 6: Multi-Registry + Polish
**Rationale:** Multi-registry management and cross-registry queries are the final integration layer. Only meaningful once single-registry publishing works. This is the enterprise-value phase.
**Delivers:** `prism registry add/remove/list/default`, multi-registry read merging, cross-registry queries (`/advise-skills`, `/audit-code`), publish tracking per-registry.
**Addresses features:** Multi-registry management, cross-registry queries, full team tier.
**Avoids pitfalls:** Registry query latency (parallel fetches, aggressive caching). Name collisions across registries (source tagging on query results).

### Phase Ordering Rationale

- **Dependency-driven:** Each phase produces something the next phase consumes. Observations feed extraction, extraction produces engrams, engrams feed context injection, stable engrams enable decay lifecycle, high-quality engrams enable promotion to skills.
- **Risk-front-loaded:** The 6 most critical pitfalls (shell injection, hook blocking, JSONL corruption, index corruption, naming collisions, MCP stdout) are all addressed in Phase 1. Extraction quality drift is addressed in Phase 2. By Phase 3, the highest-risk code is hardened.
- **Value-progressive:** Phase 1 captures data. Phase 2 turns data into knowledge. Phase 3 delivers knowledge to the user. Phase 4 keeps knowledge fresh. Phase 5-6 share knowledge across teams. Each phase delivers incrementally more value.
- **Parallel opportunity:** Phases 4 and 5 share only the foundation. Once Phase 3 ships, work on lifecycle enrichment and team layer can proceed in parallel.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Knowledge Processing):** The extraction pipeline is the quality-defining component. Prompt engineering for the extractor and validator agents needs careful iteration. The balance between extraction coverage and false positive rate is an empirical tuning problem.
- **Phase 5 (Team Layer):** The registry template bundles a Cloudflare Worker, GitHub Actions CI, and schema validation. The publish flow (Worker creates branch + commits + PR via GitHub API) has many moving parts. The Lens codebase is the source but modifications are needed (unified publish command, multi-registry support).

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Well-understood patterns -- file I/O, JSON serialization, argparse CLI, shell scripting. The pitfalls are known and solutions are documented.
- **Phase 3 (Context Injection):** MCP stdio protocol is well-documented. Push injection is file generation. Both channels exist in Engram already.
- **Phase 4 (Lifecycle):** Decay math is simple arithmetic. Session review is a prompt engineering task using established patterns from Phase 2.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technologies verified against official docs. Python stdlib, Claude CLI, Cloudflare Workers -- all mature, well-documented. Both source codebases (Engram, Lens) are available for direct examination. |
| Features | HIGH | Comprehensive competitor analysis against Claude Code auto-memory, Windsurf, Copilot, Cursor. Feature landscape well-mapped with clear differentiation. Sources include official docs from all major competitors. |
| Architecture | HIGH | Architecture directly derived from working source code (Engram + Lens). Dependency graph verified against actual import chains. Patterns validated against industry memory architecture surveys (Mem0, agentmemory). |
| Pitfalls | HIGH | Pitfalls identified from source code review, real-world JSONL corruption issues (Claude Code GitHub issues), CVE records, and Cloudflare security docs. Concrete line numbers and code patterns cited. |

**Overall confidence:** HIGH

All four research areas achieved HIGH confidence, grounded in direct source code examination of both codebases, official documentation from Claude Code/Cloudflare/GitHub, and real-world issue reports. The research is unusually strong because the source codebases are available locally -- this is a merge/evolution project, not a greenfield build.

### Gaps to Address

- **Extraction quality tuning:** The extractor and validator prompts need empirical testing with real observation data. Research identifies the risk (quality drift) and mitigation strategies, but the actual prompt text needs iteration during Phase 2 implementation.
- **Decay rate calibration:** The -0.02/week decay rate is carried from Engram but has not been validated with real usage data. May need adjustment after observing actual knowledge lifecycle patterns. Monitor during Phase 4.
- **Bash 3.2 compatibility on macOS:** Research flags that macOS ships Bash 3.2 while the hooks use `set -euo pipefail` and `$(...)` which work on 3.2+. But edge cases with newer Bash features should be tested on stock macOS.
- **Claude CLI availability in background processes:** Background `nohup` spawns may not have `claude` on PATH due to shell profile not being sourced. Need to resolve absolute path at install time and store in config.
- **Multi-registry conflict resolution:** When two registries have skills with the same name, the merge behavior is undefined. Needs design decision during Phase 6 planning.

## Sources

### Primary (HIGH confidence)
- Engram source code (`/Users/gaurav/codes/engram/`) -- all modules directly examined
- Lens source code (`/Users/gaurav/codes/Lens/`) -- Worker, skills, scripts directly examined
- Prism unified design document (`/Users/gaurav/codes/prism/unified-design.md`)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) -- complete hooks API
- [Claude Code MCP Documentation](https://code.claude.com/docs/en/mcp) -- MCP server configuration
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills) -- skill format
- [Claude Code Memory Documentation](https://code.claude.com/docs/en/memory) -- auto-memory, dreaming, CLAUDE.md
- [MCP Specification 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) -- stdio transport spec
- [Cloudflare Workers docs](https://developers.cloudflare.com/workers/) -- Wrangler 4.x, compatibility dates, secrets
- [GitHub Copilot Custom Instructions](https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot)
- [CVE-2025-59536](https://research.checkpoint.com/2026/rce-and-api-token-exfiltration-through-claude-code-project-files-cve-2025-59536/) -- hook security vulnerability
- Claude Code JSONL corruption issues: #20992, #29051, #29198, #29217

### Secondary (MEDIUM confidence)
- [Windsurf Cascade Memories](https://docs.windsurf.com/windsurf/cascade/memories) -- auto-generated memories
- [Cursor Rules Documentation](https://docs.cursor.com/context/rules) -- .mdc rules system
- [GitHub Copilot Memory Changelog](https://github.blog/changelog/2026-03-04-copilot-memory-now-on-by-default-for-pro-and-pro-users-in-public-preview/)
- [Augment Code Context Engine](https://www.augmentcode.com/context-engine)
- [Mem0 Architecture](https://mem0.ai/blog/ai-memory-layer-guide) -- two-phase extraction pattern
- [The Agent Memory Race of 2026](https://ossinsight.io/blog/agent-memory-race-2026) -- ecosystem survey
- [Martin Fowler - Encoding Team Standards](https://martinfowler.com/articles/reduce-friction-ai/encoding-team-standards.html)
- [agentmemory](https://github.com/rohitg00/agentmemory) -- Ebbinghaus decay for AI agents
- [Fazm Memory Triage](https://fazm.ai/blog/ai-agent-memory-triage-retention-decay)

### Tertiary (LOW confidence)
- None -- all sources were at least MEDIUM confidence

---
*Research completed: 2026-04-14*
*Ready for roadmap: yes*
