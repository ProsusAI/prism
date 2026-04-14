---
status: pending
phase: 02-personal-knowledge-loop
source: [02-05-PLAN.md]
started: 2026-04-14
updated: 2026-04-14
---

## Tests

### 1. Unified status display
expected: Run `prism status` in a project — should show unified `[global]`/`[project]` scope-tagged list sorted by confidence.
result: [pending]

### 2. Learn + auto-sync
expected: Run `prism learn "prefer 4-space indentation"` — should create engram file AND auto-generate `.claude/prism.md`. Verify the file exists and contains the new preference.
result: [pending]

### 3. Status after learn
expected: Run `prism status` again — should show the new entry with `[global]` or `[project]` tag and confidence 0.90.
result: [pending]

### 4. Maintain lifecycle
expected: Run `prism maintain` — should report decay/archive counts (may be 0 if nothing to decay yet).
result: [pending]

### 5. Procedures listing
expected: Run `prism procedures` — should list procedures sorted by confidence or report none found.
result: [pending]

### 6. Session analysis
expected: Run `prism analyze-sessions --list` — should show available sessions (if any exist in `~/.claude/projects/`).
result: [pending]

### 7. MCP nudge footer
expected: Check `.claude/prism.md` contains the MCP nudge footer ("Search (prism_search): when encountering errors...").
result: [pending]

### 8. Extract pipeline (optional)
expected: Run `prism extract` with 15+ observations accumulated — should run Haiku→Sonnet pipeline and produce engrams.
result: [pending]

## Summary

total: 8
passed: 0
