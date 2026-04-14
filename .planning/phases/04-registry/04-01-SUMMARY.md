---
phase: 04-registry
plan: 01
subsystem: registry
tags: [multi-registry, registries.json, token-management, argparse, cli]

# Dependency graph
requires:
  - phase: 03-bridge-slash-commands
    provides: "CLI skeleton, config.py with registry_url, commands.py pattern"
provides:
  - "lib/registry.py with full registry CRUD (load/save/add/remove/list/default/get/token)"
  - "CLI registry subcommand group with nested token sub-subcommands"
  - "Auto-migration from config.json registry_url to registries.json"
  - "Token generation with secrets.token_hex(32) and prism_ prefix"
affects: [04-02-PLAN, 04-03-PLAN, publish-skills, advise-skills, audit-code]

# Tech tracking
tech-stack:
  added: [secrets]
  patterns: [nested-argparse-subcommands, registries-json-atomic-write, kebab-case-validation]

key-files:
  created: [lib/registry.py]
  modified: [lib/cli.py, lib/commands.py]

key-decisions:
  - "Used Optional[dict] instead of dict | None for Python 3.9 compat"
  - "Token length is 70 chars (6-char 'prism_' prefix + 64 hex), not 69 as plan stated"
  - "Single-char registry names allowed as edge case in kebab-case validation"

patterns-established:
  - "registries.json atomic writes: temp file + os.rename + chmod 0o600"
  - "Nested argparse subcommands for CLI command groups (registry -> token)"
  - "Token masking in list output: first 8 chars + '...' for display"

requirements-completed: [REG-02, REG-03, REG-04, REG-05, REG-06, REG-07]

# Metrics
duration: 2min
completed: 2026-04-14
---

# Phase 4 Plan 01: Registry Config Layer Summary

**Multi-registry CRUD in lib/registry.py with 10 functions, CLI subcommand group with nested token management, auto-migration from config.json**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-14T19:56:10Z
- **Completed:** 2026-04-14T19:58:29Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created lib/registry.py with 10 exported functions for complete registry configuration management
- Wired `prism registry` CLI subcommand group with 7 subcommands including nested `token create/revoke`
- Implemented security mitigations: 0o600 file permissions, kebab-case name validation, secrets-based token generation, token masking in list output

## Task Commits

Each task was committed atomically:

1. **Task 1: Create lib/registry.py with full registry CRUD and migration** - `2dcb295` (feat)
2. **Task 2: Wire registry subcommand group into CLI and commands** - `0869fa3` (feat)

## Files Created/Modified
- `lib/registry.py` - Registry configuration management: load/save/add/remove/list/default/get/token CRUD with atomic writes and migration
- `lib/cli.py` - Added registry subcommand group with nested sub-subcommands for token management
- `lib/commands.py` - Added cmd_registry dispatcher routing all 7 subcommands with ANSI color output

## Decisions Made
- Used `Optional[dict]` type hint instead of `dict | None` union syntax for compatibility with Python 3.9 (system Python on macOS)
- Token is 70 chars total (6-char `prism_` prefix + 64 hex chars from token_hex(32)), correcting plan's assertion of 69 (which miscounted prefix as 5 chars)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Python 3.9 type union syntax**
- **Found during:** Task 1 (lib/registry.py creation)
- **Issue:** `dict | None` type union syntax requires Python 3.10+, but system Python is 3.9
- **Fix:** Changed to `Optional[dict]` with `from typing import Optional`
- **Files modified:** lib/registry.py
- **Verification:** Import succeeds on Python 3.9
- **Committed in:** 2dcb295 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor type hint fix for broader Python compatibility. No scope creep.

## Issues Encountered
None beyond the type hint fix above.

## Threat Surface Scan

All threat mitigations from the plan's threat model are implemented:
- T-04-01: `os.chmod(0o600)` after every save_registries() write; tokens masked in list_registries() output
- T-04-02: Kebab-case regex validation in add_registry() before writing
- T-04-03: `secrets.token_hex(32)` for cryptographic token generation
- T-04-04: Token displayed once in `prism registry token create` (accepted risk)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- lib/registry.py provides the data layer all other Phase 4 plans depend on
- Plan 02 can build registry template bundle using the token generation and registry CRUD functions
- Plan 03 can implement multi-registry reads/writes using load_registries, get_registry, resolve_token

---
*Phase: 04-registry*
*Completed: 2026-04-14*
