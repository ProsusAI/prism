---
phase: 05-integration-fixes-hardening
reviewed: 2026-04-15T12:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - install.sh
  - lib/commands.py
  - lib/mcp_server.py
  - skills/publish-skills/SKILL.md
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-04-15T12:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed four files spanning the installer, CLI command layer, MCP server, and a slash-command skill. The codebase is generally well-structured with good defensive patterns (atomic writes in index.py, file locking, idempotent init). However, there is one critical path-traversal vulnerability in the MCP server, several logic bugs in commands.py (race condition reading .gitignore while appending, duplicate comment blocks on re-run), and some missing input validation in the MCP server's `_record` function that could let an attacker write files outside the expected engrams directory.

## Critical Issues

### CR-01: Path traversal via MCP `prism_get` -- entry path not validated

**File:** `lib/mcp_server.py:87`
**Issue:** The `_get_entry_content` function reads a file at `PRISM_HOME / entry["path"]` where `entry["path"]` comes from the index. If a malicious or corrupt index entry contains a `path` value with `../` sequences (e.g., `../../etc/passwd`), this would read arbitrary files on the filesystem. The `_record` function also constructs file paths from user-supplied text via the slug, but at least constrains the directory. The `_get_entry_content` path is directly from the index with no sanitization.

While the index is locally written, the MCP `prism_record` tool allows Claude (or any MCP client) to create entries. A crafted entry ID could be benign, but the `path` field stored in the index by `_record` at line 180 uses `filepath.relative_to(PRISM_HOME)` which is safe -- however, if the index is ever edited externally or corrupted, the read path has no guard.

**Fix:** Validate that the resolved path is within PRISM_HOME before reading:
```python
def _get_entry_content(entry_id):
    """Read full content of a knowledge entry file."""
    entry = get_entry(entry_id)
    if not entry:
        return None

    filepath = (PRISM_HOME / entry["path"]).resolve()
    # Guard: ensure resolved path is under PRISM_HOME
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

## Warnings

### WR-01: Race condition in `_update_gitignore` -- reads file while appending

**File:** `lib/commands.py:182-184`
**Issue:** The function opens the `.gitignore` for appending (line 182), then calls `gitignore_path.read_text()` twice inside the `with` block (line 183). Reading a file that is simultaneously open for append is fragile: the append handle's write buffer and the read call can interact unpredictably. More importantly, re-reading the file twice on line 183 is redundant and wasteful. The first condition `existing_lines` already knows whether the file had content.

**Fix:** Read the file content once before opening for append, and use the cached content:
```python
def _update_gitignore() -> None:
    gitignore_path = Path.cwd() / ".gitignore"
    entries = [
        ".claude/settings.local.json",
        ".claude/prism.md",
        ".claude/skills/",
        ".claude/.prism_project_id",
    ]

    existing_content = ""
    if gitignore_path.exists():
        existing_content = gitignore_path.read_text()
    existing_lines = set(existing_content.splitlines())

    to_add = [e for e in entries if e not in existing_lines]
    if to_add:
        with open(gitignore_path, "a") as f:
            if existing_content and not existing_content.endswith("\n"):
                f.write("\n")
            f.write("# Prism (auto-generated, machine-specific)\n")
            for entry in to_add:
                f.write(entry + "\n")
```

### WR-02: Duplicate "# Prism" comment block appended on re-init with partial entries

**File:** `lib/commands.py:185`
**Issue:** If `prism init` is run, adds 4 entries plus the comment header. If the user manually removes one entry from `.gitignore` and re-runs `prism init`, `to_add` will be non-empty (1 entry), and a second `# Prism (auto-generated, machine-specific)` comment header is appended. Over multiple re-runs this creates duplicate comment blocks. The duplicate-check only looks at the data entries, not the comment line.

**Fix:** Check whether the comment header already exists in `existing_lines` before writing it:
```python
    if to_add:
        with open(gitignore_path, "a") as f:
            if existing_content and not existing_content.endswith("\n"):
                f.write("\n")
            if "# Prism (auto-generated, machine-specific)" not in existing_lines:
                f.write("# Prism (auto-generated, machine-specific)\n")
            for entry in to_add:
                f.write(entry + "\n")
```

### WR-03: MCP `_record` does not validate `kind` parameter against allowed values

**File:** `lib/mcp_server.py:137`
**Issue:** The MCP tool schema at line 278 defines an `enum` for `kind` (`["preference", "correction", "procedure", "error_recipe", "domain_fact", "tool_pattern"]`), but the `_record` function at line 137 accepts any string for `kind` without validation. If a client sends a request directly (bypassing schema validation), arbitrary `kind` values would be written into the index and engram file. MCP schema validation is advisory -- the server should enforce it.

**Fix:** Add validation at the top of `_record`:
```python
VALID_KINDS = {"preference", "correction", "procedure", "error_recipe", "domain_fact", "tool_pattern"}

def _record(text, kind="preference", project_id=None, scope="global"):
    if kind not in VALID_KINDS:
        return {"id": "", "status": "error", "message": f"Invalid kind: {kind}"}
    # ... rest of function
```

### WR-04: `cmd_forget` uses `entry.get("path", "")` which can construct path to PRISM_HOME root

**File:** `lib/commands.py:332`
**Issue:** If an entry in the index has an empty `"path"` field (or the field is missing), `PRISM_HOME / ""` resolves to `PRISM_HOME` itself. The subsequent `source_path.exists()` check would be True (it is a directory), and `shutil.move(str(source_path), str(dest))` would attempt to move the entire PRISM_HOME directory into the archive. This is unlikely but a dangerous edge case.

**Fix:** Validate that `path` is non-empty and points to a file before moving:
```python
    source_path = PRISM_HOME / entry.get("path", "")
    if entry.get("path") and source_path.is_file():
        archive_dir = PRISM_HOME / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / source_path.name
        shutil.move(str(source_path), str(dest))
        print(f"Archived: {source_path.name} -> archive/")
```

### WR-05: `cmd_maintain` iterates `list(index["engrams"])` but calls `remove_entry()` which reloads the full index each time

**File:** `lib/commands.py:430-458`
**Issue:** The maintain loop at line 430 iterates a snapshot of entries, but for each archived entry it calls `remove_entry(entry["id"])` (line 458). Looking at `index.py`, `remove_entry` calls `load_index()` + `save_index()` -- a full disk read and write per archival. If many entries need archiving simultaneously, this is N disk round-trips. More importantly, `update_confidence` on line 462 also does load+save per entry. If an entry was archived by a concurrent process between the snapshot and the `remove_entry` call, the remove silently fails (returns None), which is safe but wasteful. Consider batching index modifications similar to `_reinforce_batch` in mcp_server.py.

**Fix:** Batch all index modifications into a single load/save cycle:
```python
def cmd_maintain() -> None:
    config = get_config()
    decay_rate = config.get("decay_rate_per_week", 0.02)
    archive_threshold = config.get("archive_threshold", 0.2)

    index = load_index()
    today = date.today()
    decayed = 0
    archived = 0
    to_archive_ids = set()

    for entry in index["engrams"]:
        if entry.get("pinned"):
            continue
        # ... compute new_conf ...
        if new_conf < archive_threshold:
            to_archive_ids.add(entry["id"])
            # move file ...
            archived += 1
        elif new_conf < old_conf:
            entry["confidence"] = round(new_conf, 3)
            decayed += 1

    index["engrams"] = [e for e in index["engrams"] if e["id"] not in to_archive_ids]
    save_index(index)
```

## Info

### IN-01: Unused import `datetime` in commands.py

**File:** `lib/commands.py:6`
**Issue:** `datetime` is imported from the `datetime` module but only `date` is used throughout the file. The `datetime` and `timezone` imports are not referenced.

**Fix:** Change to `from datetime import date` only.

### IN-02: `_text_to_id` imports `re` inside the function body

**File:** `lib/commands.py:779`
**Issue:** The `re` module is imported locally inside `_text_to_id` rather than at module top level. While functional, this is inconsistent with the rest of the file which uses top-level imports.

**Fix:** Move `import re` to the top of the file with the other imports.

### IN-03: Bare `except` in SKILL.md Python snippet swallows all errors silently

**File:** `skills/publish-skills/SKILL.md:49`
**Issue:** The Python snippet for registry resolution uses a bare `except: pass` (line 49) which catches all exceptions including KeyboardInterrupt and SystemExit. Since this is a slash-command template meant to be copy-adapted by an agent, the pattern could propagate.

**Fix:** Use `except (FileNotFoundError, json.JSONDecodeError, KeyError): pass` to be explicit about expected failures.

### IN-04: MCP server `_relevant` function builds unused `filters` dict

**File:** `lib/mcp_server.py:120-124`
**Issue:** The `filters` dict is populated but then `list_entries(**filters)` is called with `kind=None` (always set at line 122 when domain is truthy) and project_id. Setting `kind=None` has no filtering effect since `list_entries` checks `if kind:` which is falsy for None. The `filters["kind"] = None` assignment is dead code.

**Fix:** Remove the `filters` dict and call `list_entries` directly with the needed parameters:
```python
def _relevant(file_path=None, domain=None, project_id=None, limit=5):
    # ... domain inference ...
    entries = list_entries(project_id=project_id)
    # ... domain prioritization ...
```

---

_Reviewed: 2026-04-15T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
