---
phase: 04-registry
plan: 02
subsystem: registry-template
tags: [cloudflare-worker, ci, template, registry]

requires: []
provides:
  - "Registry template: Cloudflare Worker, CI workflows, validation scripts, JSON Schema"
  - "install.sh copies templates/registry/ and creates cache/ directory"
affects: [prism-registry-create]

tech-stack:
  added: [wrangler-4.82, cloudflare-workers-types, typescript-5.8]
  patterns: [github-git-api-pr-creation, bearer-token-auth, flat-field-payload-validation]

key-files:
  created:
    - templates/registry/worker/src/index.ts
    - templates/registry/worker/wrangler.toml
    - templates/registry/worker/package.json
    - templates/registry/worker/tsconfig.json
    - templates/registry/ci/validate-pr.yml
    - templates/registry/ci/build-registry.yml
    - templates/registry/scripts/validate.py
    - templates/registry/scripts/build_registry.py
    - templates/registry/schemas/plugin.schema.json
    - templates/registry/README.md
  modified:
    - install.sh

key-decisions:
  - "Adapted Lens Worker structure with Prism flat-field payload format (not Lens skill_md/plugin_json format)"
  - "Added DoS mitigation: MAX_SKILLS_PER_BATCH=50, MAX_CONTENT_LENGTH=500KB per skill"
  - "Relaxed plugin.schema.json description pattern (removed TRIGGER requirement) for broader Prism compatibility"
  - "Made source_hash optional in schema (not in required array) since Prism may publish without it"

patterns-established:
  - "Flat-field publish payload: Worker reconstructs plugin.json from individual fields"
  - "DoS limits: 50 skills per batch, 500KB per skill content"

requirements-completed: [REG-08]

duration: 3min
completed: 2026-04-14
---

# Phase 4 Plan 2: Registry Template Bundle Summary

Complete registry template with Cloudflare Worker accepting Prism flat-field publish payload, CI workflows, validation scripts, and JSON Schema -- bundled for `prism registry create`.

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create template Worker, config, CI workflows, scripts, and schema | 64c1770 | 10 files created under templates/registry/ |
| 2 | Update install.sh to copy templates and create cache directory | d534871 | install.sh modified |

## Key Implementation Details

### Worker (index.ts)
- Service: `prism-registry`, User-Agent: `Prism-Worker/1.0`
- Routes: `GET /registry`, `GET /api/skills/registry` (alias), `POST /api/skills/publish`, `GET /health`, `GET /file/*`
- Auth: Bearer token validated against `REGISTRY_TOKENS` comma-separated secret
- Validation: `validatePrismPublish()` -- name regex, content min 50 chars, required fields, same-repository constraint, duplicate detection
- DoS limits: 50 skills per batch, 500KB per skill content
- File building: Reconstructs `plugin.json` from flat fields, uses `content` as `SKILL.md`
- PR creation: Git API flow (get ref -> create blobs -> create tree -> create commit -> create branch -> create PR)

### CI Workflows
- `validate-pr.yml`: Runs `validate.py` on skills/** changes (PR and push to main)
- `build-registry.yml`: Runs `build_registry.py` after validation passes, commits updated `skill-registry.json`

### Schema
- `plugin.schema.json`: Adapted from Lens with `source_hash` as optional field, relaxed description pattern

### install.sh
- Copies `templates/registry/` to `~/.prism/templates/registry/` (idempotent)
- Creates `~/.prism/cache/` directory for registry cache files

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Security] Added DoS mitigation for publish payloads**
- **Found during:** Task 1
- **Issue:** Threat model T-04-08 requires payload size limits. Lens Worker had none.
- **Fix:** Added `MAX_SKILLS_PER_BATCH = 50` and `MAX_CONTENT_LENGTH = 500_000` constants with validation checks.
- **Files modified:** templates/registry/worker/src/index.ts
- **Commit:** 64c1770

**2. [Rule 2 - Compatibility] Relaxed schema description pattern**
- **Found during:** Task 1
- **Issue:** Lens schema required `"TRIGGER when:?"` pattern in description which Prism skills may not follow.
- **Fix:** Removed the pattern constraint, kept minLength 10.
- **Files modified:** templates/registry/schemas/plugin.schema.json
- **Commit:** 64c1770

## Self-Check: PASSED

All 11 files verified present. Both task commits (64c1770, d534871) verified in git log.
