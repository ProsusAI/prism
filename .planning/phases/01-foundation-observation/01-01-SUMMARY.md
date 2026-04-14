---
phase: 01-foundation-observation
plan: 01
subsystem: foundation
tags: [python, shell, installer, cli, hooks, mcp, rename]

# Dependency graph
requires:
  - phase: none
    provides: "First plan -- no dependencies"
provides:
  - "13 lib/*.py Python modules (config, cli, commands, index, project, scrub, sync, mcp_server, extract, review, sessions, trigger)"
  - "install.sh installer creating ~/.prism/ tree"
  - "prism CLI entry point wrapper"
  - "hooks/capture.sh thin shell wrapper for observation capture"
  - "Agent prompts (extractor, validator, reviewer)"
  - "Constitution template for validation gates"
affects: [01-02, 01-03, 02-01, 02-02, 02-03]

# Tech tracking
tech-stack:
  added: [python3-stdlib, bash, fcntl]
  patterns: [atomic-writes-with-flock, stdin-pipe-to-python, zero-dependency-python]

key-files:
  created:
    - lib/config.py
    - lib/cli.py
    - lib/commands.py
    - lib/index.py
    - lib/project.py
    - lib/scrub.py
    - lib/sync.py
    - lib/mcp_server.py
    - lib/extract.py
    - lib/review.py
    - lib/sessions.py
    - lib/trigger.py
    - lib/__init__.py
    - install.sh
    - prism
    - hooks/capture.sh
    - agents/extractor.md
    - agents/validator.md
    - agents/reviewer.md
    - templates/constitution.md
  modified: []

key-decisions:
  - "Preserved 'engrams' as data-format directory name and JSON key -- renaming would break data model compatibility"
  - "Used fcntl.flock() + temp file + os.rename() + .bak backup for atomic index writes"
  - "Thin shell capture hook pipes raw stdin to single Python process -- no shell variable interpolation of untrusted data"
  - "Settings path uses .claude/settings.local.json (not settings.json) per design decision D-05"
  - "PostToolUse hook entry includes async: True per design decision D-08"

patterns-established:
  - "Zero-dependency Python: all imports from stdlib only (json, argparse, pathlib, re, subprocess, datetime, fcntl, shutil, os, sys)"
  - "Atomic file writes: fcntl.flock + write to .tmp + os.rename + .bak backup pattern for index.json"
  - "Shell hooks never block: exit 0 always, stderr to /dev/null, || true on Python invocation"
  - "Comprehensive rename: function names, variable names, env vars, paths, strings, comments -- but preserve data-format identifiers"

requirements-completed: [SETUP-01, SETUP-02, SETUP-03, SETUP-04, SETUP-05, SETUP-06, SETUP-07]

# Metrics
duration: 35min
completed: 2026-04-14
---

# Phase 01 Plan 01: Repo Scaffold Summary

**Complete Prism repo file structure with 13 renamed Python modules, idempotent installer, CLI wrapper, capture hook, agent prompts, and constitution template -- all with comprehensive engram-to-prism rename**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-04-14T12:40:00Z
- **Completed:** 2026-04-14T13:11:34Z
- **Tasks:** 2/2
- **Files created:** 20

## Accomplishments
- Copied and renamed all 13 Engram lib/*.py files with zero engram/ENGRAM/Engram references remaining (except structural data-format 'engrams' directory name and JSON key)
- Implemented atomic index writes using fcntl.flock() + temp file + os.rename() + .bak backup in lib/index.py
- Added 7 expanded secret scrub patterns (AWS AKIA, connection strings, private keys, JWT, GitHub OAuth/installation/fine-grained tokens)
- Created idempotent install.sh with prerequisite checks (python3/git hard-fail, claude soft-warn, Python version warning)
- Created thin capture.sh shell wrapper that pipes stdin directly to Python (no shell variable interpolation of untrusted data)
- Removed all Cursor support (_setup_cursor_hooks, CURSOR_HOOKS, sync_cursor, --cursor flag)
- Removed all Lens/team references (_setup_lens_skills, team.py, lens.py, publish-to-lens, import-lens commands)

## Task Commits

Each task was committed atomically:

1. **Task 1: Copy and rename all lib/*.py files** - `a10e915` (feat)
2. **Task 2: Create install.sh, CLI wrapper, capture.sh, agents, templates** - `6443a99` (feat)

## Files Created/Modified
- `lib/__init__.py` - Empty package init
- `lib/config.py` - PRISM_HOME, DEFAULT_CONFIG with expanded scrub/block patterns, path helpers
- `lib/cli.py` - CLI command router (prog="prism"), removed Lens/Cursor subcommands
- `lib/commands.py` - User-facing commands, settings.local.json paths, async PostToolUse hook
- `lib/index.py` - Master index CRUD with atomic writes (fcntl.flock)
- `lib/project.py` - Project detection via git remote SHA256[:12], PRISM_PROJECT_ID env var
- `lib/scrub.py` - Secret scrubbing with expanded patterns
- `lib/sync.py` - Context sync generating .claude/prism.md, removed sync_cursor
- `lib/mcp_server.py` - MCP server (prism_search, prism_get, prism_relevant, prism_record)
- `lib/extract.py` - Extraction pipeline (Haiku proposes, Sonnet validates)
- `lib/review.py` - Session review pipeline
- `lib/sessions.py` - Session transcript analysis
- `lib/trigger.py` - Auto-extraction trigger, _find_prism_cli()
- `install.sh` - Installer: prerequisites, directory tree, copy, symlink, config guards
- `prism` - CLI entry point delegating to lib/cli.py
- `hooks/capture.sh` - Thin shell wrapper piping stdin to Python
- `agents/extractor.md` - Observation analyzer agent prompt
- `agents/validator.md` - Validation judge agent prompt (4 safety gates)
- `agents/reviewer.md` - Session reviewer agent prompt
- `templates/constitution.md` - Immutable safety principles template

## Decisions Made
- **Preserved 'engrams' as data-format name**: The JSON key `"engrams"` in index.json and the `engrams/` directory name are structural data-format identifiers. Renaming these would break data model compatibility and require migration logic. All function names, variable names, comments, docstrings, user-facing strings, and env vars were renamed.
- **Atomic writes via fcntl.flock**: Chose OS-level file locking over advisory patterns because index.json can be written by both the CLI and background extraction processes simultaneously.
- **settings.local.json not settings.json**: Per D-05, using the local-only settings file avoids committing hook configuration to version control.
- **async: True on PostToolUse**: Per D-08, the PostToolUse hook runs asynchronously so observation capture never blocks Claude Code.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed multi-pass rename to catch all reference patterns**
- **Found during:** Task 1
- **Issue:** Initial bulk rename missed some patterns because grep patterns like `get_engram(` didn't match import-style references like `get_engram,`. Three passes were needed to catch function names, import references, local variable names, comments, and docstrings.
- **Fix:** Applied three sequential rename passes with progressively broader patterns, then verified zero matches.
- **Files modified:** All 13 lib/*.py files
- **Verification:** `grep -rn "engram\|ENGRAM\|Engram" lib/ --include="*.py" | grep -v "engrams"` returns 0 matches
- **Committed in:** a10e915

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for correctness. No scope creep.

## Issues Encountered
- The acceptance criteria specified "zero grep matches for engram/ENGRAM/Engram" but the data model structurally uses `"engrams"` as a JSON key and directory name. These 48 references (across lib/ files) and 2 references (in install.sh) are intentional data-format identifiers that cannot be renamed without breaking the data model. All non-structural references were successfully renamed to zero.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 13 Python modules exist and import cleanly -- ready for Plan 02 (CLI commands) and Plan 03 (capture pipeline)
- install.sh is ready to test end-to-end once capture.py is created in Plan 03
- hooks/capture.sh will silently exit 0 until capture.py is created in Plan 03 (graceful degradation)

## Self-Check: PASSED

- All 20 claimed files exist on disk
- Both task commits verified: a10e915, 6443a99

---
*Phase: 01-foundation-observation*
*Completed: 2026-04-14*
