---
phase: 02-personal-knowledge-loop
reviewed: 2026-04-14T12:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - agents/extractor.md
  - agents/reviewer.md
  - agents/validator.md
  - lib/cli.py
  - lib/commands.py
  - lib/extract.py
  - lib/sessions.py
  - lib/mcp_server.py
findings:
  critical: 2
  warning: 7
  info: 5
  total: 14
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-14T12:00:00Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Reviewed the core personal knowledge loop implementation: CLI router, user-facing commands, extraction pipeline, session analysis, and MCP server. The agent prompt files (extractor, reviewer, validator) are well-structured and do not contain code-level issues.

Key concerns: (1) The MCP server has a path traversal vulnerability via the `prism_get` tool, (2) the `_relevant` function passes an unexpected keyword argument to `list_entries`, (3) several file handles are opened without `with` statements risking resource leaks, and (4) the `cmd_maintain` function mutates a list while iterating a copy but the iterator pattern has a subtle correctness issue with index reloads.

Overall the code is clean, follows the zero-dependency constraint, and has good defensive patterns (lock files, stale lock cleanup, atomic index writes). The issues found are fixable with targeted changes.

## Critical Issues

### CR-01: Path Traversal in MCP prism_get Tool

**File:** `lib/mcp_server.py:87`
**Issue:** The `_get_entry_content` function reads the file at `PRISM_HOME / entry["path"]`. The `entry["path"]` value comes from the index, which is populated by both extraction (AI-generated content) and user input. If a malicious or corrupted index entry contains a relative path with `..` components (e.g., `../../etc/passwd`), the server would read arbitrary files on the filesystem. The MCP server is a long-running subprocess receiving requests from Claude Code -- the `entry["path"]` is not validated to stay within PRISM_HOME.
**Fix:**
```python
def _get_entry_content(entry_id):
    """Read full content of a knowledge entry file."""
    entry = get_entry(entry_id)
    if not entry:
        return None

    filepath = (PRISM_HOME / entry["path"]).resolve()
    # Ensure path stays within PRISM_HOME
    if not str(filepath).startswith(str(PRISM_HOME.resolve())):
        return None

    if not filepath.exists():
        return None

    try:
        return {
            "id": entry_id,
            "content": filepath.read_text(),
            "confidence": entry.get("confidence"),
            "kind": entry.get("kind"),
            "source": entry.get("source", "local"),
        }
    except OSError:
        return None
```

### CR-02: Broken Keyword Argument in _relevant Causes TypeError

**File:** `lib/mcp_server.py:126`
**Issue:** The `_relevant` function calls `list_entries(**filters)` where `filters` can contain `{"kind": None, "project_id": "..."}`. However, `list_entries` in `lib/index.py:101` checks `if kind:` which filters correctly for `None`, but the real problem is on line 123: `filters["kind"] = None` is set unconditionally when `domain` is truthy. This means `list_entries` receives `kind=None` which is benign, but the `filters` dict also never actually uses domain for filtering. The function claims to find entries relevant to a domain, but `list_entries` has no `domain` parameter -- the domain filtering is done post-hoc on lines 129-132. The actual bug is that when `domain` is set but `project_id` is not, the function passes `kind=None` to `list_entries`, which is a no-op filter but adds a confusing unused key. More critically, if `domain` is falsy and `project_id` is set, the `filters` dict becomes `{"project_id": "..."}` which is valid, but if both are set, `filters` is `{"kind": None, "project_id": "..."}` -- `kind=None` is harmlessly ignored by `list_entries` but is dead/misleading code that will confuse future maintainers. The real functional issue: when `domain` is falsy AND `project_id` is falsy, `filters` is `{}` so `list_entries()` returns ALL entries from all projects with no scoping at all.
**Fix:** Remove the confusing `kind` assignment and ensure project_id filtering is always applied:
```python
def _relevant(file_path=None, domain=None, project_id=None, limit=5):
    """Find entries relevant to current context."""
    ext_domain = { ... }

    if not domain and file_path:
        ext = Path(file_path).suffix.lower()
        domain = ext_domain.get(ext)

    entries = list_entries(project_id=project_id)

    if domain:
        matching = [e for e in entries if e.get("domain") == domain]
        others = [e for e in entries if e.get("domain") != domain]
        entries = matching + others

    return entries[:limit]
```

## Warnings

### WR-01: File Handle Not Closed in cmd_status

**File:** `lib/commands.py:238`
**Issue:** `open(obs_path)` is used without a `with` statement to count observation lines. If an exception occurs during iteration, the file handle leaks.
**Fix:**
```python
with open(obs_path) as f:
    obs_count = sum(1 for _ in f)
```

### WR-02: Double File Read in _update_gitignore

**File:** `lib/commands.py:176`
**Issue:** Line 176 calls `gitignore_path.read_text()` twice in one conditional expression (once to check truthiness, once to check `endswith`). This is a minor inefficiency but more importantly, if the file is being written to concurrently, the two reads could return different content, leading to an incorrect decision about whether to add a newline.
**Fix:**
```python
if to_add:
    existing_content = gitignore_path.read_text() if gitignore_path.exists() else ""
    with open(gitignore_path, "a") as f:
        if existing_content and not existing_content.endswith("\n"):
            f.write("\n")
        f.write("# Prism (auto-generated, machine-specific)\n")
        for entry in to_add:
            f.write(entry + "\n")
```

### WR-03: Repeated Gitignore Comment Blocks on Re-init

**File:** `lib/commands.py:178`
**Issue:** Each call to `_update_gitignore` that adds entries also writes the comment `# Prism (auto-generated, machine-specific)`. If init is run multiple times and some entries were manually removed, the function will re-add them with another comment block, creating duplicate comment lines. The `existing_lines` check on line 170 compares exact lines, so it won't detect that the comment already exists.
**Fix:** Check for the comment marker before writing it, or filter it into the dedup set:
```python
marker = "# Prism (auto-generated, machine-specific)"
if marker not in existing_lines and to_add:
    f.write(marker + "\n")
```

### WR-04: cmd_maintain Iterates Copy but Reloads Index Per Remove

**File:** `lib/commands.py:422`
**Issue:** `cmd_maintain` iterates `list(index["engrams"])` (a snapshot copy), but calls `remove_entry(entry["id"])` on line 450 which does a full `load_index()` + `save_index()` cycle internally. If two entries are archived, the second `remove_entry` call reloads the index from disk, which still has both entries removed correctly. However, this means N disk reads + N disk writes for N archived entries. More importantly, the `decayed` entries are updated via `update_confidence` on line 454, which also does a load/save cycle each time. If there are many entries, this creates a thundering-herd of index rewrites. This is not a correctness bug but a reliability concern -- if the process is killed mid-loop, partial updates are applied.
**Fix:** Accumulate all changes and do a single `save_index()` at the end:
```python
index = load_index()
# ... iterate and modify entries in index["engrams"] directly ...
save_index(index)
```

### WR-05: Validation Phase Gives Sonnet Bash Tool Access

**File:** `lib/extract.py:183`
**Issue:** The `_phase2_validate` function grants the Sonnet validation subprocess `--allowedTools "Read,Write,Edit,Glob,Grep,Bash"`. Giving `Bash` access to the validation model means it could execute arbitrary shell commands. The validator's job is to read candidate files, check them against the constitution and index, and output JSON decisions. It does not need Bash access. This violates the principle of least privilege and could be a vector for prompt injection if a malicious candidate file tricks Sonnet into running commands.
**Fix:** Remove `Bash` from the allowed tools:
```python
["claude", "--print", "--model", "sonnet", "-p", prompt,
 "--allowedTools", "Read,Write,Edit,Glob,Grep"],
```

### WR-06: _parse_frontmatter Silently Accepts Negative Confidence

**File:** `lib/extract.py:300`
**Issue:** The frontmatter parser converts `confidence` via `float()` but does not validate the range. A malicious or buggy candidate file could set `confidence: 99.0` or `confidence: -1.0`, bypassing the documented 0.0-0.95 range. This value propagates directly into the index.
**Fix:**
```python
raw_confidence = float(frontmatter.get("confidence", 0.5))
confidence = max(0.0, min(0.95, raw_confidence))
```

### WR-07: MCP Server stdout Redirection Suppresses Errors During Record

**File:** `lib/mcp_server.py:191-200`
**Issue:** The `_record` function redirects `sys.stdout` to `io.StringIO()` to suppress sync output, then restores it in a `finally` block. However, the MCP server's `main()` loop writes to `sys.stdout` for protocol messages. If `_record` is called from a concurrent context or if the `finally` block fails to restore stdout (e.g., due to a `SystemExit`), the MCP protocol stream would be corrupted. While the current single-threaded design makes this unlikely, the pattern is fragile.
**Fix:** Instead of redirecting stdout, modify `sync_claude_code` to accept a `quiet` parameter, or capture output differently:
```python
try:
    from lib.sync import sync_claude_code
    # Redirect at a more targeted level or add quiet param
    sync_claude_code(project_id, quiet=True)
except Exception:
    pass
```

## Info

### IN-01: Unused Import in extract.py

**File:** `lib/extract.py:7`
**Issue:** `sys` is imported but never used in the module.
**Fix:** Remove `import sys` from the import block.

### IN-02: Magic Number for Lock Staleness Threshold

**File:** `lib/extract.py:48`
**Issue:** The stale lock timeout of 600 seconds is a magic number. It should reference a named constant or config value for maintainability.
**Fix:**
```python
STALE_LOCK_SECONDS = 600  # 10 minutes
```

### IN-03: Redundant Conditional Check in MCP prism_search

**File:** `lib/mcp_server.py:301-303`
**Issue:** Lines 301-303 check `if results:` immediately after line 300 already returned early when `not results`. The second `if results:` guard on line 302 is always true at that point, making it dead code.
**Fix:** Remove the redundant `if results:` check:
```python
if not results:
    return {"content": [{"type": "text", "text": "No matching entries found."}]}
_reinforce_batch([r["id"] for r in results])
```

### IN-04: Same Redundant Check in prism_relevant

**File:** `lib/mcp_server.py:324-326`
**Issue:** Same pattern as IN-03. `if results:` on line 325 is always true because `not results` returned early on line 323.
**Fix:** Remove the redundant `if results:` wrapper.

### IN-05: import re Inside Function Body

**File:** `lib/commands.py:665`
**Issue:** `import re` is done inside `_text_to_id` rather than at module level. While this is a minor style issue, it causes a re-import check on every call. Since `re` is stdlib and lightweight, moving it to the top-level import block is cleaner.
**Fix:** Move `import re` to the module-level imports at the top of `commands.py`.

---

_Reviewed: 2026-04-14T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
