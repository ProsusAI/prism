# Phase 2: Personal Knowledge Loop - Research

**Researched:** 2026-04-14
**Domain:** Python extraction pipeline, MCP server, engram lifecycle, context sync
**Confidence:** HIGH

## Summary

Phase 2 builds the core intelligence loop: observations flow in, knowledge (engrams) gets extracted through a two-phase AI pipeline (Haiku proposes, Sonnet validates through 4 gates), users can manually manage knowledge, and that knowledge flows back into Claude Code sessions through both push (.claude/prism.md) and pull (MCP server) channels. Knowledge stays fresh through confidence decay and reinforcement.

The good news: nearly all the code is already copied and adapted from Engram in Phase 1. The Prism lib/ directory contains working versions of extract.py, review.py, sessions.py, index.py, sync.py, mcp_server.py, commands.py, and cli.py. The primary work is: (1) verify all these modules work end-to-end with Prism paths and naming, (2) add missing features (--since/--last flags for analyze-sessions, auto-sync after learn/correct/forget/extract/maintain), (3) refine agent prompts for Prism context, and (4) ensure the MCP server properly merges global+project scopes per D-06/D-09.

**Primary recommendation:** Treat this phase as "verify, wire up, and polish" rather than "build from scratch." The code exists; the work is making it function as a cohesive system with auto-sync, proper scoping, and refined AI prompts.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Refine agent prompts (extractor.md, validator.md, reviewer.md) for Prism context -- update terminology, add references to Prism ecosystem (registry promotion path, skill format), update naming from Engram to Prism throughout. Not just find-replace; improve wording where Prism context differs.
- **D-02:** Keep Engram's 4 validation gates (constitution, evidence, contradiction, safety) exactly as-is. Don't change the validation logic -- it's proven. Only rename references.
- **D-03:** Test the pipeline with manual smoke tests using real `claude` CLI calls. Create a sample observations.jsonl, run `prism extract`, verify engrams produced. No mocked subprocess tests needed for this phase.
- **D-04:** Time-proportional decay -- calculate actual elapsed time since last reinforcement. If 2.5 weeks passed, decay by 0.05 (2.5 x 0.02). Decay happens when `prism maintain` runs.
- **D-05:** Reinforcement triggers on BOTH observation pattern match (extraction pipeline sees recurring pattern) AND MCP query match (engram returned via prism_search/prism_relevant). Either event bumps confidence.
- **D-06:** Global and project-scoped engrams merge into one list for search and display, each tagged [global] or [project]. User sees everything relevant in one view.
- **D-07:** `.claude/prism.md` auto-regen is synchronous -- blocks until file is written. File is small (<100 lines), regen is fast (<100ms). Predictable behavior, no race conditions.
- **D-08:** Keep Engram's existing priority ordering for the 100-line trim policy: corrections > pinned > top preferences > session-validated. Don't change the selection logic.
- **D-09:** MCP `prism_search` always merges global + project engrams, tagged with scope. Consistent with D-06.
- **D-10:** Hardcoded transcript path (`~/.claude/projects/`), fail gracefully. If path doesn't exist or format changes, log warning and skip review. Don't over-engineer.
- **D-11:** `prism analyze-sessions` supports `--since DATE` and `--last N` flags for controlling scope. Default is all available sessions. Dedup via analyzed-sessions.json (EXT-12) so re-running is safe.
- **D-12:** Review triggered only by the existing hook mechanism (every 5 observations). No cascading review after extraction completes. Keep it simple.

### Claude's Discretion
- Exact confidence bump amount on reinforcement (observation match vs MCP query -- may want different weights)
- Agent prompt refinement specifics beyond rename -- how much to rewrite vs. polish
- Error message formatting for validation gate failures in extraction log
- `prism procedures` display format and sorting

### Deferred Ideas (OUT OF SCOPE)
- **MCP scope strategies** -- Alternative approaches for prism_search scope (project-only default with --global param, smart merge with relevance filter). Currently using "always merge both" (D-09). Revisit after v1 usage data shows whether noise is a problem.
- **Post-extraction review trigger** -- Running a session review automatically after extraction completes. Decided against for simplicity (D-12) but could capture patterns from the extraction interaction itself.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXT-01 | Two-phase extraction: Haiku proposes, writes to candidates/ | extract.py already implements _phase1_extract(); verify Prism paths |
| EXT-02 | Sonnet validates through 4 gates: constitution, evidence, contradiction, safety | extract.py already implements _phase2_validate(); validator.md has all 4 gates |
| EXT-03 | Approved move to engrams/, rejected deleted, modified adjusted then moved | extract.py _apply_validation_results(); verify file moves work with Prism dirs |
| EXT-04 | Typed engrams: preference, correction, procedure, domain_fact, tool_pattern, error_recipe | extractor.md already defines all 6 types; verify frontmatter schema |
| EXT-05 | Post-extraction: archive observations, regenerate .claude/prism.md | _rotate_observations() exists; need to add sync_claude_code() call post-extraction |
| EXT-06 | `prism extract [--project]` triggers manually | cli.py already routes; verify end-to-end |
| EXT-07 | Constitution loaded during validation, never overwritten | templates/constitution.md exists; install.sh preserves; validator prompt references it |
| EXT-08 | Background session reviewer scans transcripts | review.py run_review() already implemented |
| EXT-09 | Reviewer appends findings as observations for next extraction | review.py _write_observations() appends to observations.jsonl |
| EXT-10 | `prism review --session <id>` triggers manually | cli.py already routes to run_review() |
| EXT-11 | `prism analyze-sessions [--all]` bootstraps from past sessions | sessions.py exists; need to add --since/--last flags per D-11 |
| EXT-12 | Validation decisions logged to validation-log.jsonl | extract.py _log_validation() already writes to this file |
| ENG-01 | Engrams as markdown with YAML frontmatter | Already the format; _parse_frontmatter() handles it |
| ENG-02 | Master index with CRUD | index.py has add_entry/remove_entry/get_entry/list_entries with atomic writes |
| ENG-03 | `prism learn` creates at 0.9, auto-syncs | commands.py cmd_learn() exists; needs auto-sync call added |
| ENG-04 | `prism correct` supersedes, auto-syncs | commands.py cmd_correct() exists; needs auto-sync call added |
| ENG-05 | `prism forget` archives (recoverable), auto-syncs | commands.py cmd_forget() exists; needs auto-sync call added |
| ENG-06 | `prism status` shows engrams, stats, health | commands.py cmd_status() exists; verify scope merge per D-06 |
| ENG-07 | Confidence decay -0.02/week, bump on reoccurrence | cmd_maintain() has decay; reinforcement needs to be wired in extract + MCP |
| ENG-08 | Archive at 0.2 threshold | cmd_maintain() already archives below threshold |
| ENG-09 | `prism maintain` runs lifecycle | cmd_maintain() exists; verify time-proportional decay per D-04 |
| ENG-10 | `prism procedures` lists with stats | commands.py cmd_procedures() exists |
| ENG-11 | Global in ~/.prism/global/engrams/, project in projects/<hash>/engrams/ | config.py paths already set up |
| ENG-12 | analyzed-sessions.json tracks processed sessions | sessions.py TRACKER_PATH already defined and used |
| CTX-01 | Push layer with priority ordering | sync.py _select_prompt_entries() has priority ordering per D-08 |
| CTX-02 | Max context lines (default 100, configurable) | sync.py reads max_context_lines from config |
| CTX-03 | MCP nudge footer | sync.py already generates footer with MCP tool instructions |
| CTX-04 | Auto-regen after learn/correct/forget/extract/maintain | Needs to be wired -- each command must call sync_claude_code() |
| CTX-05 | prism_search via MCP | mcp_server.py _search() implemented |
| CTX-06 | prism_get via MCP | mcp_server.py _get_entry_content() implemented |
| CTX-07 | prism_relevant via MCP | mcp_server.py _relevant() implemented |
| CTX-08 | prism_record via MCP | mcp_server.py _record() implemented |
| CTX-09 | MCP server via stdio JSON-RPC | mcp_server.py main() loop implemented |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | 3.12+ | All runtime code: json, argparse, pathlib, re, subprocess, datetime, fcntl, os, shutil | Zero-dependency constraint. Everything from stdlib. [VERIFIED: CLAUDE.md constraint] |
| Claude CLI | latest (2.1.107 on system) | AI model calls for extraction (Haiku) and validation (Sonnet) | Sole interface for AI model calls. subprocess.run(["claude", "--print", ...]) [VERIFIED: system check] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| fcntl | stdlib | File locking for atomic index writes | Already used in index.py save_index() [VERIFIED: codebase] |
| hashlib | stdlib | Project ID from git remote URL | Already used in project.py detect_project_id() [VERIFIED: codebase] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom YAML frontmatter parser | PyYAML | Never -- zero-dependency constraint. Custom parser handles the simple key:value frontmatter Prism uses. [VERIFIED: CLAUDE.md] |
| Hand-rolled JSON-RPC on stdio | mcp Python SDK | Not now -- SDK adds a dependency. Hand-rolled handler is ~100 lines, covers 4 methods. [VERIFIED: CLAUDE.md] |
| Jaccard token search | Vector/embedding search | Never -- would require vector DB dependency, breaks zero-dep constraint. Token Jaccard is sufficient for expected scale. [VERIFIED: CLAUDE.md] |

## Architecture Patterns

### Existing Project Structure (Phase 1 output)
```
~/.prism/
  lib/              # Python library files (flat, no subdirectories)
  hooks/            # capture.sh (shell hook for Claude Code)
  agents/           # extractor.md, validator.md, reviewer.md (AI prompts)
  templates/        # constitution.md
  skills/           # Slash commands (Phase 3)
  global/
    engrams/        # Global-scope engram markdown files
  projects/
    <hash>/
      engrams/      # Project-scope engram markdown files
      candidates/   # Staging area for extraction pipeline
      observations.jsonl
      observations.archive/
  archive/          # Archived (decayed/forgotten) engrams
  index.json        # Master index of all engrams
  config.json       # User configuration
  constitution.md   # Immutable safety principles
  validation-log.jsonl  # Audit trail of validation decisions
  analyzed-sessions.json  # Dedup tracker for session analysis
```

### Pattern 1: Two-Phase AI Pipeline
**What:** Haiku (cheap, fast) proposes candidates; Sonnet (expensive, thorough) validates through 4 gates
**When to use:** All extraction operations -- both auto-triggered and manual
**How it works:**
```python
# Source: /Users/gaurav/codes/prism/lib/extract.py
def run_extraction(project_id):
    # Phase 1: Haiku reads observations, writes candidate .md files to candidates/
    n = _phase1_extract(project_id)
    # Phase 2: Sonnet reads candidates + constitution + index, validates each
    results = _phase2_validate(project_id)
    # Apply: approved -> engrams/, rejected -> deleted, modified -> adjusted then moved
    _apply_validation_results(project_id, results)
    # Rotate observations to archive
    _rotate_observations(project_id)
```
[VERIFIED: codebase extract.py]

### Pattern 2: Auto-Sync After Knowledge Changes
**What:** Every command that modifies engrams must call sync_claude_code() synchronously before returning
**When to use:** learn, correct, forget, extract, maintain -- per CTX-04
**Implementation needed:** Currently learn/correct/forget print "Run 'prism sync' to update IDE context files" -- this needs to be replaced with an actual sync_claude_code() call.
```python
# Pattern to add at end of cmd_learn, cmd_correct, cmd_forget, cmd_maintain:
from .sync import sync_claude_code
sync_claude_code(project_id)
```
[VERIFIED: codebase commands.py -- currently missing, needs addition]

### Pattern 3: Reinforcement on Reoccurrence
**What:** When an engram is returned in a search result or a matching pattern appears in new observations, bump its confidence and update last_observed
**When to use:** In _search() (MCP), _relevant() (MCP), and during extraction when validator notes overlap with existing engrams
**Implementation needed:** 
- MCP: After returning search/relevant results, call update_last_observed() for each returned engram
- Extraction: When validator marks a candidate as reinforcing an existing engram via "deprecates" that is actually a match, bump the existing engram's confidence
```python
# In MCP _search() and _relevant(), after filtering:
from .index import update_last_observed, update_confidence
for entry in results:
    update_last_observed(entry["id"])
    # Optionally bump confidence slightly
```
[ASSUMED -- D-05 requires this; exact boost amount is Claude's discretion]

### Pattern 4: Time-Proportional Decay
**What:** Decay is not a fixed weekly job but calculates actual elapsed time
**When to use:** In cmd_maintain() -- per D-04
**Already implemented:** cmd_maintain() in commands.py already does this correctly:
```python
weeks_since = (today - last_date).days / 7.0
new_conf = max(0.0, old_conf - (decay_rate * weeks_since))
```
[VERIFIED: codebase commands.py line 423-427]

### Anti-Patterns to Avoid
- **Blocking hooks for extraction:** Never. Extraction runs in background (subprocess.Popen with start_new_session). capture.sh always exits 0. [VERIFIED: trigger.py, CLAUDE.md]
- **Printing to stdout in MCP server:** Any stray print() to stdout corrupts the JSON-RPC connection. All logging goes to stderr. [VERIFIED: mcp_server.py, CLAUDE.md]
- **Concurrent index writes without locking:** save_index() uses fcntl.flock() + temp file + os.rename() for atomic writes. Never bypass this. [VERIFIED: index.py]
- **PyYAML or any external dependency:** All imports must be stdlib. [VERIFIED: CLAUDE.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON-RPC protocol | Custom protocol handler | The existing ~100-line handler in mcp_server.py | Already covers initialize, tools/list, tools/call, ping -- the 4 methods Prism needs [VERIFIED: codebase] |
| File locking | OS-specific lock mechanisms | fcntl.flock() as implemented in index.py | Cross-platform on macOS/Linux, handles concurrent writes from hooks + CLI [VERIFIED: codebase] |
| Secret scrubbing | Custom regex per command | scrub.py with BASELINE_SCRUB_PATTERNS | Centralized scrubbing patterns, imported by capture and review [VERIFIED: codebase] |
| YAML frontmatter parsing | yaml library import | Custom split-on-`---` parser in extract.py | Handles the simple key:value frontmatter without adding dependency [VERIFIED: codebase] |
| AI model calls | Anthropic SDK | subprocess.run(["claude", "--print", ...]) | Claude CLI handles auth, model routing, tool permissions [VERIFIED: CLAUDE.md] |

**Key insight:** Everything Prism needs for Phase 2 is already built in Phase 1 as copies from Engram. The work is verification, wiring (auto-sync, reinforcement), and refinement (agent prompts).

## Common Pitfalls

### Pitfall 1: Forgetting Auto-Sync After Knowledge Changes
**What goes wrong:** User runs `prism learn "prefer tabs"` but .claude/prism.md doesn't update. Next Claude Code session doesn't see the new preference.
**Why it happens:** Current code in cmd_learn, cmd_correct, cmd_forget prints "Run 'prism sync' to update IDE context files" instead of actually calling it.
**How to avoid:** Add sync_claude_code(project_id) call at the end of every command that modifies engrams: learn, correct, forget, maintain, extract. Per D-07, this is synchronous.
**Warning signs:** Any command that modifies index.json but doesn't call sync_claude_code(). [VERIFIED: codebase -- commands.py lines 306, 329, 394 all say "Run 'prism sync'"]

### Pitfall 2: MCP Server stdout Corruption
**What goes wrong:** A debug print() in the MCP server writes to stdout, Claude Code receives invalid JSON-RPC, connection drops.
**Why it happens:** Python's default print() goes to stdout. Easy to add during debugging.
**How to avoid:** All logging via sys.stderr.write(). Never use print() in mcp_server.py. The existing code is correct; just don't regress.
**Warning signs:** "Invalid JSON" errors from Claude Code when using prism_search/prism_get tools. [VERIFIED: codebase mcp_server.py, CLAUDE.md]

### Pitfall 3: Extraction Lock Not Released on Crash
**What goes wrong:** If extraction crashes mid-run, the .extracting lock file remains, blocking all future extractions.
**Why it happens:** OS-level crash or timeout before the finally block runs.
**How to avoid:** Already handled -- stale lock detection (>10 min = stale). extract.py checks lock age and removes stale locks. [VERIFIED: codebase extract.py lines 45-50]

### Pitfall 4: Reinforcement Creating Infinite Index Saves
**What goes wrong:** MCP _search() returns 5 results, each triggers update_last_observed(), which calls save_index() 5 times, each with flock acquisition.
**Why it happens:** Naive implementation calls save once per engram update.
**How to avoid:** Batch reinforcement -- load index once, update all entries in memory, save once:
```python
index = load_index()
for entry in matched_entries:
    for e in index["engrams"]:
        if e["id"] == entry["id"]:
            e["last_observed"] = date.today().isoformat()
save_index(index)
```
[ASSUMED -- performance pattern based on index.py structure]

### Pitfall 5: analyze-sessions Missing --since/--last Flags
**What goes wrong:** User wants to bootstrap from last 50 sessions only, but has to process all 500.
**Why it happens:** Current cli.py has --all, --extract, --dry-run, --list, --project but NOT --since or --last. D-11 requires adding these.
**How to avoid:** Add --since DATE and --last N arguments to the analyze-sessions subparser, and filter in analyze_all_sessions().
**Warning signs:** Missing from cli.py subparser definition. [VERIFIED: codebase cli.py lines 66-76]

### Pitfall 6: Post-Extraction Sync Not Wired
**What goes wrong:** Extraction produces new engrams but .claude/prism.md doesn't update until user manually runs `prism sync`.
**Why it happens:** EXT-05 requires post-extraction sync, but run_extraction() doesn't call sync_claude_code().
**How to avoid:** After _apply_validation_results() in run_extraction(), call sync_claude_code(project_id). Or wire it in the CLI handler after run_extraction() returns.
**Warning signs:** extract.py doesn't import from sync module. [VERIFIED: codebase extract.py -- no sync import]

## Code Examples

### Example 1: Adding Auto-Sync to cmd_learn
```python
# Source: pattern needed for CTX-04 compliance
# In commands.py cmd_learn(), replace the "Run 'prism sync'" print with:

from .sync import sync_claude_code
sync_claude_code(project_id)
print(f"Learned: {entry_id} (confidence: 0.9)")
```
[VERIFIED: codebase pattern, sync.py import works]

### Example 2: Batch Reinforcement in MCP Search
```python
# Source: pattern for D-05 compliance
# In mcp_server.py _search(), after scoring and selecting results:

def _search(query, project_id=None, limit=5):
    # ... existing scoring logic ...
    
    # Reinforce returned engrams (D-05)
    if results:
        _reinforce_batch([r["id"] for r in results])
    
    return results

def _reinforce_batch(entry_ids):
    """Batch-update last_observed for all returned entries."""
    index = load_index()
    today = date.today().isoformat()
    changed = False
    for e in index.get("engrams", []):
        if e["id"] in entry_ids:
            e["last_observed"] = today
            changed = True
    if changed:
        from .index import save_index
        save_index(index)
```
[ASSUMED -- implementation pattern for D-05]

### Example 3: Adding --since/--last to analyze-sessions
```python
# Source: pattern for D-11 compliance
# In cli.py, add to analyze-sessions subparser:

p_sessions.add_argument("--since", help="Only analyze sessions after DATE (YYYY-MM-DD)")
p_sessions.add_argument("--last", type=int, help="Only analyze last N sessions")

# In sessions.py analyze_all_sessions(), add filtering:
if since_date:
    sessions = [s for s in sessions if _session_date(s) >= since_date]
if last_n:
    sessions = sessions[-last_n:]
```
[ASSUMED -- CLI pattern consistent with existing argparse usage]

### Example 4: MCP prism_record with Auto-Sync
```python
# Source: pattern for CTX-04 - MCP record should also trigger sync
# In mcp_server.py _record(), after add_entry():

from .sync import sync_claude_code
sync_claude_code(project_id)
```
[ASSUMED -- needed for CTX-04 completeness, but may add latency to MCP response]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Engram naming throughout | Prism naming (PRISM_HOME, prism CLI, prism MCP tools) | Phase 1 | All imports, paths, env vars already renamed [VERIFIED: codebase] |
| Simple save_index() | Atomic save with fcntl.flock + tmp + rename + bak | Phase 1 | Prevents corruption from concurrent writes [VERIFIED: codebase index.py] |
| Multi-spawn capture hook | Single Python invocation via stdin pipe | Phase 1 | Performance improvement per D-08 [VERIFIED: codebase capture.py] |
| engram_search/get/relevant/record MCP tools | prism_search/get/relevant/record | Phase 1 | Tool names updated [VERIFIED: codebase mcp_server.py] |

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Reinforcement should batch-update index rather than per-entry save | Common Pitfalls, Code Examples | Performance issue -- 5 saves per search vs 1. Low risk, easy to fix. |
| A2 | MCP reinforcement boost should be smaller than observation match boost | Claude's Discretion area | Could over-reinforce frequently-searched engrams. Low risk -- tunable. |
| A3 | --since/--last filtering should happen at the session list level | Code Examples | Could filter at wrong stage. Low risk, straightforward logic. |
| A4 | MCP prism_record should trigger auto-sync | Code Examples | May add latency to MCP response (sync is <100ms per D-07). Low risk. |

**All other claims in this research were verified against the codebase or CLAUDE.md.**

## Open Questions (RESOLVED)

1. **Reinforcement Confidence Boost Amount** (RESOLVED -- Plan 04 uses query_boost=0.02, Claude's discretion)
   - What we know: D-05 says reinforce on both observation match and MCP query match. Claude's discretion area.
   - What's unclear: Exact boost value. Observation match could be +0.05 (strong signal -- pattern recurred). MCP query could be +0.01 (weaker signal -- just accessed, not necessarily reconfirmed).
   - Recommendation: Start with observation_boost=0.05, query_boost=0.02, make configurable in config.json. Easy to tune later.

2. **MCP Record Auto-Sync Latency** (RESOLVED -- Plan 04 does the sync per D-07)
   - What we know: D-07 says sync is synchronous, <100ms. prism_record is called during active MCP session.
   - What's unclear: Whether adding sync to every MCP record call creates noticeable latency for the user.
   - Recommendation: Do the sync -- 100ms is imperceptible. If it becomes a problem, queue it.

3. **Agent Prompt Refinement Depth** (RESOLVED -- Plan 01 specifies detailed refinement per D-01)
   - What we know: D-01 says "not just find-replace; improve wording where Prism context differs." Claude's discretion on specifics.
   - What's unclear: How much to rewrite vs. polish. Current prompts are functional.
   - Recommendation: Add Prism ecosystem references (promotion-to-skill path, registry awareness, scope tagging), update naming, improve examples. Don't restructure the prompt logic.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | All runtime code | PARTIAL | 3.9.6 (system) | Code uses `python3` command. System Python 3.9.6 should work despite CLAUDE.md saying 3.12+. No 3.12+ specific syntax observed in codebase. |
| Claude CLI | Extraction, validation, review | YES | 2.1.107 | None -- required for AI pipeline |
| git | Project ID detection | YES | 2.50.1 | Falls back to "global" project ID |
| bash | capture.sh hook | YES | 3.2.57 | No Bash 4+ features used per Phase 1 D-08 |
| ~/.claude/projects/ | Session review, analyze-sessions | YES | Has data | Graceful skip per D-10 |

**Missing dependencies with no fallback:**
- None that block execution. Python 3.9.6 is older than the 3.12+ target but all code uses stdlib features available since 3.6+. The only 3.12+ feature potentially needed would be `type X = Y` syntax or `match` statements, neither of which appear in the codebase.

**Missing dependencies with fallback:**
- Python 3.12+: System has 3.9.6 but codebase uses only 3.6+ compatible features. The `X | Y` union type hints in function signatures use string annotations (`"dict | None"`) which are forward references, not runtime evaluation -- compatible with 3.9. [VERIFIED: codebase uses quoted type hints]

## Project Constraints (from CLAUDE.md)

These directives from CLAUDE.md constrain all implementation decisions:

1. **Zero-dependency runtime:** Every import must be Python stdlib. No pip install for end users. [VERIFIED: CLAUDE.md]
2. **AI calls via claude CLI only:** `subprocess.run(["claude", "--print", "--model", "haiku/sonnet", "-p", ...])`. Never use Anthropic SDK. [VERIFIED: CLAUDE.md]
3. **Hook contract:** capture.sh exits 0 always. Background spawns for heavy work (extraction, review). [VERIFIED: CLAUDE.md]
4. **MCP protocol 2025-03-26:** Stdio transport, JSON-RPC 2.0, newline-delimited. stdout reserved for protocol; logging to stderr only. [VERIFIED: CLAUDE.md]
5. **Constitution never overwritten:** install.sh copies only if not exists. Validation gate always loads it. [VERIFIED: CLAUDE.md, templates/constitution.md, config.py init_prism_home()]
6. **Flat lib/ structure:** No subdirectories in lib/. All Python files at lib/ level. [VERIFIED: Phase 1 D-02]
7. **Atomic index writes:** fcntl.flock() + tmp file + os.rename() + .bak backup. [VERIFIED: Phase 1 decisions, index.py]
8. **No Bash 4+ features:** macOS ships Bash 3.2. Avoid associative arrays, `${var,,}`. [VERIFIED: CLAUDE.md]

## Gap Analysis: Current Code vs Requirements

This section maps exactly what needs to change to meet each requirement, based on reading both the existing Prism code and the Engram original.

### Already Working (verify only)
- EXT-01, EXT-02, EXT-03, EXT-04: extract.py pipeline complete [VERIFIED: codebase]
- EXT-06: CLI routes to run_extraction() [VERIFIED: cli.py]
- EXT-07: Constitution loaded by validator prompt, install preserves it [VERIFIED: codebase]
- EXT-08, EXT-09: review.py complete [VERIFIED: codebase]
- EXT-10: CLI routes to run_review() [VERIFIED: cli.py]
- EXT-12: validation-log.jsonl written by _log_validation() [VERIFIED: extract.py]
- ENG-01: Markdown+frontmatter format in all engram creation code [VERIFIED: codebase]
- ENG-02: Index CRUD with atomic writes [VERIFIED: index.py]
- ENG-08: Archive below 0.2 in cmd_maintain() [VERIFIED: commands.py]
- ENG-10: cmd_procedures() exists [VERIFIED: commands.py]
- ENG-11: Global/project paths in config.py [VERIFIED: config.py]
- ENG-12: analyzed-sessions.json tracker [VERIFIED: sessions.py]
- CTX-01: Priority ordering in sync.py _select_prompt_entries() [VERIFIED: sync.py]
- CTX-02: max_context_lines config [VERIFIED: sync.py]
- CTX-03: MCP nudge footer [VERIFIED: sync.py]
- CTX-05, CTX-06, CTX-07, CTX-08: MCP tools implemented [VERIFIED: mcp_server.py]
- CTX-09: MCP stdio loop [VERIFIED: mcp_server.py]

### Needs Wiring (code changes required)
- EXT-05: Post-extraction sync -- add sync_claude_code() call after _apply_validation_results()
- EXT-11: Add --since/--last flags to analyze-sessions subparser and session filtering
- ENG-03: cmd_learn needs auto-sync (replace print with sync call)
- ENG-04: cmd_correct needs auto-sync
- ENG-05: cmd_forget needs auto-sync
- ENG-06: cmd_status needs scope merge display ([global]/[project] tags per D-06)
- ENG-07: Reinforcement on reoccurrence -- needs implementation in MCP server and extraction
- ENG-09: cmd_maintain needs auto-sync and verify time-proportional decay matches D-04
- CTX-04: Auto-regen wiring for all five commands (learn, correct, forget, extract, maintain)

### Needs New Code (small additions)
- D-01: Agent prompt refinement (extractor.md, validator.md, reviewer.md) -- content updates
- D-05: Reinforcement mechanism in MCP server (_reinforce_batch helper)
- D-06: Scope tagging in search/display results ([global]/[project] labels)
- D-11: --since/--last argument parsing and session date filtering logic

## Sources

### Primary (HIGH confidence)
- Prism codebase at `/Users/gaurav/codes/prism/lib/` -- all modules read and analyzed
- Engram codebase at `/Users/gaurav/codes/engram/lib/` -- original implementations compared
- Phase 2 CONTEXT.md -- all 12 locked decisions
- CLAUDE.md -- all project constraints and stack decisions
- REQUIREMENTS.md -- all 30 phase requirements (EXT-01 through EXT-12, ENG-01 through ENG-12, CTX-01 through CTX-09)

### Secondary (MEDIUM confidence)
- MCP protocol spec 2025-03-26 -- referenced in CLAUDE.md for stdio transport details
- Claude Code hooks documentation -- referenced in CLAUDE.md for hook contract

### Tertiary (LOW confidence)
- None -- all findings verified against codebase or documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, no choices to make, verified against CLAUDE.md
- Architecture: HIGH -- code already exists from Phase 1, patterns verified in codebase
- Pitfalls: HIGH -- all identified from reading actual code gaps and Phase 1 decisions
- Gap analysis: HIGH -- every requirement mapped to specific file and line

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (stable -- no external dependencies changing)
