---
phase: 05-integration-fixes-hardening
plan: 02
subsystem: integration
tags: [project-id-cache, env-var, install-hardening, documentation]

requires:
  - phase: 01-core-library
    provides: "commands.py cmd_init, mcp_server.py, capture.py hook pipeline"
provides:
  - "Project ID cache file (.claude/.prism_project_id) written by prism init"
  - "Consistent PRISM_PROJECT_ID env var across commands.py and mcp_server.py"
  - "install.sh excludes test_*.py from lib copy and has complete config heredoc"
affects: [capture-performance, mcp-server-config]

tech-stack:
  added: []
  patterns: [project-id-caching-for-hook-performance]

key-files:
  created: []
  modified:
    - lib/commands.py
    - lib/mcp_server.py
    - install.sh
    - .planning/phases/04-registry/04-02-SUMMARY.md

key-decisions:
  - "Cache file uses .claude/.prism_project_id (dotfile, gitignored) matching capture.py's read path"
  - "Standardized on PRISM_PROJECT_ID (not PRISM_PROJECT) to match capture.py convention"
  - "scrub_patterns and block_patterns intentionally omitted from install.sh heredoc (large lists merged from DEFAULT_CONFIG at runtime)"

patterns-established:
  - "Project ID cache: prism init writes, capture.py reads, avoids git subprocess on every hook invocation"

requirements-completed: [OBS-05, SETUP-01, SETUP-03]

duration: 2min
completed: 2026-04-15
---

# Phase 5 Plan 2: Integration Fixes and Hardening Summary

**Project ID cache for hook performance, PRISM_PROJECT_ID env var standardization, install.sh test-file exclusion, and config heredoc completion**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-15T08:04:05Z
- **Completed:** 2026-04-15T08:06:44Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- prism init now writes .claude/.prism_project_id so capture.py avoids git subprocess on every hook invocation
- Env var name standardized to PRISM_PROJECT_ID across commands.py (setter) and mcp_server.py (reader)
- install.sh excludes test_*.py files from lib copy to production installs
- install.sh config.json heredoc now includes publish_min_evidence: 3
- 04-02-SUMMARY.md frontmatter corrected to match summary template (hyphenated keys, patterns-established, requirements-completed)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write project ID cache file and standardize env var names** - `8d5a6ba` (fix)
2. **Task 2: Harden install.sh and fix documentation artifacts** - `4387755` (fix)

## Files Created/Modified
- `lib/commands.py` - Added .prism_project_id cache write in cmd_init, renamed env var to PRISM_PROJECT_ID, added cache file to gitignore entries
- `lib/mcp_server.py` - Renamed PRISM_PROJECT to PRISM_PROJECT_ID in both _record() and _handle_tool_call()
- `install.sh` - Replaced single cp with loop excluding test_* files, added publish_min_evidence to config heredoc
- `.planning/phases/04-registry/04-02-SUMMARY.md` - Fixed frontmatter to use hyphenated keys matching template format

## Decisions Made
- Cache file uses .claude/.prism_project_id (dotfile, gitignored) matching capture.py's existing read path
- Standardized on PRISM_PROJECT_ID (with _ID suffix) to match capture.py convention; the old PRISM_PROJECT name was inconsistent
- scrub_patterns and block_patterns intentionally omitted from install.sh heredoc since they are large lists that get merged from DEFAULT_CONFIG at runtime via get_config()

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All v1.0 milestone integration fixes complete
- Project ID cache, env var consistency, and install hardening close the remaining audit gaps

## Self-Check: PASSED

All 4 modified files verified present. Both task commits (8d5a6ba, 4387755) verified in git log.

---
*Phase: 05-integration-fixes-hardening*
*Completed: 2026-04-15*
