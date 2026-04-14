# Phase 3: Bridge + Slash Commands - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

High-quality personal engrams can be promoted to publishable team skill format, and the full suite of slash commands for codebase analysis, skill extraction, curation, publishing, and querying is available. Delivers: `prism promote` CLI command, 12 slash commands adapted from Lens (analysis pipelines, extraction, curation, publishing, querying), unified `/publish-skills` with delta tracking. Registry creation and multi-registry management are Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Skill Output & Directory Layout
- **D-01:** Promoted engrams are written to `_analysis/extracted_skills_codebase/<name>/` — same directory as extraction pipeline output. The `source` field in plugin.json distinguishes promoted engrams (`"engram"`) from extracted skills (`"external"`). This way `/curate-skills` and `/publish-skills` see everything in one place without scanning multiple directories.
- **D-02:** `prism promote` auto-creates `_analysis/extracted_skills_codebase/` on demand if it doesn't exist. No prior extraction pipeline run required. BRG-04 requires promotion to work fully offline and standalone.
- **D-03:** Skill names are auto-generated from engram content — extract key terms from engram title/content, generate kebab-case name matching the `^[a-z][a-z0-9]*(-[a-z0-9]+)+$` pattern required by plugin.schema.json. User can override with `--name` flag.

### Claude's Discretion
- Promotion format mapping: how engram fields (type, confidence, evidence, content) map to plugin.json fields (description, category, TRIGGER clause). The schema requires specific fields — Claude should follow plugin.schema.json and generate a TRIGGER clause from the engram's content.
- Slash command adaptation scope: how much to modify the 13 Lens commands into Prism's 12. Lens has separate publish-skills-cloudflare and publish-skills-github — Prism unifies to one `/publish-skills`. Commands reference `_analysis/` directories and Lens-specific paths that need updating. Follow the copy-and-modify approach (Phase 1 D-01).
- Registry readiness boundary: `/advise-skills` and `/audit-code` query registries. In Phase 3, these should work with local `skill-registry.json` if available. Full multi-registry support comes in Phase 4.
- `.published.json` delta tracking structure and content hash algorithm for `/publish-skills`
- Exact kebab-case name generation algorithm from engram content
- Which Lens command files need heavy rewriting vs light rename-and-ship

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Lens source (primary copy source for slash commands)
- `/Users/gaurav/codes/Lens/CLAUDE.md` — Complete overview of all 13 Lens commands, directory structure, key conventions
- `/Users/gaurav/codes/Lens/GUIDE.md` — User guide with recommended workflow, pipeline orchestration, skill lifecycle
- `/Users/gaurav/codes/Lens/.claude/skills/` — All 13 slash command SKILL.md files (the actual command implementations to adapt)
- `/Users/gaurav/codes/Lens/schemas/plugin.schema.json` — JSON Schema for plugin.json validation (required fields: name, description, author, repository, category, source, commit_date, source_hash)
- `/Users/gaurav/codes/Lens/skill-registry.json` — Registry index format for /advise-skills and /audit-code queries
- `/Users/gaurav/codes/Lens/scripts/build_registry.py` — Registry builder script (CI reference)
- `/Users/gaurav/codes/Lens/scripts/validate.py` — Skill validation script (CI reference)

### Lens sample skill (format reference)
- `/Users/gaurav/codes/Lens/skills/claude-code/anthropic-api-prompt-cache-preservation/plugin.json` — Example plugin.json with all required fields
- `/Users/gaurav/codes/Lens/skills/claude-code/anthropic-api-prompt-cache-preservation/SKILL.md` — Example SKILL.md with YAML frontmatter and content structure

### Prism codebase (existing code to extend)
- `lib/commands.py` — Current CLI commands, _setup_slash_commands() already implemented, no promote command yet
- `lib/cli.py` — CLI router with argparse subparsers, needs promote subcommand added
- `lib/index.py` — Engram index with load_index(), engram data structure (fields available for promotion)
- `lib/sync.py` — Context sync, already references `prism promote` in push layer output (line 105)
- `lib/config.py` — Config management, PRISM_HOME path

### Design and requirements
- `unified-design.md` — Complete design document with promote command spec and slash command descriptions
- `.planning/PROJECT.md` — Key decisions (copy-and-modify, worker-only registry, zero-dependency)
- `.planning/REQUIREMENTS.md` — BRG-01 through BRG-04, SKILL-01 through SKILL-12

### Prior phase context
- `.planning/phases/01-foundation-observation/01-CONTEXT.md` — D-01 (copy fidelity), D-02 (flat structure), D-04 (Lens deferred to Phase 3)
- `.planning/phases/02-personal-knowledge-loop/02-CONTEXT.md` — D-05 (reinforcement on MCP query match), D-06 (scope-tagged merged lists)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lib/commands.py:_setup_slash_commands()` — Already symlinks skills from `~/.prism/skills/` to `.claude/skills/`. Lens commands will be installed at `~/.prism/skills/<name>/` by `install.sh` and automatically linked by `prism init`.
- `lib/index.py:load_index()` — Returns `{"engrams": [...]}` with each engram having id, type, confidence, evidence_count, tags, path. These fields feed into `prism promote`.
- `lib/sync.py` — Already generates "publish-ready" section in `.claude/prism.md` for engrams with confidence >= 0.7 and evidence >= 3, and shows `prism promote <id>` hint. The promotion gates are already surfaced to users.
- `lib/config.py:PRISM_HOME` — `~/.prism/` base path. Skills installed at `PRISM_HOME / "skills"`.
- Lens `.claude/skills/` directory — 13 complete SKILL.md files ready to copy and adapt. Each is a self-contained Claude Code slash command.

### Established Patterns
- Python stdlib only — zero-dependency constraint applies to `prism promote` (json, pathlib, re, hashlib)
- Markdown with YAML frontmatter — engrams and SKILL.md both use this format (custom parser, no PyYAML)
- `subprocess.run(["claude", ...])` — NOT needed for promote (local-only), but slash commands that use AI will call claude CLI
- Kebab-case naming in plugin.schema.json — `^[a-z][a-z0-9]*(-[a-z0-9]+)+$` pattern
- Lens skill structure: each skill = directory with `SKILL.md` + `plugin.json` (optional supporting files like question sets for `/analyze-agent-codebase`)

### Integration Points
- CLI: `lib/cli.py` subparsers need `promote` subcommand added
- Install: `install.sh` needs to copy Lens slash command SKILL.md files into `~/.prism/skills/`
- Symlinks: `prism init` already handles linking `~/.prism/skills/<name>/` → `.claude/skills/<name>/`
- Output: `_analysis/` directory in project working directory (created on demand per D-02)
- Registry: `/publish-skills` will POST to Worker API (Phase 4 provides the Worker; Phase 3 implements the client-side delta tracking and request construction)

</code_context>

<specifics>
## Specific Ideas

- Lens has 13 commands (publish-skills-cloudflare + publish-skills-github are separate). Prism unifies to 12 commands with one `/publish-skills` that handles both Worker API publishing and potentially GitHub-based publishing via the same interface. PROJECT.md says "Worker-only registry access (no GitHub-direct)" so the unified command targets the Worker API.
- The `source` field in plugin.json should use `"engram"` for promoted skills (not `"external"` which is for extracted skills from codebase analysis). This new source type makes provenance clear.
- `/advise-skills` and `/audit-code` should gracefully handle missing `skill-registry.json` — these commands become fully functional once a registry is configured in Phase 4, but should work with local skills in Phase 3.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-bridge-slash-commands*
*Context gathered: 2026-04-14*
