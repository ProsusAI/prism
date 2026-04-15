---
status: complete
phase: 03-bridge-slash-commands
source: [03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md]
started: 2026-04-15
updated: 2026-04-15
---

## Current Test

[testing complete]

## Tests

### 1. prism promote command exists
expected: Run `prism promote --help` — should show usage for the promote subcommand with --name override option.
result: pass

### 2. Gate check blocks low-confidence engrams
expected: Run `prism promote <entry-id>` on an engram with confidence below 0.7 — should be rejected with a gate check message, not promoted.
result: pass

### 3. Promote produces skill files
expected: Run `prism promote <entry-id>` on the "use-4-space-identation" engram (confidence 0.9) — should create `_analysis/extracted_skills_codebase/use-4-space-identation/plugin.json` and `SKILL.md`.
result: issue (fixed)
reported: "Files created but SKILL.md contained irrelevant 'evidence' section. Expected sections: key decisions, anti-patterns (structural template optional)."
severity: major
resolution: "_build_skill_md rewritten to generate Key Decisions + Anti-patterns sections. Evidence section stripped. Structural Template included only for procedure/tool_pattern/error_recipe kinds."

### 4. Slash commands present in skills/ directory
expected: Run `ls ~/.prism/skills/` — should list the 12 slash commands: analyze-agent-codebase, mine-history, mine-design, curate-skills, run-analysis-pipeline, run-history-pipeline, extract-skills, synthesize, synthesize-decisions, publish-skills, advise-skills, audit-code.
result: pass

### 5. Slash commands linked in project
expected: After `prism init` in a project, run `ls .claude/skills/` — should show symlinks to the prism skills.
result: pass

### 6. advise-skills command is accessible
expected: In Claude Code, type `/advise` — should show the advise-skills skill as an option. Running it should attempt to query the registry (or fall back gracefully if none configured).
result: pass

## Summary

total: 6
passed: 5
issues: 1 (fixed inline)
pending: 0
skipped: 0

## Gaps

- truth: "prism promote SKILL.md should match extract-skills format: Key Decisions, Anti-patterns, optional Structural Template"
  status: fixed
  reason: "SKILL.md had irrelevant Evidence section and no structured sections"
  severity: major
  test: 3
  fix: "_build_skill_md rewritten; Evidence stripped; Structural Template optional for procedure/tool_pattern/error_recipe kinds only"
