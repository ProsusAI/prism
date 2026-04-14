# Phase 4: Registry - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Teams can create, configure, and manage shared skill registries backed by GitHub repos and Cloudflare Workers, with full multi-registry support for reading, writing, and querying across organizational boundaries. Delivers: `prism registry create/add/remove/list/default`, `prism registry token create/revoke`, registry template bundle, multi-registry reads with merge and cache, multi-registry writes with per-registry delta tracking. Personal learning features and slash commands are complete from prior phases.

</domain>

<decisions>
## Implementation Decisions

### Multi-Registry Configuration
- **D-01:** Registry configuration lives in a separate `~/.prism/registries.json` file, not inline in `config.json`. Clean separation — `config.json` stays focused on personal settings, `registries.json` is dedicated to registry configs.
- **D-02:** The existing `config.json` `registry_url` field becomes a migration path — if `registries.json` doesn't exist but `config.json` has `registry_url`, auto-migrate it as the `"default"` registry entry on first access.

### Multi-Registry Reads
- **D-03:** Fetch `skill-registry.json` from every configured registry, merge into one deduplicated list, tag each result with `[registry-name]` (e.g., `[team]`, `[community]`). Queries always search everything — no opt-out per query.
- **D-04:** One cache file per registry at `~/.prism/cache/{registry-name}.json` with filesystem mtime-based TTL check (24h). Each registry cached independently. Simple, greppable, no cross-contamination on cache invalidation.
- **D-05:** `prism registry default` affects writes only — it controls where `/publish-skills` sends skills. Reads always merge all configured registries regardless of default.

### Multi-Registry Writes
- **D-06:** `/publish-skills` resolves the target registry (default or `--registry NAME`), checks writable flag, diffs against `.published.json` entry for that specific registry name, and POSTs delta to the target Worker API.
- **D-07:** `.published.json` already supports per-registry keys from Phase 3 (uses `"default"` key). Phase 4 extends this to use actual registry names as keys.

### Registry Creation Flow
- **D-08:** `prism registry create` is a guided wizard with manual steps — walks the user through: 1) create GitHub repo from template (via `gh` CLI), 2) deploy Worker (user runs `wrangler deploy`), 3) set secrets (user runs `wrangler secret put`), 4) generate initial API token, 5) configure local Prism. Each step has clear instructions and verification prompts. User stays in control.
- **D-09:** Template files live under `templates/registry/` in the Prism repo. Contains: Worker source (adapted TypeScript), `wrangler.toml`, `package.json`, CI workflows (`validate-pr.yml`, `build-registry.yml`), validation schema (`plugin.schema.json`), build script (`build_registry.py`), validation script (`validate.py`). `prism registry create` copies this directory to the new repo.
- **D-10:** The template Worker is adapted from the Lens Worker with improvements: updated endpoint paths (`/publish` → `/api/skills/publish` as Phase 3's `/publish-skills` already targets), Wrangler v4 + latest `@cloudflare/workers-types`, `User-Agent: Prism-Worker`, service name `prism-registry`, Prism-specific metadata. Not a blind copy — match what the existing client code expects.

### Token Management
- **D-11:** Tokens are managed on the Worker side (stored in `REGISTRY_TOKENS` Wrangler secret as comma-separated list). `prism registry token create` generates a random token locally, instructs the user to add it to their Worker's secret. `prism registry token revoke` instructs the user to update the secret. Local Prism stores the token per-registry in `registries.json`.

### Claude's Discretion
- `registries.json` schema structure (required fields per registry entry: name, url, token, writable, read_only flags)
- Exact `prism registry create` wizard step text and verification checks
- Cache directory creation and cleanup strategy
- How `prism registry list` formats output (table, list, etc.)
- Token generation algorithm (random hex, UUID, etc.)
- Migration logic from `config.json` `registry_url` to `registries.json` — exact trigger and one-time flag
- How `prism registry remove` handles the case where the removed registry is the default

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Lens Worker source (template base)
- `/Users/gaurav/codes/Lens/cloudfare_worker/src/index.ts` — Complete Worker implementation: auth, GitHub proxy, skill publish via PR, validation. ~400 lines. Adapt for Prism template.
- `/Users/gaurav/codes/Lens/cloudfare_worker/wrangler.toml` — Wrangler config with env vars (GH_OWNER, GH_REPO, GH_BRANCH). Update for Prism template.
- `/Users/gaurav/codes/Lens/cloudfare_worker/package.json` — Dependencies: wrangler ^3.99.0, @cloudflare/workers-types. Update to v4.

### Lens CI workflows (template base)
- `/Users/gaurav/codes/Lens/.github/workflows/validate-pr.yml` — PR validation: runs scripts/validate.py on skills/** changes
- `/Users/gaurav/codes/Lens/.github/workflows/build-registry.yml` — Registry rebuild: runs scripts/build_registry.py after validation passes on main

### Lens scripts (template base)
- `/Users/gaurav/codes/Lens/scripts/validate.py` — Skill validation against plugin.schema.json (CI-only, uses jsonschema)
- `/Users/gaurav/codes/Lens/scripts/build_registry.py` — Builds skill-registry.json from skills/ directory

### Lens schema
- `/Users/gaurav/codes/Lens/schemas/plugin.schema.json` — JSON Schema for plugin.json validation

### Prism codebase (existing code to extend)
- `lib/config.py` — Config management, has `registry_url` field. Needs `registries.json` handling added.
- `lib/commands.py` — CLI commands, needs `registry` subcommands added
- `lib/cli.py` — CLI router with argparse, needs `registry` subcommand group
- `skills/publish-skills/SKILL.md` — Current publish implementation targeting `/api/skills/publish` endpoint
- `skills/advise-skills/SKILL.md` — Current advise implementation, needs multi-registry search
- `skills/audit-code/SKILL.md` — Current audit implementation, needs multi-registry search
- `install.sh` — Installer, needs to copy `templates/registry/` to `~/.prism/templates/registry/`

### Design and requirements
- `unified-design.md` — Complete design document with registry commands spec
- `.planning/PROJECT.md` — Key decisions (Worker-only, zero-dependency, copy-and-modify)
- `.planning/REQUIREMENTS.md` — REG-01 through REG-12

### Prior phase context
- `.planning/phases/03-bridge-slash-commands/03-CONTEXT.md` — D-01 (skill output directory), Phase 3 Claude's Discretion (registry readiness boundary, .published.json structure)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lib/config.py`: Config management with `load_config()`, `save_config()`, `get_config()`, `set_config()`. Has `registry_url` field in DEFAULT_CONFIG. Can be extended for `registries.json` load/save.
- `lib/commands.py`: All existing CLI commands. `_setup_slash_commands()` handles symlinks. Pattern for adding new subcommand groups.
- `skills/publish-skills/SKILL.md`: Complete publish implementation with delta tracking, Worker API POST, `.published.json` atomic writes. Targets `POST {registry_url}/api/skills/publish`. Multi-registry extension needs per-registry URL resolution.
- `skills/advise-skills/SKILL.md` and `skills/audit-code/SKILL.md`: Query commands that currently read from local `skill-registry.json`. Need to fetch + merge from all configured registries.
- Lens Worker (`cloudfare_worker/src/index.ts`): 400-line TypeScript with auth, GitHub proxy reads, skill publish via Git API (branch → blobs → tree → commit → PR). Endpoints: `GET /registry`, `GET /skills/:name`, `POST /publish`.
- Lens CI workflows: validate-pr.yml + build-registry.yml — complete CI for skill validation and registry rebuilds.

### Established Patterns
- Python stdlib only (json, pathlib, re, hashlib, subprocess, urllib.request) — zero-dependency constraint
- Atomic writes via temp file + `os.rename()` for JSON files (config, index, .published.json)
- `subprocess.run()` for external CLI calls (claude, gh)
- SHA256[:12] content hashes for delta tracking
- `REGISTRY_TOKEN` env var for auth (not stored in config files)
- Kebab-case naming for skills and registries

### Integration Points
- CLI: `lib/cli.py` argparse subparsers need `registry` subcommand group with nested subcommands (create, add, remove, list, default, token)
- Install: `install.sh` needs to copy `templates/registry/` to `~/.prism/templates/registry/`
- Config: New `~/.prism/registries.json` alongside existing `~/.prism/config.json`
- Cache: New `~/.prism/cache/` directory for per-registry cache files
- Slash commands: `/publish-skills`, `/advise-skills`, `/audit-code` need multi-registry awareness
- `gh` CLI: Required for `prism registry create` (repo creation from template)

</code_context>

<specifics>
## Specific Ideas

- The Lens Worker endpoint is `POST /publish` but Phase 3's `/publish-skills` already targets `POST /api/skills/publish` — the template Worker must match what the client expects, not the other way around.
- `registries.json` should be simple: `{"registries": [{"name": "team", "url": "https://...", "token_env": "TEAM_REGISTRY_TOKEN", "writable": true}, ...], "default": "team"}`.
- Cache files use filesystem mtime — `os.path.getmtime()` compared against `time.time() - 86400`. No custom timestamp tracking needed.
- The guided wizard pattern is similar to `gh repo create` — step-by-step with verification between steps.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-registry*
*Context gathered: 2026-04-14*
