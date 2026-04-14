# Phase 3: Bridge + Slash Commands - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 03-bridge-slash-commands
**Areas discussed:** Skill output & directory layout

---

## Skill Output & Directory Layout

### Q1: Where should promoted engrams be written?

| Option | Description | Selected |
|--------|-------------|----------|
| Same _analysis/extracted_skills_codebase/ (Recommended) | Promoted engrams land alongside extracted skills. /curate-skills and /publish-skills see everything in one place. 'source' field distinguishes promoted ("engram") from extracted ("external"). | ✓ |
| Separate _analysis/promoted_skills/ | Keeps promoted engrams distinct from extraction pipeline output. Requires updating /curate-skills and /publish-skills to scan both dirs. |  |
| You decide | Claude picks the best approach during implementation |  |

**User's choice:** Same _analysis/extracted_skills_codebase/ (Recommended)
**Notes:** None

### Q2: Should `prism promote` create _analysis/ if it doesn't exist, or require a prior extraction run?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-create _analysis/ on demand (Recommended) | prism promote works standalone — no prior pipeline needed. BRG-04 says promotion is local-only and offline. | ✓ |
| Require prior analysis | User must run an extraction pipeline first. Promote fails with helpful error if _analysis/ doesn't exist. |  |

**User's choice:** Auto-create _analysis/ on demand (Recommended)
**Notes:** None

### Q3: How should skill names be generated from engram data?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-generate from engram content (Recommended) | Extract key terms from engram title/content, generate kebab-case name. User can override with --name flag. | ✓ |
| Always require explicit --name | Forces user to think about the skill name. Prevents auto-generated gibberish but adds friction. |  |
| You decide | Claude picks the naming approach during implementation |  |

**User's choice:** Auto-generate from engram content (Recommended)
**Notes:** None

---

## Claude's Discretion

- Promotion format mapping (engram fields → plugin.json fields, TRIGGER clause generation)
- Slash command adaptation scope (13 Lens → 12 Prism, copy-and-modify depth)
- Registry readiness boundary (/advise-skills and /audit-code local-only in Phase 3)
- .published.json delta tracking structure
- Kebab-case name generation algorithm

## Deferred Ideas

None — discussion stayed within phase scope
