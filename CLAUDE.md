<!-- GSD:project-start source:PROJECT.md -->
## Project

**Prism** — knowledge layer for Claude Code. Two things:
1. **Personal learning**: hooks observe tool usage, an extraction pipeline (Haiku proposes, Sonnet validates) converts patterns into engrams (living, decaying knowledge), engrams flow back into Claude Code via `.claude/prism.md` and MCP tools.
2. **Team skills**: high-confidence engrams promote to skills published to a Cloudflare Worker-backed registry that teams query.

### Hard constraints

- **Zero runtime Python dependencies** — every import must be stdlib. No pip installs for end users.
- **Hooks never block Claude Code** — `capture.sh` must always exit 0; background spawns only.
- **AI calls via `claude` CLI only** — never import the Anthropic SDK. `subprocess.run(["claude", "--print", "--model", "haiku", ...])`.
- **No database** — flat files only: JSONL observations, JSON index, Markdown engrams with YAML frontmatter.
- **Custom YAML frontmatter parser** — never import PyYAML. Split on `---`, parse `key: value` lines.
- **`subprocess.run()` not `os.system()`** — always use `capture_output=True, text=True, timeout=N`.
- **MCP stdout is protocol-only** — any stray `print()` in lib code corrupts the JSON-RPC stream. All logging to stderr.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Library / CLI | Python 3.12+ (stdlib only) | `argparse`, `json`, `pathlib`, `subprocess`, `hashlib`, `fcntl` |
| Hooks / installer | Bash (POSIX-compatible) | `capture.sh` → `capture.py`. Avoid Bash 4+ features (macOS ships 3.2) |
| AI calls | `claude` CLI (Haiku + Sonnet) | Haiku for extraction proposals, Sonnet for validation |
| MCP server | Python stdio, JSON-RPC 2.0 | Protocol version `2025-03-26`. Tools only, no resources/prompts |
| Registry API | Cloudflare Worker (TypeScript) | Wrangler 4.x, Node 22 LTS — for registry maintainers only, not end users |
| Registry backend | GitHub repo | Versioning, PRs, CI, and hosting for free. No database needed |

### Claude Code integration points

| Integration | Config location | Key detail |
|-------------|----------------|------------|
| Hook (observe) | `.claude/settings.local.json` → `PreToolUse` | `capture.sh pre` — PreToolUse only, exit 0 always |
| MCP (query) | `.claude/settings.local.json` → `mcpServers.prism` | stdio subprocess, flush stdout after every write |
| Skills (slash commands) | `.claude/skills/` symlinks → `~/.prism/skills/` | SKILL.md format, set up by `prism init` |
| Context push | `.claude/prism.md` | Written by `prism sync`; read by Claude Code as project instructions |
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

- **Project ID** is SHA256[:12] of git remote URL (portable) or repo root path (fallback). Never hardcode it.
- **Index writes** use `fcntl.flock` + atomic `os.rename` (write to `.tmp`, rename). A `.bak` is kept. Stale locks > 10 min are auto-broken.
- **Observation appends** use `O_APPEND | O_WRONLY | O_CREAT` with a single `os.write()` call — atomic under POSIX PIPE_BUF (4096 bytes).
- **Engram IDs** are kebab-case slugs derived from trigger text, max 60 chars.
- **Frontmatter** is hand-parsed: split on `---` delimiters, parse `key: value` lines. No PyYAML.
- **Secret scrubbing** runs before any observation is written to disk. Baseline patterns are hardcoded and cannot be disabled.
- **Extraction lock**: `.extracting` file in `~/.prism/`. Lock > 10 min old = stale, auto-cleared.
- **`capture.py`**: runs on every tool call — keep it fast. No imports beyond stdlib + `lib/scrub`.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## File Layout

```
~/.prism/                          # Runtime home (created by install.sh)
  prism                            # CLI entry point
  config.json                      # User config (thresholds, decay, registry URL)
  constitution.md                  # Safety principles — never overwritten on upgrade
  index.json                       # Master engram index (all projects + global)
  lib/
    cli.py                         # Command router (argparse)
    commands.py                    # Command implementations (init, learn, forget, disable, uninstall, ...)
    capture.py                     # Observation processor — runs on every PreToolUse
    extract.py                     # Two-phase extraction pipeline (Haiku → Sonnet)
    review.py                      # Session transcript review (background)
    sessions.py                    # Session analysis + SQLite FTS5 search
    sync.py                        # Writes .claude/prism.md from index
    mcp_server.py                  # MCP stdio server (prism_search, prism_get, prism_relevant, prism_record)
    index.py                       # Index load/save/lock/query
    config.py                      # Config management + PRISM_HOME resolution
    project.py                     # Project ID detection (git remote → path → global)
    trigger.py                     # Auto-extraction threshold check (spawns background)
    bridge.py                      # Engram → skill promotion (prism promote)
    registry.py                    # Registry add/remove/list/publish
    search.py                      # SQLite FTS5 session search
    scrub.py                       # Secret scrubbing + adversarial prompt detection
  hooks/
    capture.sh                     # Claude Code PreToolUse hook
  agents/
    extractor.md                   # Phase 1 prompt (Haiku)
    validator.md                   # Phase 2 prompt (Sonnet)
    reviewer.md                    # Session review prompt
  skills/                          # 13 slash commands (symlinked into .claude/skills/ by prism init)
  global/engrams/                  # Global-scope engrams (shared across projects)
  projects/<id>/                   # Per-project data
    observations.jsonl
    engrams/
    candidates/
  archive/                         # Decayed engrams (recoverable)

<project>/.claude/
  settings.local.json              # Hook + MCP config (written by prism init, gitignored)
  prism.md                         # Active engrams injected as project instructions (gitignored)
  skills/                          # Symlinks to ~/.prism/skills/ (gitignored)
  .prism_project_id                # Cached project ID for hook performance (gitignored)
```
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Slash Commands (13 total)

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
| `/find-vulnerabilities` | Security-focused codebase audit |
| `/run-analysis-pipeline` | Orchestrated: analyze → extract → curate → publish |
| `/run-history-pipeline` | Orchestrated: mine-history → synthesize → publish |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
