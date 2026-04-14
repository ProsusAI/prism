# Phase 1: Foundation + Observation - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

User can install Prism, initialize any project for learning, and Claude Code tool usage flows into observation logs. Delivers: `install.sh`, `prism` CLI wrapper, `prism init`, `prism config`, `prism status`, `prism log`, and `capture.sh` hook with secret scrubbing. Extraction pipeline, engram management, and context injection are Phase 2.

</domain>

<decisions>
## Implementation Decisions

### Copy Fidelity
- **D-01:** Rename and ship — literal copy of Engram's `lib/*.py` with `engram`->`prism` renames in imports, paths, env vars (`ENGRAM_HOME`->`PRISM_HOME`). Drop `lib/team.py`, `lib/lens.py`, `hooks/cursor-capture.sh` per PROJECT.md.
- **D-02:** Keep Engram's flat `lib/*.py` file structure as-is. No restructuring into subdirectories.
- **D-03:** Fork and forget — Prism is the canonical codebase going forward. Engram becomes archived/read-only. No upstream merge strategy needed.

### Lens Timing
- **D-04:** Defer Lens slash commands to Phase 3. Phase 1 only copies Engram code (lib, hooks, agents, templates). Keeps the phase focused.

### Init Experience
- **D-05:** `prism init` merges carefully into existing `.claude/settings.local.json` — reads existing JSON, adds Prism hooks/MCP entries alongside existing ones. Never clobbers other tools' config. Warns if conflicts found.
- **D-06:** `prism init` is fully automatic, zero prompts. Detects project, configures everything, prints a concise summary (not too detailed, so users actually read it). Re-running is safe (idempotent).
- **D-07:** `install.sh` hard-fails on missing `python3` or `git` (non-negotiable). `claude` CLI is a soft warning — needed at runtime for extraction, not for install.

### Hook Architecture
- **D-08:** Fix hook performance in Phase 1 — collapse to a single `python3` invocation that receives JSON on stdin, handles scrubbing + JSONL append + trigger check. No multi-spawn pattern from Engram.
- **D-09:** Stdin pipe for data passing — shell reads Claude Code's JSON from stdin, pipes directly to Python. No temp files, no shell injection surface.
- **D-10:** Extraction trigger threshold is configurable from day one via `prism config extraction.threshold <N>`, defaulting to 15 (Engram's proven value).

### CLI Output Style
- **D-11:** Friendly with context personality — brief explanations alongside data (e.g., "3 engrams active (2 from this session)"). Think `gh` CLI. Color for emphasis (green=good, red=error, yellow=warning).
- **D-12:** `prism log` defaults to human-readable formatted table (timestamp, tool, summary). `--json` flag for raw JSONL output.
- **D-13:** `prism status` auto-detects project when run inside a git repo (shows that project's status). Outside a repo, shows global summary. `--project <id>` for explicit targeting.

### Claude's Discretion
- Lens slash command copy timing was deferred to Claude's judgment — decided to defer to Phase 3 for focus.
- Exact `prism init` summary format and content
- `install.sh` upgrade behavior for partial failures
- Color scheme specifics and table formatting details

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Engram source (primary copy source)
- `/Users/gaurav/codes/engram/install.sh` -- Installer to adapt (108 lines)
- `/Users/gaurav/codes/engram/lib/` -- All Python library files to copy and rename
- `/Users/gaurav/codes/engram/hooks/capture.sh` -- Hook to rewrite (collapse to single Python call)
- `/Users/gaurav/codes/engram/agents/` -- Extraction/review agent prompts to copy
- `/Users/gaurav/codes/engram/templates/` -- Templates to copy

### Prism design
- `unified-design.md` -- Complete design document with architecture, user stories, file layout, all commands
- `.planning/PROJECT.md` -- Key decisions (copy-and-modify, fork-and-forget, zero-dependency)
- `.planning/REQUIREMENTS.md` -- SETUP-01 through SETUP-14, OBS-01 through OBS-08

### Research findings
- `.planning/research/` -- Pre-roadmap research with performance, security, and compatibility findings

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Engram `lib/cli.py` + `lib/commands.py`: argparse-based CLI with subcommands — adapt for `prism` CLI wrapper
- Engram `lib/config.py`: config management with JSON read/write — adapt for `prism config`
- Engram `lib/project.py`: project detection via git remote SHA256[:12] — reuse directly
- Engram `lib/scrub.py`: secret scrubbing patterns (API keys, tokens, bearer, sk-*, ghp-*) — reuse directly
- Engram `lib/index.py`: master engram index with CRUD — reuse directly
- Engram `lib/sync.py`: `.claude/prism.md` generation with priority ordering — reuse directly

### Established Patterns
- Python stdlib only (json, argparse, pathlib, re, subprocess, datetime) — zero-dependency constraint
- JSONL for observation logs (append-only, line-by-line processing)
- JSON for config and index (atomic read/write)
- Markdown with YAML frontmatter for engrams (custom parser, no PyYAML)
- `subprocess.run()` with `capture_output=True, text=True, timeout=N` for external calls

### Integration Points
- Claude Code hooks: PreToolUse + PostToolUse in `.claude/settings.local.json`
- MCP server: stdio transport registered in `.claude/settings.local.json`
- Slash commands: symlinks from `.claude/skills/` to `~/.prism/skills/`
- Context push: `.claude/prism.md` in project root `.claude/` directory
- CLI wrapper: `~/.local/bin/prism` symlink

</code_context>

<specifics>
## Specific Ideas

- `prism init` summary should be concise enough that users actually read it — not a wall of text
- CLI personality inspired by `gh` CLI — friendly, contextual, not robotic
- Hook performance fix is a priority even though it's a deviation from pure "rename and ship" — the research flagged it and we're touching the code anyway

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation-observation*
*Context gathered: 2026-04-14*
