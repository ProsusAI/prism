---
status: partial
phase: 01-foundation-observation
source: [01-VERIFICATION.md]
started: 2026-04-14T13:45:00.000Z
updated: 2026-04-14T13:45:00.000Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Install end-to-end
expected: Run `./install.sh` on a clean system, verify `~/.prism/` tree created with all subdirs (global/engrams, archive, hooks, agents, lib, skills, projects), `prism` symlinked to `~/.local/bin/prism`. Re-run to confirm idempotency (no errors, config.json/constitution.md/index.json preserved).
result: [pending]

### 2. prism init JSON merge safety
expected: Create a `.claude/settings.local.json` with existing third-party tool entries (e.g., another MCP server, another hook). Run `prism init`. Verify Prism hooks and MCP server are added without removing or corrupting existing entries.
result: [pending]

### 3. Live hook capture
expected: After `prism init` in a project, use Claude Code tools normally. Run `prism log` and verify observations appear with tool name, timestamp, and scrubbed input summary. No perceptible delay during tool use.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
