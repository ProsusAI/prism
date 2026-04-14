# Phase 1: Foundation + Observation - Research

**Researched:** 2026-04-14
**Domain:** Shell installer, Python CLI/library, Claude Code hook integration, observation capture
**Confidence:** HIGH

## Summary

Phase 1 is a copy-and-adapt phase: take Engram's existing Python library, shell hooks, agent prompts, and templates, rename `engram` to `prism` throughout, and fix critical issues identified in the pre-roadmap pitfalls research. The codebase being copied is well-understood (HIGH confidence) because we have full access to every source file.

The key deviations from pure "rename and ship" are: (1) rewriting `capture.sh` to collapse three `python3 -c` invocations into a single Python process that reads stdin, addressing both shell injection and performance pitfalls; (2) switching from `.claude/settings.json` to `.claude/settings.local.json` for hook/MCP registration per the design document; (3) adding atomic writes + backup for `index.json`; and (4) dropping `cursor-capture.sh`, `team.py`, `lens.py` per PROJECT.md decisions. Lens slash commands are deferred to Phase 3 (decision D-04).

**Primary recommendation:** Copy all Engram `lib/*.py` files (minus `team.py`, `lens.py`) with `engram`->`prism` renames, rewrite `capture.sh` as a thin shell wrapper around a single `python3` call, adapt `install.sh` for `~/.prism/` tree, and write `prism init` to configure `.claude/settings.local.json`. Every file must pass a zero-match grep for `engram`/`ENGRAM`/`Engram` after rename.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Rename and ship -- literal copy of Engram's `lib/*.py` with `engram`->`prism` renames in imports, paths, env vars (`ENGRAM_HOME`->`PRISM_HOME`). Drop `lib/team.py`, `lib/lens.py`, `hooks/cursor-capture.sh` per PROJECT.md.
- **D-02:** Keep Engram's flat `lib/*.py` file structure as-is. No restructuring into subdirectories.
- **D-03:** Fork and forget -- Prism is the canonical codebase going forward. Engram becomes archived/read-only. No upstream merge strategy needed.
- **D-04:** Defer Lens slash commands to Phase 3. Phase 1 only copies Engram code (lib, hooks, agents, templates). Keeps the phase focused.
- **D-05:** `prism init` merges carefully into existing `.claude/settings.local.json` -- reads existing JSON, adds Prism hooks/MCP entries alongside existing ones. Never clobbers other tools' config. Warns if conflicts found.
- **D-06:** `prism init` is fully automatic, zero prompts. Detects project, configures everything, prints a concise summary (not too detailed, so users actually read it). Re-running is safe (idempotent).
- **D-07:** `install.sh` hard-fails on missing `python3` or `git` (non-negotiable). `claude` CLI is a soft warning -- needed at runtime for extraction, not for install.
- **D-08:** Fix hook performance in Phase 1 -- collapse to a single `python3` invocation that receives JSON on stdin, handles scrubbing + JSONL append + trigger check. No multi-spawn pattern from Engram.
- **D-09:** Stdin pipe for data passing -- shell reads Claude Code's JSON from stdin, pipes directly to Python. No temp files, no shell injection surface.
- **D-10:** Extraction trigger threshold is configurable from day one via `prism config extraction.threshold <N>`, defaulting to 15 (Engram's proven value).
- **D-11:** Friendly with context personality -- brief explanations alongside data (e.g., "3 engrams active (2 from this session)"). Think `gh` CLI. Color for emphasis (green=good, red=error, yellow=warning).
- **D-12:** `prism log` defaults to human-readable formatted table (timestamp, tool, summary). `--json` flag for raw JSONL output.
- **D-13:** `prism status` auto-detects project when run inside a git repo (shows that project's status). Outside a repo, shows global summary. `--project <id>` for explicit targeting.

### Claude's Discretion
- Exact `prism init` summary format and content
- `install.sh` upgrade behavior for partial failures
- Color scheme specifics and table formatting details

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SETUP-01 | `install.sh` creates `~/.prism/` tree (lib, agents, hooks, skills, global/engrams, archive) and copies all components | Engram `install.sh` (108 lines) is the direct template. Adapt directory names, drop cursor-capture.sh and lens-skills copy |
| SETUP-02 | `install.sh` creates CLI wrapper at `~/.local/bin/prism` | Engram uses `ln -sf` for symlink. Prism should use same pattern but symlink to installed `~/.prism/prism` wrapper, not repo path |
| SETUP-03 | `install.sh` writes default `config.json` and empty `index.json` | Engram pattern: heredoc for config.json, echo for index.json, both with if-not-exists guards |
| SETUP-04 | `install.sh` copies `constitution.md` template (only if not exists) | Engram pattern: `if [ ! -f ... ]; then cp ...; fi` |
| SETUP-05 | `install.sh` is idempotent -- re-running updates lib/agents/hooks but preserves config, index, constitution, project data | Engram pattern: unconditional `cp` for lib/hooks/agents, conditional for config/constitution/index |
| SETUP-06 | `install.sh` checks prerequisites (python3, git, claude) before proceeding | Decision D-07: hard-fail on python3/git, soft-warn on claude |
| SETUP-07 | `install.sh` works from both `curl \| bash` (public) and `git clone` (private repo) paths | Design doc specifies dual-path detection. For now, clone path only (repo is private) |
| SETUP-08 | `prism init` detects project ID from git remote (SHA256[:12] of origin URL) | Engram `lib/project.py` provides `detect_project_id()` -- copy and rename |
| SETUP-09 | `prism init` configures hooks in `.claude/settings.local.json` (PreToolUse + PostToolUse) | Claude Code hooks API verified: uses `settings.local.json` for project-scoped, gitignored config. Hook format documented in detail |
| SETUP-10 | `prism init` registers MCP server in `.claude/settings.local.json` | MCP config goes in same settings file as hooks. `mcpServers` key with `command`, `args`, `env` |
| SETUP-11 | `prism init` symlinks slash commands from `~/.prism/skills/` to `.claude/skills/` | Deferred to Phase 3 (D-04) -- but the symlink mechanism should be scaffolded (no-op if `~/.prism/skills/` is empty) |
| SETUP-12 | `prism init` adds `.claude/skills/`, `.claude/prism.md`, `.claude/settings.local.json` to `.gitignore` | Standard gitignore append with duplicate check |
| SETUP-13 | `prism init` generates initial `.claude/prism.md` (push layer) | Engram `lib/sync.py` provides `sync_claude_code()`. Initially sparse -- no engrams yet |
| SETUP-14 | `prism config [key] [value]` gets/sets configuration values | Engram `lib/cli.py::_cmd_config()` + `lib/config.py` -- copy and rename |
| OBS-01 | `capture.sh` hook receives JSON on stdin (`tool_name`, `tool_input`, `session_id`) from PreToolUse/PostToolUse | Claude Code hooks API confirmed: stdin JSON includes `session_id`, `tool_name`, `tool_input`, `transcript_path`, `cwd`, `hook_event_name` |
| OBS-02 | `capture.sh` scrubs secrets before writing (API keys, tokens, bearer, sk-*, ghp-*) | Engram `lib/scrub.py` provides `scrub_text()` with configurable patterns. Expand patterns per pitfalls research |
| OBS-03 | `capture.sh` truncates `input_summary` to 500 chars | Engram `lib/scrub.py::truncate()` handles this |
| OBS-04 | `capture.sh` appends JSONL line to `~/.prism/projects/<hash>/observations.jsonl` | Rewrite to use `os.open(O_WRONLY \| O_APPEND \| O_CREAT)` + `os.write()` for atomic append |
| OBS-05 | `capture.sh` never blocks Claude Code (exit 0 always, background spawns) | Use `async: true` in hook config for PostToolUse. Shell wrapper always exits 0 |
| OBS-06 | `capture.sh` spawns background extraction at 15 observations | Engram `trigger.py::maybe_trigger_extraction()` provides the logic |
| OBS-07 | `capture.sh` spawns background session review every 5 observations | Engram `capture.sh` lines 114-121 provide the pattern |
| OBS-08 | `prism log [--last N] [--insights]` shows recent observations | Engram `lib/commands.py::cmd_log()` -- copy, rename, add `--json` flag per D-12 |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python 3 (stdlib only) | 3.9+ (see note) | All library code, CLI, MCP server, capture processor | Zero-dependency constraint. Stdlib modules: `json`, `argparse`, `pathlib`, `re`, `subprocess`, `datetime`, `hashlib`, `os`, `sys`, `fcntl` |
| Bash (POSIX-ish) | 3.2+ | `install.sh`, `capture.sh` wrapper, CLI wrapper | Must work on macOS default Bash 3.2. Avoid Bash 4+ features (associative arrays, `${var,,}` case folding) |
| Claude Code Hooks API | Current (2026) | PreToolUse + PostToolUse integration | Stable API since early 2026. Async mode supported for non-blocking capture |

**CRITICAL: Python version note.** The system Python on this macOS machine is 3.9.6 (`/usr/bin/python3`). No Python 3.12+ is installed. [VERIFIED: `python3 --version` returned 3.9.6, no python3.12/3.13/3.14 found] CLAUDE.md specifies Python 3.12+ as minimum. However, the Engram codebase uses only stdlib features available since Python 3.6+ (no `match` statements, no `TypeAlias`, no `tomllib`). The only 3.12+ feature mentioned in CLAUDE.md is availability, not syntax. **Recommendation: Target Python 3.9+ for actual compatibility (the code will work), but document 3.12+ as the officially supported floor per CLAUDE.md. Do not use any Python 3.10+ syntax features (no `match`, no `X | Y` union types in annotations).** [ASSUMED -- user should confirm minimum Python version]

**CRITICAL: Bash version note.** macOS ships Bash 3.2.57. [VERIFIED: `bash --version` returned 3.2.57] The Engram codebase uses `set -euo pipefail` and `$(...)` which work on 3.2+. Must avoid Bash 4+ features: no associative arrays, no `${var,,}`, no `|&` redirection, no `coproc`.

### Supporting (Phase 1 only)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `fcntl` (stdlib) | N/A | File locking for `index.json` writes | Every index mutation to prevent corruption |
| `hashlib` (stdlib) | N/A | SHA256 for project ID detection | `detect_project_id()` -- portable alternative to `shasum` CLI |
| `shutil` (stdlib) | N/A | File copy operations | `install.sh` equivalent operations in Python, engram archival |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `argparse` (stdlib) | Click / Typer | Never -- zero-dependency constraint [VERIFIED: CLAUDE.md] |
| Custom frontmatter parser | PyYAML | Never for runtime -- external dependency [VERIFIED: CLAUDE.md] |
| `python3 -c` in shell hooks | jq | Avoid -- Python is already required, adding jq is unnecessary [VERIFIED: CLAUDE.md] |
| Hand-rolled JSON-RPC MCP | `mcp` Python SDK | Not now -- SDK adds dependency, Engram's ~100 line handler works [VERIFIED: CLAUDE.md] |

**Installation:**
```bash
# No packages to install -- Python stdlib only
# The installer copies files from the repo to ~/.prism/
./install.sh
```

## Architecture Patterns

### Recommended Project Structure (in repo)
```
prism/
├── install.sh               # Shell installer -> ~/.prism/
├── prism                     # CLI wrapper (Python, copies to ~/.prism/prism)
├── lib/
│   ├── __init__.py           # Empty
│   ├── cli.py                # Command router (argparse)
│   ├── commands.py           # init, status, learn, correct, forget, maintain, log, procedures
│   ├── config.py             # Config management, path helpers, defaults
│   ├── index.py              # Engram index CRUD (with atomic writes + flock)
│   ├── project.py            # Project detection (git remote SHA256[:12])
│   ├── scrub.py              # Secret scrubbing + truncation
│   ├── sync.py               # Generate .claude/prism.md (push layer)
│   ├── mcp_server.py         # MCP tools (search, get, relevant, record)
│   ├── extract.py            # Haiku -> Sonnet pipeline (copied, not active until Phase 2)
│   ├── review.py             # Session review (copied, not active until Phase 2)
│   ├── sessions.py           # Bootstrap from transcripts (copied, not active until Phase 2)
│   └── trigger.py            # Auto-extraction trigger
├── hooks/
│   └── capture.sh            # Thin shell wrapper -> single python3 call
├── agents/
│   ├── extractor.md          # Haiku extraction prompt
│   ├── validator.md          # Sonnet validation prompt
│   └── reviewer.md           # Session review prompt
└── templates/
    └── constitution.md       # Safety principles template
```

### Installed Layout (`~/.prism/`)
```
~/.prism/
├── config.json               # User config (preserved on upgrade)
├── constitution.md           # Safety principles (preserved on upgrade)
├── index.json                # Master engram index (preserved on upgrade)
├── lib/                      # Python library (overwritten on upgrade)
│   ├── __init__.py
│   ├── cli.py
│   ├── commands.py
│   ├── config.py
│   ├── index.py
│   ├── project.py
│   ├── scrub.py
│   ├── sync.py
│   ├── mcp_server.py
│   ├── extract.py
│   ├── review.py
│   ├── sessions.py
│   └── trigger.py
├── hooks/
│   └── capture.sh            # Overwritten on upgrade
├── agents/                   # Overwritten on upgrade
│   ├── extractor.md
│   ├── validator.md
│   └── reviewer.md
├── skills/                   # Empty in Phase 1 (populated in Phase 3)
├── global/engrams/           # Global engrams
├── archive/                  # Decayed/forgotten engrams
├── prism                     # CLI wrapper script
└── projects/<hash12>/        # Per-project data
    ├── project.json
    ├── observations.jsonl
    ├── observations.archive/
    ├── engrams/
    └── candidates/
```

### Pattern 1: Capture Hook Architecture (Phase 1 Rewrite)
**What:** Replace Engram's multi-`python3 -c` capture.sh with a thin shell wrapper piping stdin to a single Python process.
**When to use:** Every PreToolUse and PostToolUse event from Claude Code.
**Example:**
```bash
#!/usr/bin/env bash
# capture.sh - thin wrapper, all logic in Python
# Source: Design decision D-08, D-09

set -euo pipefail

PRISM_HOME="${PRISM_HOME:-$HOME/.prism}"
PHASE="${1:-pre}"

# Guard: don't capture during extraction
[ -f "$PRISM_HOME/.extracting" ] && exit 0

# Pipe stdin directly to Python - single invocation, no shell variable interpolation
exec python3 "$PRISM_HOME/lib/capture.py" "$PHASE" 2>/dev/null

# If Python fails for any reason, exit 0 (never block Claude Code)
exit 0
```

The companion `lib/capture.py` reads JSON from stdin, processes entirely in Python:
```python
# Source: Engram capture.sh rewrite per D-08, D-09
import json, sys, os, re
from datetime import datetime, timezone
from pathlib import Path

def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "pre"
    prism_home = Path(os.environ.get("PRISM_HOME", os.path.expanduser("~/.prism")))
    
    raw = sys.stdin.read()
    if not raw:
        return
    
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    
    tool_name = data.get("tool_name", "")
    session_id = data.get("session_id", "")
    tool_input = data.get("tool_input", {})
    
    # Detect project ID (cached or computed)
    project_id = _detect_project_id(prism_home)
    project_dir = prism_home / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # Build input summary with scrubbing + truncation
    summary = _build_summary(tool_input)
    summary = _scrub(summary)
    summary = summary[:500]
    
    # Build observation
    obs = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": "tool_start" if phase == "pre" else "tool_end",
        "tool": tool_name,
        "input_summary": summary,
        "session": session_id,
        "project_id": project_id,
        "source": "claude_code",
    }
    
    # Atomic append (O_APPEND + single write)
    line = json.dumps(obs, ensure_ascii=False) + "\n"
    obs_path = str(project_dir / "observations.jsonl")
    fd = os.open(obs_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    
    # Trigger checks (background spawns)
    _maybe_trigger(prism_home, project_id, obs_path, session_id)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # Never crash, never block
```

### Pattern 2: Careful JSON Merge for settings.local.json
**What:** `prism init` reads existing `.claude/settings.local.json`, merges Prism's hook and MCP entries without clobbering other tools' config.
**When to use:** Every `prism init` invocation.
**Example:**
```python
# Source: Engram commands.py _setup_claude_code_hooks() adapted for settings.local.json
def _setup_hooks_and_mcp(project_id: str) -> None:
    settings_path = Path.cwd() / ".claude" / "settings.local.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    
    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    
    # Merge hooks (don't duplicate)
    hooks = existing.get("hooks", {})
    capture_cmd = str(Path.home() / ".prism" / "hooks" / "capture.sh")
    
    for event, phase_arg in [("PreToolUse", "pre"), ("PostToolUse", "post")]:
        hook_entry = {
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": f"{capture_cmd} {phase_arg}",
            }],
        }
        # For PostToolUse, use async mode
        if event == "PostToolUse":
            hook_entry["hooks"][0]["async"] = True
        
        if event not in hooks:
            hooks[event] = [hook_entry]
        else:
            # Check for existing Prism hook
            existing_cmds = set()
            for mg in hooks[event]:
                for h in mg.get("hooks", []):
                    existing_cmds.add(h.get("command", ""))
            if hook_entry["hooks"][0]["command"] not in existing_cmds:
                hooks[event].append(hook_entry)
    
    existing["hooks"] = hooks
    
    # Register MCP server
    mcp_servers = existing.get("mcpServers", {})
    mcp_servers["prism"] = {
        "command": "python3",
        "args": [str(Path.home() / ".prism" / "lib" / "mcp_server.py")],
        "env": {"PRISM_PROJECT": project_id},
    }
    existing["mcpServers"] = mcp_servers
    
    settings_path.write_text(json.dumps(existing, indent=2) + "\n")
```

### Pattern 3: Atomic Index Writes with Backup
**What:** Every `index.json` mutation uses file locking, writes to a temp file, then atomic rename.
**When to use:** All `save_index()` calls.
**Example:**
```python
# Source: Pitfall #6 prevention (index.json corruption)
import fcntl, os, json, shutil
from pathlib import Path

def save_index(index: dict) -> None:
    path = PRISM_HOME / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Backup existing index
    if path.exists():
        backup = path.with_suffix(".json.bak")
        try:
            shutil.copy2(str(path), str(backup))
        except OSError:
            pass
    
    # Write to temp, then atomic rename
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            json.dump(index, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    os.rename(str(tmp), str(path))  # Atomic on POSIX
```

### Pattern 4: CLI Wrapper Script
**What:** A Python script that sets up sys.path and delegates to `lib/cli.py`.
**When to use:** The `prism` command entry point.
**Example:**
```python
#!/usr/bin/env python3
"""Prism - knowledge layer for Claude Code."""
# Source: Engram CLI wrapper adapted
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.cli import main

if __name__ == "__main__":
    main()
```

### Anti-Patterns to Avoid
- **Shell variable interpolation into Python strings:** Never embed `$INPUT_SUMMARY` into a `python3 -c` script. Pipe data through stdin instead. [Source: Pitfalls research, Pitfall #1]
- **Multiple `python3 -c` invocations in hooks:** Each Python cold start is 80-150ms. Use one process for all logic. [Source: Pitfalls research, Pitfall #2]
- **Writing to `.claude/settings.json` (committed):** Use `.claude/settings.local.json` (gitignored) for machine-specific paths. [Source: Design document, verified in Claude Code docs]
- **Using `print()` in MCP server code:** Stdout is reserved for JSON-RPC messages. All logging to `sys.stderr`. [Source: Pitfalls research, Pitfall #9]
- **Non-atomic `index.json` writes:** Always write-to-temp + rename. [Source: Pitfalls research, Pitfall #6]
- **Bash 4+ features:** No associative arrays, no `${var,,}`, macOS default is Bash 3.2. [VERIFIED: Bash 3.2.57 on this machine]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON parsing in shell | `grep`/`awk`/`sed` on JSON | `python3 -c "import json..."` or pipe to Python process | JSON edge cases (nested quotes, unicode escapes) break regex |
| Secret pattern matching | Simple string search | Regex patterns from `config.py` with `re.sub()` | Patterns must handle case-insensitive matching, variable formats |
| File locking | Custom lock files only | `fcntl.flock()` + backup + atomic rename | OS-level locks are more reliable than advisory lock files alone |
| Project ID generation | Shell `shasum` piping | Python `hashlib.sha256()` | Portable (no `shasum` vs `sha256sum` platform difference) |
| YAML frontmatter parsing | Full YAML parser | Custom strict-subset parser (split on `---`, parse `key: value`) | Zero-dependency constraint; define strict subset, validate on write |
| CLI argument parsing | Manual `sys.argv` parsing | `argparse` (stdlib) | Handles edge cases, generates help text, validates types |

**Key insight:** Python stdlib provides everything needed. The temptation is to use shell utilities (jq, shasum, etc.) but every shell dependency is a compatibility risk. Python is the one hard requirement -- use it for everything.

## Common Pitfalls

### Pitfall 1: Shell Injection via Variable Interpolation in capture.sh
**What goes wrong:** Engram's capture.sh embeds shell variables into Python string literals: `'input_summary': '''$INPUT_SUMMARY'''`. Tool inputs with quotes/backticks break or inject code.
**Why it happens:** Proof-of-concept code used the simplest approach.
**How to avoid:** Decision D-08/D-09 address this: pipe stdin directly to a single Python process. Zero shell variable interpolation of untrusted data.
**Warning signs:** Corrupted fields in observations.jsonl, Python syntax errors in hook stderr.

### Pitfall 2: Hook Blocking Claude Code
**What goes wrong:** Three `python3 -c` calls = 300-450ms per hook invocation. Perceptible delay on every tool use.
**Why it happens:** Python cold start is 80-150ms per invocation. Pyenv/asdf shims add more.
**How to avoid:** Single Python invocation (D-08). Use `async: true` for PostToolUse hooks. Cache project ID on disk (write during `prism init`, read back in capture). [VERIFIED: Claude Code supports `async: true` hook property]
**Warning signs:** Users reporting Claude Code feels slow after installing Prism.

### Pitfall 3: JSONL Concurrent Write Corruption
**What goes wrong:** Overlapping hook invocations write interleaved bytes to observations.jsonl.
**Why it happens:** Python `open("a")` + `write()` is not guaranteed atomic due to buffering.
**How to avoid:** Use `os.open(O_WRONLY | O_APPEND | O_CREAT)` + `os.write()` with a single byte-string. Keep each observation under 4096 bytes (PIPE_BUF). Add newline-recovery in extraction reader (skip unparseable lines).
**Warning signs:** `json.loads()` errors when reading observations, merged lines.

### Pitfall 4: Secret Leakage in Observations
**What goes wrong:** Current scrub patterns miss AWS keys, connection strings, private keys, JWTs.
**Why it happens:** Secret formats are unbounded; regex-only approach has gaps.
**How to avoid:** Expand default patterns to include: `AKIA[0-9A-Z]{16}` (AWS), `[a-z]+://[^:]+:[^@]+@` (connection strings), `-----BEGIN .* PRIVATE KEY-----`, `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+` (JWT). Allow custom patterns via config.
**Warning signs:** Grep for common secret prefixes in observations.jsonl.

### Pitfall 5: Index.json Single Point of Failure
**What goes wrong:** Crash during `save_index()` truncates file. Concurrent access produces race conditions.
**Why it happens:** Simple `open("w")` + `json.dump()` with no locking or atomic writes.
**How to avoid:** Atomic writes (write to `.tmp`, `os.rename()`), file locking (`fcntl.flock()`), backup (copy to `.bak` before write), recovery (try `.bak` if main fails, rebuild from engram files if both fail).
**Warning signs:** `json.JSONDecodeError` on index load, missing engrams.

### Pitfall 6: Incomplete engram->prism Rename
**What goes wrong:** A leftover `ENGRAM_HOME` reference reads from `~/.engram/` instead of `~/.prism/`, splitting state.
**Why it happens:** Find-and-replace across 15 Python files, shell scripts, templates, and agent prompts is error-prone.
**How to avoid:** Comprehensive rename checklist: env vars (`ENGRAM_HOME`->`PRISM_HOME`, `ENGRAM_PROJECT_ID`->`PRISM_PROJECT_ID`), file paths, CLI names, MCP tool names (`engram_search`->`prism_search` etc.), config keys, user-facing strings, error messages. Post-rename grep: `grep -r "engram\|ENGRAM\|Engram" --include="*.py" --include="*.sh" --include="*.md" --include="*.json"` must return zero matches (except historical docs/CHANGELOG).
**Warning signs:** Files appearing under `~/.engram/`, MCP tool names not matching.

### Pitfall 7: macOS Bash 3.2 Compatibility
**What goes wrong:** Bash 4+ features silently fail or produce wrong results on macOS default Bash.
**Why it happens:** macOS ships Bash 3.2 (GPLv2 license prevents newer versions).
**How to avoid:** No associative arrays, no `${var,,}` case conversion, no `|&` pipe-with-stderr, no `coproc`, no `readarray`/`mapfile`. Use `$(...)` not backticks. `set -euo pipefail` works on 3.2+.
**Warning signs:** Script works on Linux but fails on fresh macOS.

### Pitfall 8: `shasum` vs `sha256sum` Cross-Platform
**What goes wrong:** Engram's capture.sh uses `shasum -a 256` which exists on macOS but may not on minimal Linux.
**Why it happens:** Different platforms package different hash utilities.
**How to avoid:** Move project ID detection entirely to Python (`hashlib.sha256()`). The capture.sh no longer needs to compute hashes -- it reads a cached project ID file or delegates to Python.
**Warning signs:** Hook failures on Linux systems without `shasum`.

### Pitfall 9: MCP Server stdout Contamination
**What goes wrong:** Any `print()` call in MCP server code corrupts the JSON-RPC stream.
**Why it happens:** Python's `print()` defaults to stdout. Any imported module printing warnings also corrupts.
**How to avoid:** At MCP server startup: save real stdout, redirect `sys.stdout = sys.stderr`, use saved fd exclusively for JSON-RPC output. Add comment block warning about stdout.
**Warning signs:** MCP server disconnects mid-session.

## Code Examples

### Comprehensive Rename Map
```
# Source: Engram source code audit + design document

# Environment variables
ENGRAM_HOME          -> PRISM_HOME
ENGRAM_PROJECT_ID    -> PRISM_PROJECT_ID
ENGRAM_EXTRACT_THRESHOLD -> (use config, not env var)
ENGRAM_REVIEW_INTERVAL   -> (use config, not env var)

# File paths
~/.engram/           -> ~/.prism/
.claude/engrams.md   -> .claude/prism.md

# CLI command
engram               -> prism

# MCP server name and tools
engram               -> prism  (server name in mcpServers)
engram_search        -> prism_search
engram_get           -> prism_get
engram_relevant      -> prism_relevant
engram_record        -> prism_record
ENGRAM_PROJECT       -> PRISM_PROJECT  (MCP env var)

# Python imports
from lib.config import ENGRAM_HOME -> from lib.config import PRISM_HOME
(all references to ENGRAM_HOME in code)

# Config keys (internal)
engram -> prism in all user-facing strings, help text, error messages
"Engram initialized" -> "Prism initialized"
"engram extract"     -> "prism extract"
"engram sync"        -> "prism sync"
etc.

# Files to DROP (not copy to Prism)
lib/team.py          # Old team registry code
lib/lens.py          # Lens import/export code
hooks/cursor-capture.sh  # Cursor support dropped
```

### Claude Code Hook Configuration (settings.local.json format)
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/.prism/hooks/capture.sh pre"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "~/.prism/hooks/capture.sh post",
            "async": true
          }
        ]
      }
    ]
  },
  "mcpServers": {
    "prism": {
      "command": "python3",
      "args": ["~/.prism/lib/mcp_server.py"],
      "env": {
        "PRISM_PROJECT": "<project_id>"
      }
    }
  }
}
```
Note: `~` must be expanded to actual home path in the generated config. [VERIFIED: Claude Code hooks docs show absolute paths in examples]

### Expanded Secret Scrubbing Patterns
```python
# Source: Pitfalls research + gitleaks patterns reference
DEFAULT_SCRUB_PATTERNS = [
    # Original Engram patterns
    r"(?i)(api[_-]?key|secret|token|password|credential)\s*[:=]\s*\S+",
    r"(?i)bearer\s+\S+",
    r"sk-[a-zA-Z0-9]{20,}",
    r"ghp_[a-zA-Z0-9]{36}",
    r"xoxb-[a-zA-Z0-9\-]+",
    # Expanded patterns (Phase 1)
    r"AKIA[0-9A-Z]{16}",                                          # AWS access key
    r"(?i)[a-z]+://[^:]+:[^@\s]+@",                               # Connection strings
    r"-----BEGIN\s+\w+\s+PRIVATE\s+KEY-----",                     # Private keys
    r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",   # JWT tokens
    r"gho_[A-Za-z0-9]{36}",                                       # GitHub OAuth token
    r"ghs_[A-Za-z0-9]{36}",                                       # GitHub server token
    r"github_pat_[A-Za-z0-9_]{82}",                                # GitHub fine-grained PAT
]
```

### Default Config (Prism)
```json
{
  "extract_threshold": 15,
  "review_interval": 5,
  "review_timeout": 60,
  "decay_rate_per_week": 0.02,
  "archive_threshold": 0.2,
  "publish_min_confidence": 0.7,
  "max_context_lines": 100,
  "scrub_patterns": [],
  "block_patterns": [
    "(?i)expand\\s+access",
    "(?i)grant\\s+permissions",
    "(?i)ignore\\s+safety",
    "(?i)skip\\s+validation",
    "(?i)bypass\\s+checks",
    "(?i)modify\\s+engram\\s+system",
    "(?i)change\\s+constitution",
    "(?i)ignore\\s+previous",
    "(?i)disregard\\s+rules"
  ],
  "registry_url": ""
}
```

## State of the Art

| Old Approach (Engram) | Current Approach (Prism) | When Changed | Impact |
|----------------------|--------------------------|--------------|--------|
| 3x `python3 -c` in capture.sh | Single Python process via stdin pipe | Phase 1 | ~300ms -> ~100ms hook latency |
| Shell variable interpolation | Stdin JSON pipe to Python | Phase 1 | Eliminates shell injection surface |
| `.claude/settings.json` for hooks | `.claude/settings.local.json` | Phase 1 | Machine paths not committed to git |
| Both Claude Code + Cursor support | Claude Code only | Phase 1 | Drop cursor-capture.sh, _setup_cursor_hooks() |
| `shasum -a 256` in shell | Python `hashlib.sha256()` | Phase 1 | Cross-platform, no external binary dependency |
| Non-atomic index.json writes | Atomic write with flock + backup | Phase 1 | Prevents corruption under concurrency |
| `ENGRAM_HOME` env var | `PRISM_HOME` env var | Phase 1 | Clean namespace, no Engram references |

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research. The planner and discuss-phase use this
> section to identify decisions that need user confirmation before execution.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Python 3.9+ is acceptable as the real minimum (despite CLAUDE.md saying 3.12+) since no 3.10+ syntax features are used | Standard Stack | If user strictly requires 3.12+, install.sh must reject 3.9 and users on stock macOS would need to install newer Python |
| A2 | PostToolUse hooks support `async: true` for non-blocking capture | Architecture Patterns | If async not supported for PostToolUse specifically, hook will run synchronously (minor perf impact, not blocking) |
| A3 | `install.sh` should create the `prism` CLI wrapper at `~/.prism/prism` and symlink to `~/.local/bin/prism` (instead of Engram's pattern of symlinking to repo script) | Architecture Patterns | If user prefers repo-linked pattern, auto-updates from git pull won't apply to installed copy (requires re-running install.sh) |

## Open Questions (RESOLVED)

1. **Python minimum version enforcement** -- RESOLVED
   - What we know: System Python is 3.9.6. CLAUDE.md says 3.12+. Engram code uses only 3.6+ features.
   - Decision: install.sh warns (not fails) if python3 --version < 3.12. The code uses only 3.6+ features and works on 3.9+. A version check prints a warning like: "WARNING: Python 3.12+ recommended (found 3.x.x). Prism should work but is untested on older versions." This is implemented in Plan 01-01 Task 2 (install.sh prerequisite checks).

2. **CLI wrapper: symlink to repo vs copy to ~/.prism/** -- RESOLVED
   - Decision: Copy to ~/.prism/prism, symlink ~/.local/bin/prism -> ~/.prism/prism. Updates are explicit via install.sh re-run. For curl|bash path, no repo exists to link to. Implemented in Plan 01-01 Task 2.

3. **capture.py vs inline capture logic in capture.sh** -- RESOLVED
   - Decision: New file lib/capture.py -- it is the hot path (runs on every tool use), deserves its own module for clarity and testability. Implemented in Plan 01-03 Task 1.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python3 | All Python code, MCP server, capture processing | Yes | 3.9.6 | No fallback -- hard requirement |
| git | Project ID detection, install.sh prerequisite | Yes | 2.50.1 | No fallback -- hard requirement |
| claude CLI | Background extraction/review triggers | Yes | Available at /Users/gaurav/.local/bin/claude | Soft warning -- only needed at extraction runtime (Phase 2) |
| Bash | install.sh, capture.sh wrapper | Yes | 3.2.57 | No fallback -- hard requirement (but must use 3.2-compatible syntax) |

**Missing dependencies with no fallback:**
- None -- all required dependencies are available.

**Missing dependencies with fallback:**
- Python 3.12+: Not installed, but Python 3.9.6 is available and sufficient for all code patterns used. Recommend warning rather than blocking.

## Project Constraints (from CLAUDE.md)

These directives from CLAUDE.md constrain all implementation:

1. **Zero runtime dependencies** -- Every import must be from Python stdlib. No pip install for end users.
2. **Shell hooks never block** -- `capture.sh` must exit 0 always, use background spawns for heavy work.
3. **Safety: 4 validation gates** -- Constitution.md never overwritten by updates.
4. **Python stdlib only** -- `json`, `argparse`, `pathlib`, `re`, `subprocess`, `datetime`, `hashlib`, `os`, `sys`, `fcntl`.
5. **No `os.system()` or `os.popen()`** -- Use `subprocess.run()` with `capture_output=True, text=True, timeout=N`.
6. **No PyYAML** -- Custom frontmatter parser for the strict subset Prism uses.
7. **No jq dependency** -- Use `python3 -c` or full Python process for JSON operations in shell.
8. **`.claude/skills/` directory format** -- Not `.claude/commands/` (legacy).
9. **MCP protocol version 2025-03-26** -- Not the newer 2025-11-25 spec.
10. **`subprocess.run()` pattern** -- Always with `capture_output=True, text=True, timeout=N`.
11. **GSD Workflow Enforcement** -- Use GSD entry points for all work.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A for Phase 1 (no registry auth) |
| V3 Session Management | No | N/A for Phase 1 |
| V4 Access Control | Partial | File permissions on `~/.prism/` (700 for hooks) |
| V5 Input Validation | Yes | Secret scrubbing via regex, JSON schema validation on stdin |
| V6 Cryptography | No | SHA256 used for hashing only (not crypto) |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Shell injection via hook input | Tampering | Pipe stdin to Python, no shell interpolation (D-08, D-09) |
| Secret leakage in observations | Information Disclosure | Multi-pattern regex scrubbing at capture time |
| Hook script tampering on shared machines | Elevation of Privilege | Install hooks with restrictive permissions (chmod 700) |
| MCP stdout contamination | Tampering | Redirect stdout at startup, dedicated JSON-RPC output fd |
| Path traversal in MCP server | Information Disclosure | Validate all file paths are under PRISM_HOME |
| Git remote URL containing tokens | Information Disclosure | Only hash the URL (already done), never log raw URL |
| JSONL corruption enabling malformed observation injection | Tampering | Skip unparseable lines, validate JSON structure |

## Sources

### Primary (HIGH confidence)
- Engram source code (`/Users/gaurav/codes/engram/`) -- All library files, hooks, agents, templates directly inspected
- Claude Code Hooks API docs (`https://code.claude.com/docs/en/hooks`) -- Complete hook format, stdin JSON structure, async support, matcher syntax
- Prism design document (`/Users/gaurav/codes/prism/unified-design.md`) -- Architecture, file layout, CLI commands, installation flow
- Prism CONTEXT.md (`.planning/phases/01-foundation-observation/01-CONTEXT.md`) -- Locked decisions D-01 through D-13
- Pre-roadmap pitfalls research (`.planning/research/PITFALLS.md`) -- 10 pitfalls with prevention strategies

### Secondary (MEDIUM confidence)
- Claude Code MCP docs (`https://code.claude.com/docs/en/mcp`) -- MCP server configuration in settings files
- Python 3.9 compatibility -- tested against actual Engram source code patterns (no 3.10+ features used)

### Tertiary (LOW confidence)
- None -- all findings verified against source code or official documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries are Python stdlib, fully verified
- Architecture: HIGH -- adapting from working Engram codebase with well-understood changes
- Pitfalls: HIGH -- documented from source code review + pre-roadmap research with cited sources

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (stable domain -- Python stdlib, shell scripting, Claude Code hooks)
