# Phase 4: Registry - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 04-registry
**Areas discussed:** Multi-registry architecture, Registry creation flow

---

## Multi-registry architecture

### Registry configuration location

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in config.json | Add a `registries` dict inside existing ~/.prism/config.json | |
| Separate registries.json | New file ~/.prism/registries.json dedicated to registry configs | ✓ |
| You decide | Claude picks the approach that fits the existing config pattern best | |

**User's choice:** Separate registries.json
**Notes:** Clean separation from personal settings

### Multi-registry read behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Merge all, tag source | Fetch from every registry, merge, tag with [registry-name] | ✓ |
| Default registry first, others on demand | Only query default automatically, others with --registry flag | |
| You decide | Claude picks based on requirements | |

**User's choice:** Merge all, tag source
**Notes:** Matches REG-09 requirement

### Cache strategy

| Option | Description | Selected |
|--------|-------------|----------|
| One cache file per registry | ~/.prism/cache/{registry-name}.json with mtime-based TTL | ✓ |
| Single merged cache file | ~/.prism/cache/registries-cache.json with per-registry timestamps | |
| You decide | Claude picks based on simplicity | |

**User's choice:** One cache file per registry
**Notes:** Simple, greppable, independent invalidation

### Default registry scope

| Option | Description | Selected |
|--------|-------------|----------|
| Writes only | Default controls publish target. Reads always merge all. | ✓ |
| Both reads and writes | Default is primary for both querying and publishing | |
| You decide | Claude picks based on requirements | |

**User's choice:** Writes only
**Notes:** Cleaner separation — you always see everything

---

## Registry creation flow

### Automation level

| Option | Description | Selected |
|--------|-------------|----------|
| Guided wizard with manual steps | Walk user through each step with instructions and verification | ✓ |
| Fully automated end-to-end | Single command does everything, needs rollback logic | |
| You decide | Claude picks based on constraint complexity | |

**User's choice:** Guided wizard with manual steps
**Notes:** User stays in control, similar to `gh repo create`

### Template file organization

| Option | Description | Selected |
|--------|-------------|----------|
| templates/registry/ directory | All template files in Prism repo, copied to new repo by create command | ✓ |
| Bundled at ~/.prism/templates/ | install.sh copies to installed location, create reads from there | |
| You decide | Claude picks simplest approach | |

**User's choice:** templates/registry/ directory
**Notes:** Keep in repo, install.sh copies to ~/.prism/templates/registry/

### Worker adaptation

| Option | Description | Selected |
|--------|-------------|----------|
| Copy and rebrand | Direct copy of Lens Worker with renames only | |
| Adapt with improvements | Start from Lens, update endpoints, wrangler v4, match Phase 3 client expectations | ✓ |
| You decide | Claude picks based on existing client code | |

**User's choice:** Adapt with improvements
**Notes:** Must match what /publish-skills already targets (/api/skills/publish)

---

## Claude's Discretion

- registries.json schema structure
- Exact wizard step text and verification checks
- Cache directory creation/cleanup
- prism registry list output format
- Token generation algorithm
- Migration logic from config.json registry_url
- prism registry remove handling when removing default

## Deferred Ideas

None — discussion stayed within phase scope
