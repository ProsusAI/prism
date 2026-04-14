# Stack Research

**Domain:** CLI-driven knowledge layer for AI coding assistants (Claude Code integration)
**Researched:** 2026-04-14
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python 3.12+ | 3.12 - 3.14 | Library, CLI, MCP server, extraction pipeline | Zero-dependency constraint from Engram. stdlib-only (`json`, `argparse`, `pathlib`, `re`, `subprocess`, `datetime`). 3.12 is minimum floor for broad macOS/Linux availability; 3.14 is current stable. No need to pin tightly -- any 3.12+ works. |
| Bash (POSIX-ish) | 5.x | Hooks (`capture.sh`), installer (`install.sh`), CLI wrapper script | Shell hooks must never block Claude Code (exit 0, background spawns). Bash is universally available on macOS/Linux. Carried from Engram. |
| TypeScript | 5.x | Cloudflare Worker (registry API) | Cloudflare Workers runtime is TypeScript-native. Lens Worker already uses TS. Type-checked at build time, zero runtime overhead. |
| Node.js | 22 LTS | Wrangler dev/deploy toolchain for Workers | Node 22 is Active LTS through April 2027. Required only for Worker development, not for Prism end users. |
| Claude CLI | latest | AI model calls (`claude --print -p ... --model haiku/sonnet`) | The `claude` CLI is the sole interface for AI model calls. Used by extraction pipeline (Haiku proposes, Sonnet validates) and session reviewer. Not a library dependency -- a runtime tool dependency. |

### Claude Code Integration Points

| Integration | Mechanism | Configuration Location | Notes |
|-------------|-----------|----------------------|-------|
| Hooks (observation) | `PreToolUse` / `PostToolUse` command hooks | `~/.claude/settings.json` or `.claude/settings.json` | Hook receives JSON on stdin with `tool_name`, `tool_input`, `session_id`. Must exit 0 always. Background spawns for extraction/review. |
| MCP Server (knowledge pull) | stdio transport, JSON-RPC 2.0 | `.mcp.json` or `claude mcp add` | Python process, protocol version `2025-03-26`. Tools: `prism_search`, `prism_get`, `prism_relevant`, `prism_record`. Critical: Python stdout buffering must be handled (flush after every write). |
| Slash Commands (skills) | `.claude/skills/<name>/SKILL.md` | Project `.claude/skills/` directory | Legacy `.claude/commands/` format still works but `.claude/skills/` is the current standard (merged in Claude Code 2.1.3). SKILL.md contains instructions, optional supporting files alongside. |
| Context Injection (push) | `.claude/prism.md` file | Project root `.claude/` directory | Priority-ordered engrams written by `prism sync`. Claude Code reads this as project instructions. |

### MCP Protocol Details

| Aspect | Value | Notes |
|--------|-------|-------|
| Protocol Version | `2025-03-26` | Current version used by Engram. Claude Code supports this. The 2025-11-25 spec adds tasks/sampling but Prism does not need those features. |
| Transport | stdio | Server launched as subprocess by Claude Code. No HTTP/SSE needed for local MCP. |
| Capabilities | `{"tools": {}}` | Prism only exposes tools, not resources or prompts. |
| Message Format | JSON-RPC 2.0, newline-delimited | One JSON object per line on stdin/stdout. No embedded newlines in messages. |
| Logging | stderr only | stdout is reserved for protocol messages. Any stray print to stdout corrupts the connection. |

### Cloudflare Worker (Registry API)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Wrangler | ^4.x (latest: 4.82.0) | Worker dev server, deployment, secret management | Cloudflare's official CLI. `wrangler dev` for local testing, `wrangler deploy` for production, `wrangler secret put` for tokens. Version 4.x is current mainline. |
| @cloudflare/workers-types | ^4.20260411.0 | TypeScript type definitions for Worker runtime | Auto-generated types matching Worker runtime. Date-stamped versioning. Always use latest. |
| Compatibility Date | `2026-04-01` | Worker runtime feature gating | Set to current date at project start. Cloudflare recommends keeping current for latest features. Update periodically and test. |

### Data Formats

| Format | Purpose | Why |
|--------|---------|-----|
| JSONL (`observations.jsonl`) | Observation log from hooks | Append-only, one JSON object per line. Easy to rotate/archive. No parsing of whole file needed. |
| JSON (`index.json`) | Engram index, config, registry cache | Structured data with atomic read/write. Python `json` module (stdlib). |
| Markdown with YAML frontmatter | Engram files, SKILL.md, constitution | Human-readable, parseable frontmatter for metadata. Custom parser (no PyYAML dependency) using simple `---` delimiter splitting. |
| JSON Schema (draft 2020-12) | `plugin.schema.json` for skill validation | Carried from Lens. Used by CI validation (`validate.py` with `jsonschema` library -- CI-only dependency, not runtime). |

### Supporting Tools (Development/CI Only)

| Tool | Purpose | When to Use |
|------|---------|-------------|
| ShellCheck | Static analysis for bash scripts | CI and pre-commit. Catches quoting issues, unsafe `cd`, missing error handling in `capture.sh` and `install.sh`. |
| shfmt | Shell script formatter | CI. Consistent formatting for all `.sh` files. |
| jq 1.8+ | JSON manipulation in shell scripts | Optional runtime dependency for hook scripts. Engram uses `python3 -c` instead (avoids jq dependency). Keep this pattern -- Python is already required. |
| jsonschema (Python) | JSON Schema validation | CI-only (`validate.py`). Not a runtime dependency. `pip install jsonschema` in CI. |
| gh CLI | GitHub API interactions | Used by `prism registry create` to create repos from template. Runtime dependency for registry management commands only. |

## Installation

```bash
# End user installation (zero dependencies beyond Python 3.12+ and Claude Code)
git clone <prism-repo> /tmp/prism && /tmp/prism/install.sh

# What install.sh does:
# 1. Creates ~/.prism/ tree (lib/, hooks/, agents/, skills/, global/engrams/, archive/)
# 2. Copies Python lib, shell hooks, agent prompts, slash commands, templates
# 3. Symlinks `prism` CLI wrapper to ~/.local/bin/prism
# 4. Preserves existing config.json, constitution.md, index.json (idempotent)

# Worker development (registry maintainers only)
cd registry-template/cloudflare_worker
npm install  # installs wrangler + @cloudflare/workers-types (devDependencies only)
npx wrangler dev  # local dev server
npx wrangler deploy  # production deployment
npx wrangler secret put GH_TOKEN  # set GitHub PAT
npx wrangler secret put REGISTRY_TOKENS  # set API keys
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Python `argparse` (stdlib) | Click / Typer | Never for Prism. Zero-dependency constraint rules out Click (external package). argparse is verbose but sufficient for Prism's flat command structure. |
| Custom YAML frontmatter parser | PyYAML | Never for Prism runtime. PyYAML is an external dependency. The custom parser (split on `---`, parse `key: value` lines) handles the simple frontmatter Prism uses. PyYAML acceptable in CI scripts only. |
| Python `json` (stdlib) for JSON | orjson / ujson | Never for Prism. Performance is irrelevant (index.json is small, JSONL files are processed line-by-line). External dependency not justified. |
| Raw JSON-RPC over stdio | `mcp` Python SDK | Not now. The official `mcp` Python SDK (PyPI) exists but adds a dependency. Engram's hand-rolled JSON-RPC handler is ~100 lines, handles the 4 methods Prism needs (`initialize`, `tools/list`, `tools/call`, `ping`), and works. Revisit only if MCP protocol changes require complex negotiation. |
| `subprocess.run(["claude", ...])` | Anthropic Python SDK | Never for Prism. The `claude` CLI handles auth, model routing, tool permissions, and billing. Using the SDK directly would require API key management, lose Claude Code's tool access, and add a dependency. |
| Cloudflare Worker (TypeScript) | AWS Lambda / Vercel Edge | Never for Prism. Carried from Lens. Workers have zero cold start, global edge deployment, built-in KV/secrets. The Worker is already written and working. |
| GitHub repo as registry backend | Dedicated database (Postgres, SQLite) | Never for Prism. GitHub provides versioning (git), review (PRs), CI (Actions), access control (tokens), and hosting (raw content) -- all for free. No database needed. |
| `python3 -c "..."` in shell hooks | jq | Avoid jq for Prism. Python is already a required dependency (for the lib). Using `python3 -c` for JSON parsing in shell hooks avoids requiring jq as an additional system dependency. |
| `.claude/skills/` directory | `.claude/commands/` directory | Only if supporting Claude Code < 2.1.3. The commands format still works but skills is the current standard and supports autonomous invocation. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Any Python package manager (pip/poetry/conda) for runtime | Prism's zero-dependency constraint is a core feature. Users should never need to `pip install` anything. Every runtime import must be from Python stdlib. | Python stdlib only. CI can use pip for dev tools (jsonschema, shellcheck). |
| FastAPI/Flask for MCP server | MCP over stdio is a subprocess, not an HTTP server. Adding a web framework is unnecessary weight and wrong transport. | Raw JSON-RPC on stdio (Engram's existing pattern). |
| Docker for distribution | Prism installs to `~/.prism/` via shell script. Docker adds complexity, prevents hook integration with the host Claude Code process, and breaks the "single install.sh" experience. | `install.sh` with file copies and symlinks. |
| Wrangler v3 | v3 is legacy. v4.x is current mainline with full TypeScript support and newer APIs. Lens was on `^3.99.0` which auto-resolves to v4 anyway. | Wrangler ^4.x explicitly. |
| MCP protocol version 2025-11-25 | Adds complexity (tasks, sampling) that Prism does not need. Claude Code's MCP client negotiates down gracefully, but targeting the newer spec means implementing more surface area for no benefit. | Protocol version `2025-03-26`. Sufficient for tools-only MCP server. |
| `os.system()` or `os.popen()` | Unsafe, no timeout control, no stderr capture. | `subprocess.run()` with `capture_output=True`, `text=True`, `timeout=N`. Already used throughout Engram. |
| YAML libraries (PyYAML, ruamel) | External dependencies. Prism's frontmatter is simple enough for hand-parsing. | Custom frontmatter parser (split `---` blocks, parse `key: value`). |
| SQLite for engram storage | Over-engineering for what is a flat-file knowledge base. Index.json + markdown files is simpler, human-editable, and grep-friendly. | JSON index + markdown files with frontmatter. |

## Stack Patterns by Variant

**Personal tier (offline, zero-config):**
- Python lib only: `argparse` CLI, JSON index, markdown engrams, JSONL observations
- Shell hooks: `capture.sh` in Claude Code PreToolUse/PostToolUse
- MCP server: stdio Python process
- Context push: `.claude/prism.md` generated by `prism sync`
- AI calls: `claude --print --model haiku` (extraction), `claude --print --model sonnet` (validation)
- No network, no registry, no tokens required

**Team tier (registry, requires config):**
- Everything from personal tier, plus:
- Slash commands in `.claude/skills/` for extraction pipelines and querying
- Registry API: Cloudflare Worker (TypeScript) proxying GitHub repo
- Auth: Bearer token for Worker API, GitHub PAT for Worker-to-GitHub
- Publishing: Worker creates branch + commit + PR via GitHub Git API
- Multi-registry: `~/.prism/registries.json` listing multiple Worker URLs
- Cache: 24h TTL on fetched `skill-registry.json`

**Registry maintainer (Worker development):**
- Node.js 22 LTS + Wrangler 4.x + TypeScript
- `wrangler dev` for local testing
- `wrangler deploy` for production
- GitHub Actions for CI validation (`validate.py` + `build_registry.py`)

## Version Compatibility

| Component | Compatible With | Notes |
|-----------|-----------------|-------|
| Python 3.12+ | macOS 13+, Ubuntu 22.04+, any Linux with Python 3.12 | macOS ships Python 3 via Xcode CLI tools. Most CI images have 3.12+. Python 3.11 likely works but untested -- don't officially support. |
| Bash 5.x | macOS (via Homebrew), Linux (default) | macOS ships Bash 3.2 (GPLv2). Hooks use `set -euo pipefail` and `$(...)` which work on 3.2+. Avoid Bash 4+ features (associative arrays, `${var,,}`) unless willing to require Homebrew bash. |
| Claude Code | Current (hooks + MCP + skills) | Hooks API is stable since early 2026. MCP stdio transport is stable. Skills directory format is stable since 2.1.3. |
| Wrangler 4.x | Node.js 18+ (22 LTS recommended) | Worker development only. End users never interact with Node.js. |
| MCP protocol 2025-03-26 | Claude Code, Cursor, VS Code Copilot | Widely supported. If Claude Code moves to 2025-11-25 exclusively, the server's `initialize` response will need updating (protocol negotiation is backward-compatible). |

## File System Layout

```
~/.prism/                          # PRISM_HOME
  config.json                      # User configuration (decay rates, thresholds, registry URLs)
  constitution.md                  # Safety principles (never overwritten by updates)
  index.json                       # Engram index (all engrams across all projects)
  registries.json                  # Multi-registry configuration [NEW in Prism]
  global/
    engrams/                       # Global-scope engrams (*.md with frontmatter)
  projects/
    <hash>/                        # Project-scoped data (hash of git remote or path)
      engrams/                     # Project-scope engrams
      candidates/                  # Staging area for extraction pipeline
      observations.jsonl           # Hook-captured observations (rotated after extraction)
      observations.archive/        # Rotated observation files
  archive/                         # Archived (decayed) engrams
  hooks/
    capture.sh                     # PreToolUse/PostToolUse hook
  agents/
    extractor.md                   # Haiku extraction prompt
    validator.md                   # Sonnet validation prompt
    reviewer.md                    # Session review prompt
  skills/                          # Slash commands (SKILL.md files)
  lib/
    *.py                           # Python library (config, index, extract, review, etc.)
    mcp_server.py                  # MCP server entry point
  cache/                           # Registry cache [NEW in Prism]
    <registry-hash>/
      skill-registry.json          # Cached registry with TTL metadata
  templates/
    constitution.md                # Default constitution
    worker/                        # Cloudflare Worker template [NEW in Prism]
      src/index.ts
      package.json
      wrangler.toml
```

## Sources

- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks) -- Complete hooks API (30+ events, handler types, stdin format) - HIGH confidence
- [Claude Code MCP Documentation](https://code.claude.com/docs/en/mcp) -- MCP server configuration, stdio transport - HIGH confidence
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills) -- Skill/slash command format - HIGH confidence
- [MCP Specification 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) -- Protocol spec for stdio transport - HIGH confidence
- [MCP Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) -- Latest spec (tasks, sampling -- not needed for Prism) - HIGH confidence
- [Cloudflare Workers Wrangler docs](https://developers.cloudflare.com/workers/wrangler/) -- Wrangler 4.x, compatibility dates - HIGH confidence
- [Cloudflare Workers Best Practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/) -- Compatibility date guidance - HIGH confidence
- [Python Releases](https://blog.python.org/2026/04/python-3150a8-3144-31313/) -- Python 3.14.4 current stable - HIGH confidence
- [Node.js Releases](https://nodejs.org/en/about/previous-releases) -- Node 22 LTS through April 2027 - HIGH confidence
- [ShellCheck](https://github.com/koalaman/shellcheck) -- Shell script linting - HIGH confidence
- Engram source code (`/Users/gaurav/codes/engram/`) -- Actual implementation patterns - HIGH confidence (primary source)
- Lens source code (`/Users/gaurav/codes/Lens/`) -- Worker implementation, skill format - HIGH confidence (primary source)

---
*Stack research for: CLI-driven knowledge layer for AI coding assistants*
*Researched: 2026-04-14*
