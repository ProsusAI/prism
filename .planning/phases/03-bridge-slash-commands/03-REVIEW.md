---
phase: 03-bridge-slash-commands
reviewed: 2026-04-14T12:00:00Z
depth: standard
files_reviewed: 24
files_reviewed_list:
  - install.sh
  - lib/bridge.py
  - lib/cli.py
  - lib/config.py
  - schemas/plugin.schema.json
  - skills/advise-skills/SKILL.md
  - skills/analyze-agent-codebase/SKILL.md
  - skills/analyze-agent-codebase/questions_cluster_a.md
  - skills/analyze-agent-codebase/questions_cluster_b.md
  - skills/analyze-agent-codebase/questions_cluster_c.md
  - skills/analyze-agent-codebase/questions_cluster_d.md
  - skills/analyze-agent-codebase/questions_cluster_e.md
  - skills/analyze-agent-codebase/questions_cluster_f.md
  - skills/analyze-agent-codebase/questions_synthesis.md
  - skills/audit-code/SKILL.md
  - skills/curate-skills/SKILL.md
  - skills/extract-skills/SKILL.md
  - skills/mine-design/SKILL.md
  - skills/mine-history/SKILL.md
  - skills/publish-skills/SKILL.md
  - skills/run-analysis-pipeline/SKILL.md
  - skills/run-history-pipeline/SKILL.md
  - skills/synthesize-decisions/SKILL.md
  - skills/synthesize/SKILL.md
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-04-14T12:00:00Z
**Depth:** standard
**Files Reviewed:** 24
**Status:** issues_found

## Summary

Reviewed the bridge module (`lib/bridge.py`), CLI router (`lib/cli.py`), config module (`lib/config.py`), installer (`install.sh`), plugin schema (`schemas/plugin.schema.json`), and 14 SKILL.md slash command files. The Python source code is generally well-structured, follows the project's zero-dependency constraint, and uses safe subprocess patterns (list-based arguments, timeouts). The slash command SKILL.md files are well-written instructional documents.

The main concerns are: a potential `AttributeError` crash in `cli.py` when session data contains `None` for `cwd`, a missing path-containment check when reading engram files from index-provided paths in `bridge.py`, and a grep regex issue in `install.sh` that could give incorrect PATH advice.

No critical security issues were found. All subprocess calls use list-based arguments (no shell injection). The `scrub_patterns` and `block_patterns` in `config.py` provide reasonable safety defaults.

## Warnings

### WR-01: Potential AttributeError on None cwd in session listing

**File:** `lib/cli.py:212`
**Issue:** When `sess_list[0]["cwd"]` is `None` (not just missing but explicitly null), the expression `sess_list[0]["cwd"].rstrip("/")` will raise `AttributeError: 'NoneType' object has no attribute 'rstrip'`. The ternary condition `if sess_list[0]["cwd"]` guards the falsy case, but Python evaluates the full ternary left-to-right and the truthy branch calls `.rstrip()` before the condition is checked. Wait -- actually in Python, `X if COND else Y` evaluates `COND` first, then `X` only if true. So `None` is falsy and would take the `else pid` branch. The real issue is if `"cwd"` key is absent entirely, which raises `KeyError`. If session data from Claude Code transcripts ever omits the `cwd` field, this line crashes.
**Fix:**
```python
cwd = sess_list[0].get("cwd") or ""
name = os.path.basename(cwd.rstrip("/")) if cwd else pid
```
Also add `import os` at the top of the function or file instead of using `__import__("os")`.

### WR-02: No path-containment check when reading engram files from index

**File:** `lib/bridge.py:72`
**Issue:** `entry_path = PRISM_HOME / entry.get("path", "")` directly uses the `path` field from the index file without verifying the resolved path is within `PRISM_HOME`. If `index.json` were tampered with (e.g., `path` set to `../../etc/shadow`), `entry_path.read_text()` on line 77 would read arbitrary files. While `index.json` is written by Prism itself and lives in `~/.prism/`, the extraction pipeline uses AI-generated content that flows through the index, so defense-in-depth is warranted.
**Fix:**
```python
entry_path = (PRISM_HOME / entry.get("path", "")).resolve()
if not str(entry_path).startswith(str(PRISM_HOME.resolve())):
    print("Security: path escapes PRISM_HOME: {}".format(entry_path))
    return
```

### WR-03: grep without -F flag may misinterpret PATH components as regex

**File:** `install.sh:109`
**Issue:** `grep -qx "$BIN_DIR"` uses regex matching. The default `$BIN_DIR` value `$HOME/.local/bin` contains a dot (`.`) which is a regex wildcard. This means the PATH check could produce a false match against a path like `/Users/gaurav/Xlocal/bin` (the dot matches any character). In practice this is unlikely to cause harm, but it could suppress the PATH warning when `$BIN_DIR` is not actually in PATH.
**Fix:**
```bash
if ! echo "$PATH" | tr ':' '\n' | grep -qxF "$BIN_DIR"; then
```

## Info

### IN-01: Unused import -- hashlib in bridge.py

**File:** `lib/bridge.py:3`
**Issue:** `import hashlib` is present but never used anywhere in the file.
**Fix:** Remove line 3: `import hashlib`

### IN-02: __import__ usage instead of standard import

**File:** `lib/cli.py:212`
**Issue:** `__import__("os").path.basename(...)` uses the dunder import function instead of a standard `import os` statement. Same pattern appears in `lib/mcp_server.py:216` with `__import__("datetime")`. This is a code smell that harms readability.
**Fix:** Add `import os` to the imports section of `lib/cli.py` and `import datetime` (or `from datetime import date`) to `lib/mcp_server.py`, then use the modules directly.

### IN-03: Empty lead in description when trigger and body are empty

**File:** `lib/bridge.py:226-238`
**Issue:** If `trigger` is an empty string and `body` is empty or contains only headings/bullet points, `lead` stays as empty string. The resulting description would start with `". TRIGGER when: ..."` (a leading dot-space). This is an edge case since gate checks require evidence and confidence, making empty-trigger promotion unlikely, but the function has no guard against it.
**Fix:**
```python
lead = trigger or skill_name.replace("-", " ").title()
```

### IN-04: Skill directory copy does not handle subdirectories

**File:** `install.sh:64`
**Issue:** `cp "$skill_dir"* "$PRISM_HOME/skills/$skill_name/" 2>/dev/null || true` copies only top-level files. If any skill directory contains subdirectories, those will not be copied. Currently all skill directories contain only flat files, but this could silently break if a skill with a subdirectory is added later.
**Fix:** Use `cp -r` to recursively copy:
```bash
cp -r "$skill_dir"* "$PRISM_HOME/skills/$skill_name/" 2>/dev/null || true
```

---

_Reviewed: 2026-04-14T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
