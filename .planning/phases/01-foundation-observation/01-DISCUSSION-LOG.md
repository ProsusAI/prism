# Phase 1: Foundation + Observation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md -- this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 01-foundation-observation
**Areas discussed:** Copy fidelity, Init experience, Hook architecture, CLI output style

---

## Copy Fidelity

### Transplant Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Rename and ship | Literal copy with engram->prism renames, drop team.py/lens.py/cursor-capture.sh. Fastest path. | ✓ |
| Rename + restructure | Copy with renames plus reorganize into cleaner module structure (prism/core/, prism/hooks/, etc.) | |
| Rewrite from design doc | Fresh code inspired by Engram patterns but not literally copied. Cleanest, slowest. | |

**User's choice:** Rename and ship
**Notes:** Fastest path to working Phase 1. Clean up later if needed.

### Lens Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Copy now, wire later | Copy all 12 Lens skill directories during install.sh. Sit dormant until Phase 3. | |
| Defer to Phase 3 | Phase 1 only copies Engram code. Lens skills arrive when needed. | ✓ |

**User's choice:** Claude's discretion — "Do what you think has lesser pitfall and better unified experience long term"
**Notes:** Decided to defer to Phase 3 for focus.

### Upstream Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Fork and forget | Prism is canonical. Engram becomes archived. No merge strategy. | ✓ |
| Track upstream | Keep Engram alive. Periodically pull changes. | |
| Monorepo | Move Engram source into Prism as subdirectory. | |

**User's choice:** Fork and forget
**Notes:** None

---

## Init Experience

### Merge Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Merge carefully | Read existing JSON, add Prism entries alongside existing. Never clobber. Warn on conflicts. | ✓ |
| Overwrite Prism entries | Replace Prism-related entries, leave non-Prism alone. | |
| Fail if exists | Refuse if settings exist, require --force. | |

**User's choice:** Merge carefully
**Notes:** None

### Interactivity

| Option | Description | Selected |
|--------|-------------|----------|
| Fully automatic | One command, zero prompts. Detect, configure, print summary. Idempotent. | ✓ |
| Guided with confirmations | Show plan, ask confirmation before each change. | |
| Automatic with --dry-run | Default automatic, --dry-run flag to preview. | |

**User's choice:** Fully automatic
**Notes:** "But it gives a summary (not too detailed so users actually read) either at the start or the end"

### Prerequisites

| Option | Description | Selected |
|--------|-------------|----------|
| Hard fail on python3/git | python3 and git non-negotiable. claude CLI is soft warning. | ✓ |
| Fail on all three | Refuse unless python3, git, AND claude all present. | |
| Warn and continue | Print warnings, install anyway. | |

**User's choice:** Hard fail on python3/git
**Notes:** None

---

## Hook Architecture

### Performance Fix Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Fix now -- single Python call | Collapse to one python3 invocation. Since we're renaming anyway, diff is small. | ✓ |
| Keep Engram's pattern | Copy capture.sh as-is. Multiple Python calls but known-working. Optimize in v2. | |
| Rewrite hook in Python | Replace capture.sh entirely with Python script. Eliminates shell layer. | |

**User's choice:** Fix now -- single Python call
**Notes:** None

### Data Passing

| Option | Description | Selected |
|--------|-------------|----------|
| Stdin pipe | Shell reads JSON from stdin, pipes to Python. No temp files, no injection risk. | ✓ |
| Temp file | Shell writes to temp file, Python reads. Simpler debugging. | |
| Environment variable | Pass JSON as env var. Simple but size-limited. | |

**User's choice:** Stdin pipe
**Notes:** None

### Extraction Threshold

| Option | Description | Selected |
|--------|-------------|----------|
| Keep 15, hardcoded | Engram's threshold. No config complexity. | |
| Configurable from day one | `prism config extraction.threshold 20`. Adds config key. | ✓ |
| Higher default (25) | More conservative, fewer runs, more signal per run. | |

**User's choice:** Configurable from day one
**Notes:** Default remains 15.

---

## CLI Output Style

### Personality

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal and clean | Short, structured. No emoji. Think `git status`. | |
| Friendly with context | Brief explanations alongside data. Think `gh` CLI. | ✓ |
| Terse/scriptable | Machine-first. Plain text, no color default. Think `jq`/`aws`. | |

**User's choice:** Friendly with context
**Notes:** None

### Log Format

| Option | Description | Selected |
|--------|-------------|----------|
| Human-readable table | Formatted table: timestamp, tool, summary. --json for raw. | ✓ |
| Raw JSONL | Default raw JSONL. --pretty flag for human view. | |
| Compact one-liner | Each observation as single formatted line. Dense but scannable. | |

**User's choice:** Human-readable table
**Notes:** None

### Status Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-detect project | Inside git repo: project status. Outside: global summary. --project for explicit. | ✓ |
| Always show global | Default all projects. --project narrows. | |
| Require explicit scope | No magic detection. Explicit flags only. | |

**User's choice:** Auto-detect project
**Notes:** None

---

## Claude's Discretion

- Lens slash command copy timing (decided: defer to Phase 3)
- Exact `prism init` summary format and content
- `install.sh` upgrade behavior for partial failures
- Color scheme specifics and table formatting details

## Deferred Ideas

None -- discussion stayed within phase scope
