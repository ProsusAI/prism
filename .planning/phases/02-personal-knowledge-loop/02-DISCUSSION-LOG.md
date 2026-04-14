# Phase 2: Personal Knowledge Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 02-personal-knowledge-loop
**Areas discussed:** Extraction pipeline behavior, Engram lifecycle tuning, Context injection behavior, Session review mechanics

---

## Extraction Pipeline Behavior

### Agent Prompt Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Rename references only | Replace 'engram' with 'prism' in prompts but keep all instructions identical | |
| Refine for Prism context | Update prompts with Prism-specific terminology, add ecosystem references | ✓ |
| You decide | Claude uses judgment | |

**User's choice:** Refine for Prism context
**Notes:** User wants genuine refinement, not just find-replace.

### Validation Gate Strictness

| Option | Description | Selected |
|--------|-------------|----------|
| Keep Engram's behavior exactly | Don't touch validation logic, just rename references | ✓ |
| Tighten safety gate | Add stricter checks for file paths, secrets-adjacent patterns, PII | |
| Add 5th 'relevance' gate | New gate checking if pattern is actually useful | |

**User's choice:** Keep Engram's behavior exactly
**Notes:** Proven gates, don't risk regression.

### Testing Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Manual smoke test with real claude CLI | Create sample observations, run extract, verify engrams | ✓ |
| Mock subprocess calls in unit tests | Fast, CI-friendly, doesn't validate AI quality | |
| Both mocked + real | Unit tests for CI, manual smoke for real validation | |

**User's choice:** Manual smoke test with real claude CLI
**Notes:** None.

---

## Engram Lifecycle Tuning

### Decay Calculation

| Option | Description | Selected |
|--------|-------------|----------|
| Time-proportional decay | Calculate actual elapsed time, decay proportionally | ✓ |
| Per-run batch decay | Fixed -0.02 per maintain run regardless of time | |
| Keep Engram's implementation | Don't change the math | |

**User's choice:** Time-proportional decay
**Notes:** None.

### Reinforcement Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Observation pattern match | Extraction pipeline sees recurring pattern | |
| MCP query match | Engram returned via search/relevant | |
| Both observation + MCP query | Either event reinforces | ✓ |

**User's choice:** Both observation + MCP query
**Notes:** Broadest reinforcement -- knowledge that recurs or is actively used stays alive.

### Global vs Project Scope Interaction

| Option | Description | Selected |
|--------|-------------|----------|
| Merge both, tag source | Single list with [global]/[project] tags | ✓ |
| Project-first, global fallback | Project engrams first, global only for non-overlapping | |
| Separate views | Default project, --global for global, MCP always merges | |

**User's choice:** Merge both, tag source
**Notes:** None.

---

## Context Injection Behavior

### Sync Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Synchronous | Blocks until .claude/prism.md written | ✓ |
| Async background | Queue regen, return immediately | |
| Keep Engram's approach | Don't change sync behavior | |

**User's choice:** Synchronous
**Notes:** None.

### Trim Policy

| Option | Description | Selected |
|--------|-------------|----------|
| Lowest confidence first | Sort by confidence, drop lowest when full | |
| Oldest first | Keep newest in push layer | |
| Keep Engram's priority ordering | corrections > pinned > top preferences > session-validated | ✓ |

**User's choice:** Keep Engram's priority ordering
**Notes:** None.

### MCP Search Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Always merge global + project | Every search returns both scopes, tagged | ✓ |
| Project-only default, --global param | Add optional include_global parameter | |
| Smart merge with relevance filter | Include global only above relevance threshold | |

**User's choice:** Always merge global + project
**Notes:** User wants option 1 but asked to note the other options "somewhere in the doc for later to explore."

---

## Session Review Mechanics

### Transcript Path Resilience

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcoded path, fail gracefully | Use ~/.claude/projects/, warn and skip if missing | ✓ |
| Configurable path | Add session_transcript_dir config option | |
| Auto-discover from Claude Code config | Read Claude Code's own config for path | |

**User's choice:** Hardcoded path, fail gracefully
**Notes:** None.

### analyze-sessions History Scope

| Option | Description | Selected |
|--------|-------------|----------|
| All available sessions | Scan everything, dedup via analyzed-sessions.json | |
| Last 30 days | Recent only, --all to override | |
| Configurable with --since flag | --since DATE and --last N flags | ✓ |

**User's choice:** Configurable with --since/--last flags
**Notes:** Default is all available sessions.

### Auto-Review After Extraction

| Option | Description | Selected |
|--------|-------------|----------|
| Keep existing trigger only | Review runs every 5 observations via hook, no cascading | ✓ |
| Also after extraction | Trigger review after extraction completes | |
| You decide | Claude uses judgment | |

**User's choice:** Keep existing trigger only
**Notes:** None.

---

## Claude's Discretion

- Exact confidence bump amount on reinforcement
- Agent prompt refinement specifics beyond rename
- Error message formatting for validation gate failures
- `prism procedures` display format and sorting

## Deferred Ideas

- MCP scope strategies (project-only default, smart relevance filter) -- revisit after v1 usage data
- Post-extraction review trigger -- decided against but could catch extraction-interaction patterns
