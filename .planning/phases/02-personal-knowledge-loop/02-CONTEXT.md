# Phase 2: Personal Knowledge Loop - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Prism extracts validated knowledge from observations, user can manage engrams manually, knowledge flows back into Claude Code sessions through push and pull channels, and knowledge stays fresh through confidence decay and reinforcement. Delivers: extraction pipeline (Haiku proposes, Sonnet validates through 4 gates), session reviewer, `prism learn/correct/forget/maintain/status/extract/review/analyze-sessions/procedures`, `.claude/prism.md` sync, MCP server with 4 tools. Bridge/promotion and slash commands are Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Extraction Pipeline
- **D-01:** Refine agent prompts (extractor.md, validator.md, reviewer.md) for Prism context -- update terminology, add references to Prism ecosystem (registry promotion path, skill format), update naming from Engram to Prism throughout. Not just find-replace; improve wording where Prism context differs.
- **D-02:** Keep Engram's 4 validation gates (constitution, evidence, contradiction, safety) exactly as-is. Don't change the validation logic -- it's proven. Only rename references.
- **D-03:** Test the pipeline with manual smoke tests using real `claude` CLI calls. Create a sample observations.jsonl, run `prism extract`, verify engrams produced. No mocked subprocess tests needed for this phase.

### Engram Lifecycle
- **D-04:** Time-proportional decay -- calculate actual elapsed time since last reinforcement. If 2.5 weeks passed, decay by 0.05 (2.5 x 0.02). Decay happens when `prism maintain` runs.
- **D-05:** Reinforcement triggers on BOTH observation pattern match (extraction pipeline sees recurring pattern) AND MCP query match (engram returned via prism_search/prism_relevant). Either event bumps confidence.
- **D-06:** Global and project-scoped engrams merge into one list for search and display, each tagged [global] or [project]. User sees everything relevant in one view.

### Context Injection
- **D-07:** `.claude/prism.md` auto-regen is synchronous -- blocks until file is written. File is small (<100 lines), regen is fast (<100ms). Predictable behavior, no race conditions.
- **D-08:** Keep Engram's existing priority ordering for the 100-line trim policy: corrections > pinned > top preferences > session-validated. Don't change the selection logic.
- **D-09:** MCP `prism_search` always merges global + project engrams, tagged with scope. Consistent with D-06.

### Session Review
- **D-10:** Hardcoded transcript path (`~/.claude/projects/`), fail gracefully. If path doesn't exist or format changes, log warning and skip review. Don't over-engineer.
- **D-11:** `prism analyze-sessions` supports `--since DATE` and `--last N` flags for controlling scope. Default is all available sessions. Dedup via analyzed-sessions.json (EXT-12) so re-running is safe.
- **D-12:** Review triggered only by the existing hook mechanism (every 5 observations). No cascading review after extraction completes. Keep it simple.

### Claude's Discretion
- Exact confidence bump amount on reinforcement (observation match vs MCP query -- may want different weights)
- Agent prompt refinement specifics beyond rename -- how much to rewrite vs. polish
- Error message formatting for validation gate failures in extraction log
- `prism procedures` display format and sorting

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Engram source (primary copy source for extraction/review/lifecycle)
- `/Users/gaurav/codes/engram/lib/extract.py` -- Original extraction pipeline with Haiku/Sonnet phases
- `/Users/gaurav/codes/engram/lib/review.py` -- Original session reviewer
- `/Users/gaurav/codes/engram/lib/sessions.py` -- Original session analysis / bootstrap
- `/Users/gaurav/codes/engram/lib/index.py` -- Original index management with lifecycle
- `/Users/gaurav/codes/engram/lib/sync.py` -- Original context push layer
- `/Users/gaurav/codes/engram/lib/mcp_server.py` -- Original MCP server with 4 tools
- `/Users/gaurav/codes/engram/agents/extractor.md` -- Original extractor prompt (to refine for Prism)
- `/Users/gaurav/codes/engram/agents/reviewer.md` -- Original reviewer prompt (to refine for Prism)
- `/Users/gaurav/codes/engram/agents/validator.md` -- Original validator prompt (to refine for Prism)

### Prism codebase (already copied in Phase 1)
- `lib/extract.py` -- Current Prism extraction pipeline (copied, needs verification)
- `lib/review.py` -- Current Prism session reviewer (copied, needs verification)
- `lib/sessions.py` -- Current Prism session analysis (copied, needs --since/--last flags)
- `lib/index.py` -- Current Prism index with atomic writes (copied, needs lifecycle verification)
- `lib/commands.py` -- Current Prism CLI commands (copied, needs end-to-end testing)
- `lib/sync.py` -- Current Prism context sync (copied, needs verification)
- `lib/mcp_server.py` -- Current Prism MCP server (copied, needs scope merge verification)
- `agents/extractor.md` -- Current Prism extractor prompt (needs Prism-context refinement per D-01)
- `agents/reviewer.md` -- Current Prism reviewer prompt (needs Prism-context refinement per D-01)
- `agents/validator.md` -- Current Prism validator prompt (needs Prism-context refinement per D-01)

### Design and requirements
- `unified-design.md` -- Complete design document with architecture and all command specs
- `.planning/PROJECT.md` -- Key decisions and constraints
- `.planning/REQUIREMENTS.md` -- EXT-01 through EXT-12, ENG-01 through ENG-12, CTX-01 through CTX-09

### Phase 1 context (prior decisions)
- `.planning/phases/01-foundation-observation/01-CONTEXT.md` -- D-01 through D-13 from Phase 1

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lib/extract.py`: Full Haiku->Sonnet pipeline already copied -- `run_extraction()` is the entry point
- `lib/review.py`: Session reviewer with lock management already copied -- `run_review()` entry point
- `lib/sessions.py`: Session analysis with transcript parsing already copied -- needs --since/--last flag addition
- `lib/index.py`: Atomic index with flock/rename/backup already implemented per Phase 1 D-decisions
- `lib/commands.py`: All CLI commands (learn, correct, forget, maintain, status, extract, review, procedures) already stubbed/copied
- `lib/sync.py`: Push layer with priority ordering already copied -- `sync_claude_code()` entry point
- `lib/mcp_server.py`: MCP server with 4 tools (search, get, relevant, record) already copied
- `lib/scrub.py`: Secret scrubbing patterns already implemented and tested
- `lib/config.py`: Config management with project/global paths already implemented
- `agents/extractor.md`, `reviewer.md`, `validator.md`: Agent prompts copied, need Prism refinement

### Established Patterns
- Python stdlib only (json, argparse, pathlib, re, subprocess, datetime, fcntl) -- zero-dependency
- `subprocess.run(["claude", "--print", ...])` for all AI model calls
- JSONL for observations (append-only), JSON for index/config (atomic read/write)
- Markdown with YAML frontmatter for engrams (custom parser, no PyYAML)
- Lock files with stale detection for concurrent operation safety (extraction lock, review lock)

### Integration Points
- Hook trigger: `capture.sh` spawns extraction at 15 obs, review at 5 obs (already wired in Phase 1)
- MCP server: registered in `.claude/settings.local.json` by `prism init` (Phase 1)
- Context push: `.claude/prism.md` regenerated by sync, read by Claude Code at session start
- CLI wrapper: `~/.local/bin/prism` symlink routes to `lib/cli.py` (Phase 1)

</code_context>

<specifics>
## Specific Ideas

- Agent prompts should be genuinely refined for Prism context, not just find-replace -- reference the promotion-to-skill path, updated ecosystem, Prism naming throughout
- MCP scope alternatives (project-only default, smart relevance filter) noted for future exploration after v1 ships
- `prism analyze-sessions` should support `--since 2025-01-01` and `--last 50` for flexible bootstrapping

</specifics>

<deferred>
## Deferred Ideas

- **MCP scope strategies** -- Alternative approaches for prism_search scope (project-only default with --global param, smart merge with relevance filter). Currently using "always merge both" (D-09). Revisit after v1 usage data shows whether noise is a problem.
- **Post-extraction review trigger** -- Running a session review automatically after extraction completes. Decided against for simplicity (D-12) but could capture patterns from the extraction interaction itself.

</deferred>

---

*Phase: 02-personal-knowledge-loop*
*Context gathered: 2026-04-14*
