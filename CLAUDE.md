<!-- GSD:project-start source:PROJECT.md -->
## Project

**Prism** — knowledge layer for **Claude Code and Cursor**. Two things:
1. **Personal learning**: hooks observe tool usage, a two-phase extraction pipeline (fast model proposes, strong model validates — via `claude` or Cursor `agent` per backend) converts patterns into engrams (living, decaying knowledge). Engrams flow back into the IDE via context files (`.claude/prism.md`, `.cursor/rules/prism.mdc`) and MCP tools.
2. **Team skills**: high-confidence engrams promote to skills published to a Cloudflare Worker-backed registry that teams query.

### Hard constraints

- **Hooks never block the IDE** — `capture.sh` (Claude Code) and `capture_cursor.sh` (Cursor) must always exit 0; background spawns only.
- **Storage split** — observations + sessions live in SQLite (`~/.prism/prism.db`) via stdlib `sqlite3`. Engrams stay flat Markdown + YAML frontmatter; the engram index stays `index.json`. No external DB, no ORM.
- **AI calls via IDE CLIs only** — `claude --print` (Claude Code) or `agent -p` (Cursor). Never import the Anthropic SDK or cursor-sdk. No API keys for extraction. Routed through `lib/agent_runner.py` (`resolve_backend` + `run_agent`).
- **One extraction CLI per user** — Claude-only needs `claude login`; Cursor-only needs `agent login`. Not both unless you use both IDEs.
- **Custom YAML frontmatter parser** — never import PyYAML. Split on `---`, parse `key: value` lines.
- **`subprocess.run()` not `os.system()`** — always use `capture_output=True, text=True, timeout=N`.
- **MCP stdout is protocol-only** — any stray `print()` in lib code corrupts the JSON-RPC stream. All logging to stderr.
- **Never read `.env` files** — config comes from `os.environ` only. No dotenv parsing, no opening `.env` files.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Library / CLI | Python 3.12+ (stdlib only) | `argparse`, `json`, `pathlib`, `subprocess`, `hashlib`, `fcntl` |
| Hooks / installer | Bash (POSIX-compatible) | `capture.sh` / `capture_cursor.sh` → `capture.py`. Avoid Bash 4+ features (macOS ships 3.2) |
| AI calls | `claude` CLI or Cursor `agent` CLI | Claude: `haiku` / `sonnet`. Cursor: `cursor_models.fast` / `cursor_models.strong` (defaults: `composer-2.5[fast=false]`, `claude-4.6-sonnet-medium`). All via `lib/agent_runner.py`. |
| MCP server | Python stdio, JSON-RPC 2.0 | Protocol version `2025-03-26`. Tools only, no resources/prompts |
| Storage | SQLite (stdlib `sqlite3`) + flat files | `prism.db` = observations + sessions + `observations_fts` (FTS5); `index.json` = engram index; Markdown engrams |
| Registry API | Cloudflare Worker (TypeScript) | Wrangler 4.x, Node 22 LTS — for registry maintainers only, not end users |
| Registry backend | GitHub repo | Versioning, PRs, CI, and hosting for free. No database needed |

### IDE integration points

Prism supports **Claude Code and Cursor**; `prism init` configures both (unused IDE integration is inert until you use that IDE).

| Integration | Claude Code | Cursor |
|-------------|-------------|--------|
| Hook (observe) | `.claude/settings.local.json` → `PreToolUse`, runs `capture.sh pre` (sets `PRISM_SOURCE=claude_code`) | `.cursor/hooks.json` → `preToolUse`, runs `capture_cursor.sh pre` (sets `PRISM_SOURCE=cursor`) |
| MCP (query) | `~/.claude.json` → `projects[cwd].mcpServers.prism` | `~/.cursor/mcp.json` → `mcpServers.prism` |
| Skills | `.claude/skills/` symlinks → `~/.prism/skills/` | `.cursor/rules/` |
| Context push | `.claude/prism.md` | `.cursor/rules/prism.mdc` |

**Extraction backend** (`agent_backend: auto`): `--backend` flag → `PRISM_AGENT_BACKEND` → `config.agent_backend` → `PRISM_SOURCE` → unanimous pending observation source → `mixed_backend_preference` when mixed → `claude`. Hook auto-extract passes `--backend` from `PRISM_SOURCE` (`trigger.py`). Manual `prism extract` on mixed pending prefers `mixed_backend_preference` when both CLIs are installed.

Shared rules: hooks are `preToolUse`-only (one observation per tool call) and exit 0 always; hook scripts prepend `~/.local/bin` and `~/.cursor/bin` to PATH so background `prism extract` → `agent`/`claude` resolves from GUI-launched IDEs; MCP is a stdio JSON-RPC subprocess (flush stdout after every write); context files are written by `prism sync` and read as project instructions.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

- **Project ID** is SHA256[:12] of git remote URL (portable) or repo root path (fallback). Never hardcode it.
- **Index writes** (`index.json`) use `fcntl.flock` + atomic `os.rename` (write to `.tmp`, rename). A `.bak` is kept. Stale locks > 10 min are auto-broken.
- **Observations** are written to SQLite (`prism.db`) via `storage.insert_observation()`. The `observations_fts` (FTS5) virtual table is kept in sync by triggers. (Legacy per-project `observations.jsonl` was migrated to SQLite; `.migrated.*` leftovers may remain on disk.)
- **Engram IDs** are kebab-case slugs derived from trigger text, max 60 chars.
- **Frontmatter** is hand-parsed: split on `---` delimiters, parse `key: value` lines. No PyYAML.
- **Secret scrubbing** runs before any observation is persisted. Baseline patterns are hardcoded and cannot be disabled.
- **Extraction lock**: `.extracting` file in `~/.prism/`. Lock > 10 min old = stale, auto-cleared.
- **Observation `source`** — `claude_code` or `cursor` from hook env (`PRISM_SOURCE`); `session_import` / `cursor_transcript` from transcript mining.
- **Extraction backend** — `lib/agent_runner.resolve_backend()`: override → env → config → `PRISM_SOURCE` → pending-source classification (`classify_pending_sources`) → default `claude`. Config keys: `agent_backend`, `mixed_backend_preference`, `cursor_models`.
- **`capture.py`**: runs on every tool call — keep it fast. Imports stay within stdlib + `lib` internals (`observation_summary` → scrub/compress/truncate, `storage` → SQLite insert, `project`, `trigger`).
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## File Layout

```
~/.prism/                          # Runtime home (created by install.sh)
  prism                            # CLI entry point
  config.json                      # User config (thresholds, agent_backend, cursor_models, decay, registry URL)
  constitution.md                  # Safety principles — never overwritten on upgrade
  prism.db                         # SQLite: observations + sessions + observations_fts (FTS5)
  index.json                       # Master engram index (all projects + global); .bak + .lock alongside
  lib/
    cli.py                         # Command router (argparse)
    commands.py                    # Command implementations (init, status, extract, review, learn, forget, sync, promote, registry, ...)
    capture.py                     # Observation processor — runs on every PreToolUse / Cursor preToolUse
    storage.py                     # SQLite storage layer (init_db, insert_observation, FTS search)
    schema.py                      # SQLite schema + migrations (sessions, observations, observations_fts)
    observation_summary.py         # Scrub → compress → truncate tool input before storage
    compress.py / expand.py        # Lexicon-based summary compression / re-expansion
    lexicon.py (+ lexicon.json)    # Abbreviation/expansion tables for compression
    text_tokenize.py               # Code/path/url-aware tokenizer (protects spans from compression)
    extract.py                     # Two-phase extraction pipeline (fast → strong)
    agent_runner.py                # IDE CLI backend resolution + subprocess (claude / agent)
    review.py                      # Session transcript review (background)
    sessions.py                    # Session transcript import + analysis (Claude Code + Cursor JSONL)
    search.py                      # FTS5 search over prism.db observations
    sync.py                        # Writes .claude/prism.md + .cursor/rules/prism.mdc from index
    mcp_server.py                  # MCP stdio server (prism_search, prism_get, prism_relevant, prism_record)
    dashboard.py (+ dashboard.html)# Local web dashboard (`prism dashboard`) — stdlib http.server, reads ~/.prism read-only
    index.py                       # Engram index load/save/lock/query (index.json)
    frontmatter.py                 # Sync engram Markdown YAML frontmatter to index.json
    config.py                      # Config management + PRISM_HOME resolution
    project.py                     # Project ID detection (git remote → path → global)
    trigger.py                     # Auto-extract spawn (passes --backend from PRISM_SOURCE)
    bridge.py                      # Engram → skill promotion (prism promote)
    registry.py                    # Registry add/remove/list/publish
    scrub.py                       # Secret scrubbing + adversarial prompt detection
    version_check.py               # Daily installed-vs-remote commit check
  hooks/
    capture.sh                     # Claude Code PreToolUse hook (PRISM_SOURCE=claude_code)
    capture_cursor.sh              # Cursor preToolUse hook (PRISM_SOURCE=cursor)
  agents/
    extractor.md                   # Phase 1 prompt (fast tier)
    validator.md                   # Phase 2 prompt (strong tier)
    reviewer.md                    # Session review prompt (fast tier)
  skills/                          # 12 slash commands (+ _shared helpers) symlinked into IDE skill dirs by prism init
  global/engrams/                  # Global-scope engrams (shared across projects)
  projects/<id>/                   # Per-project data
    project.json                   # Project metadata (path, remote)
    engrams/                       # Active engrams (Markdown + YAML frontmatter)
    candidates/                    # Pending extraction candidates
  archive/                         # Decayed engrams (recoverable)

<project>/
  .claude/
    settings.local.json            # Hook config — PreToolUse (written by prism init, gitignored)
    prism.md                       # Active engrams injected as project instructions (gitignored)
    skills/                        # Symlinks to ~/.prism/skills/ (gitignored)
    .prism_project_id              # Cached project ID for hook performance (gitignored)
  .cursor/
    hooks.json                     # Cursor preToolUse hook (written by prism init)
    rules/prism.mdc                # Active engrams as Cursor rules (written by prism sync)
```

> MCP servers are registered user-level, not per-project: Claude Code in `~/.claude.json`, Cursor in `~/.cursor/mcp.json`.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Slash Commands (12 total)

| Command | Description |
|---------|-------------|
| `/analyze-agent-codebase` | Deep architectural analysis across 6 clusters |
| `/mine-history` | Extract incident patterns from git history |
| `/mine-design` | Extract design decisions from source code |
| `/extract-skills` | Convert codebase analysis reports into skills |
| `/synthesize` | Promote incident clusters into publishable skills |
| `/synthesize-decisions` | Convert design decisions into skills |
| `/curate-skills` | Quality review: dedup, rewrite, remove |
| `/publish-skills` | Publish to registry with delta tracking |
| `/advise-skills` | Query registry for skills matching a question |
| `/audit-code` | Surface registry skills relevant to current codebase |
| `/run-analysis-pipeline` | Orchestrated: analyze → extract → curate → publish |
| `/run-history-pipeline` | Orchestrated: mine-history → synthesize → publish |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Use a GSD command for **complex tasks** — multi-step work, anything spanning several files, or changes that benefit from planning artifacts and execution context staying in sync.

Use these entry points:
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work
- `/gsd-quick` for smaller scoped tasks that still warrant a tracked workflow

**Simple tasks** — one-line edits, small fixes, doc tweaks, and ad-hoc changes — can be executed directly without a GSD workflow.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
