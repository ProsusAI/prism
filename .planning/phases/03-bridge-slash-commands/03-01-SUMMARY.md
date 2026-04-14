---
phase: 03-bridge-slash-commands
plan: 01
subsystem: bridge
tags: [engram, skill, plugin-json, promote, cli]

# Dependency graph
requires:
  - phase: 02-personal-knowledge-loop
    provides: engram index with get_entry(), config with get_config(), CLI router pattern
provides:
  - cmd_promote() function converting engrams to skill format (plugin.json + SKILL.md)
  - plugin.schema.json with engram source type
  - promote CLI subcommand with --name override
  - install.sh copies skills/ and schemas/ directories
affects: [03-bridge-slash-commands plan 02 (curate), 03-bridge-slash-commands plan 03 (publish)]

# Tech tracking
tech-stack:
  added: []
  patterns: [gate-check-before-promotion, engram-to-skill-conversion, kebab-case-name-generation, TRIGGER-when-description-format]

key-files:
  created:
    - lib/bridge.py
    - schemas/plugin.schema.json
  modified:
    - lib/cli.py
    - lib/config.py
    - install.sh

key-decisions:
  - "Used subprocess with timeout=5 for all git calls (T-03-03 mitigation)"
  - "Description builder generates TRIGGER when: clause from domain+kind scenarios"
  - "Stop-word removal in name generation prevents verbose skill names"

patterns-established:
  - "Gate check pattern: confidence >= min, evidence >= min, source != registry before promotion"
  - "Engram-to-skill conversion: frontmatter parsing + plugin.json + SKILL.md generation"
  - "Output to _analysis/extracted_skills_codebase/<name>/ for downstream curate/publish"

requirements-completed: [BRG-01, BRG-02, BRG-03, BRG-04]

# Metrics
duration: 2min
completed: 2026-04-14
---

# Phase 3 Plan 1: Engram-to-Skill Promotion Summary

**cmd_promote() with gate checks, kebab-case name generation, plugin.json + SKILL.md output, schema with engram source type, install.sh skills/schemas copy**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-14T15:23:39Z
- **Completed:** 2026-04-14T15:26:09Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Created lib/bridge.py with complete engram-to-skill promotion pipeline: gate checks (confidence, evidence, source), frontmatter parsing, skill name generation, plugin.json and SKILL.md output
- Added promote subcommand to CLI with --name override for custom skill names
- Created schemas/plugin.schema.json with engram added as valid source type alongside internal/external
- Updated install.sh to copy skills/ subdirectories and schemas/*.json into ~/.prism/ on install/upgrade

## Task Commits

Each task was committed atomically:

1. **Task 1: Create lib/bridge.py with cmd_promote and wire CLI + config** - pending (orchestrator commits)
2. **Task 2: Add plugin.schema.json and update install.sh** - pending (orchestrator commits)

## Files Created/Modified
- `lib/bridge.py` - Engram-to-skill promotion: cmd_promote(), gate checks, name generation, plugin.json/SKILL.md builders, git helpers
- `lib/cli.py` - Added promote subparser and routing to cmd_promote
- `lib/config.py` - Added publish_min_evidence: 3 default config key
- `schemas/plugin.schema.json` - JSON Schema with engram source type (copied from Lens, modified)
- `install.sh` - Added steps 4b (copy skills/) and 4c (copy schemas/) for install/upgrade

## Decisions Made
- Used subprocess with timeout=5 for all git calls to prevent hanging on broken git repos (T-03-03 threat mitigation)
- Description builder generates TRIGGER when: clause by combining domain-based and kind-based scenarios, ensuring >= 50 char minimum
- Stop-word removal (23 common words) in name generation prevents verbose multi-word skill names
- Name validation falls back to kind-based name (e.g., "preference-skill") if generated name fails pattern check

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- lib/bridge.py cmd_promote() is ready for /curate-skills and /publish-skills slash commands to consume
- Output directory (_analysis/extracted_skills_codebase/<name>/) matches expected input for downstream tools
- Schema file ready for CI validation of promoted skills

## Self-Check: PASSED

All 6 files verified present: lib/bridge.py, lib/cli.py, lib/config.py, schemas/plugin.schema.json, install.sh, 03-01-SUMMARY.md.

---
*Phase: 03-bridge-slash-commands*
*Completed: 2026-04-14*
