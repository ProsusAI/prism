---
phase: 01-foundation-observation
reviewed: 2026-04-14T15:30:00Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - agents/extractor.md
  - agents/reviewer.md
  - agents/validator.md
  - hooks/capture.sh
  - install.sh
  - lib/__init__.py
  - lib/capture.py
  - lib/cli.py
  - lib/commands.py
  - lib/config.py
  - lib/extract.py
  - lib/index.py
  - lib/mcp_server.py
  - lib/project.py
  - lib/review.py
  - lib/scrub.py
  - lib/sessions.py
  - lib/sync.py
  - lib/test_capture.py
  - lib/trigger.py
  - prism
  - templates/constitution.md
findings:
  critical: 2
  warning: 8
  info: 5
  total: 15
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-14T15:30:00Z
**Depth:** standard
**Files Reviewed:** 22
**Status:** issues_found

## Summary

The Prism foundation layer is well-structured with good defensive programming throughout -- swallowed exceptions in the capture path, atomic file operations with locking, and secret scrubbing on all observation payloads. The codebase follows its own zero-dependency constraint rigorously (stdlib only).

Two critical issues were found: a file descriptor leak in the background spawn function (`capture.py` and `trigger.py`), and `fcntl` usage in `index.py` which is not available on Windows (minor portability concern, but the project currently targets macOS/Linux). Eight warnings cover missing error handling, unclosed file handles, a race condition in lock acquisition, and validation gaps. Five informational items note code quality improvements.

## Critical Issues

### CR-01: File descriptor leak in `_spawn_background` (capture.py)

**File:** `lib/capture.py:217-222`
**Issue:** `devnull = open(os.devnull, "w")` opens a file descriptor that is never closed. Because `_spawn_background` is called from the hot capture path (every tool use), this leaks one fd per trigger invocation. The `Popen` object also holds a reference but the fd is never explicitly closed after process creation. Over many observations, this can exhaust file descriptors.
**Fix:**
```python
def _spawn_background(prism_home: Path, args: list) -> None:
    """Spawn a background prism command. Non-blocking, fire-and-forget."""
    import shutil
    import subprocess

    prism_cli = shutil.which("prism")
    if not prism_cli:
        candidate = prism_home / "prism"
        if candidate.exists():
            prism_cli = str(candidate)

    if not prism_cli:
        return

    try:
        devnull = open(os.devnull, "w")
        try:
            subprocess.Popen(
                [sys.executable, prism_cli] + args,
                stdout=devnull,
                stderr=devnull,
                start_new_session=True,
            )
        except OSError:
            pass
        finally:
            devnull.close()
    except OSError:
        pass
```

Alternatively, use `subprocess.DEVNULL` which avoids opening a file descriptor entirely:
```python
subprocess.Popen(
    [sys.executable, prism_cli] + args,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
```

### CR-02: Identical file descriptor leak in `trigger.py`

**File:** `lib/trigger.py:51-57`
**Issue:** Same pattern as CR-01. `devnull = open(os.devnull, "w")` is opened but never closed.
**Fix:** Use `subprocess.DEVNULL` instead:
```python
subprocess.Popen(
    [sys.executable, prism_cli, "extract", "--project", project_id],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
)
```

## Warnings

### WR-01: Race condition between stale lock check and lock acquisition in extraction

**File:** `lib/extract.py:46-58`
**Issue:** Between the stale lock check (`lock.exists()` + `lock.unlink()` on line 50) and the atomic lock creation (`os.open` with `O_CREAT | O_EXCL` on line 54), another process could create the lock file. The `unlink` + `open(EXCL)` sequence is not atomic. While the `O_EXCL` flag will correctly prevent double-acquisition (the second process would get `FileExistsError`), the stale lock removal itself can race: two processes could both see the stale lock, both try to unlink it (one succeeds, one gets `FileNotFoundError` which is unhandled), and then both try to acquire.
**Fix:** Wrap the stale lock removal in a try/except for `FileNotFoundError`:
```python
if lock.exists():
    age_seconds = time.time() - lock.stat().st_mtime
    if age_seconds > 600:
        print(f"Removing stale lock ({int(age_seconds)}s old).")
        try:
            lock.unlink()
        except FileNotFoundError:
            pass  # Another process already cleaned it up
```

### WR-02: Unclosed file handle in `cmd_status`

**File:** `lib/commands.py:237`
**Issue:** `sum(1 for _ in open(obs_path))` opens a file handle inside a generator expression without ever closing it. While CPython's reference counting will collect it promptly, this is a resource leak in other Python implementations (PyPy, etc.) and violates the project's own careful coding patterns elsewhere.
**Fix:**
```python
if obs_path.exists():
    with open(obs_path) as f:
        obs_count = sum(1 for _ in f)
    print(f"\nPending observations: {obs_count}")
```

### WR-03: MCP server does not handle `notifications/initialized` message

**File:** `lib/mcp_server.py:299-348`
**Issue:** Per the MCP 2025-03-26 spec, after the `initialize` response, the client sends a `notifications/initialized` notification (no `id` field). The current code handles notifications by returning `None` (line 306), which is correct for not responding. However, the server does not send an `initialized` notification back, nor does it track initialization state. More importantly, if the client sends any method before `initialize`, the server will still process it. While this works in practice with Claude Code, it violates the spec's initialization handshake requirement.
**Fix:** Add state tracking:
```python
_initialized = False

def _handle_message(msg):
    global _initialized
    method = msg.get("method")
    msg_id = msg.get("id")

    if msg_id is None:
        if method == "notifications/initialized":
            _initialized = True
        return None

    if method == "initialize":
        _initialized = True
        # ... existing initialize handling ...
```

### WR-04: `_relevant` function passes unexpected keyword argument to `list_entries`

**File:** `lib/mcp_server.py:119-126`
**Issue:** The `_relevant` function builds a `filters` dict with `filters["kind"] = None` (line 122), then passes `**filters` to `list_entries()`. The `list_entries` function in `index.py` checks `if kind:` on line 113, which is falsy for `None`, so this happens to work. However, `filters["project_id"]` is set on line 125, but the dict may also contain `"kind": None`. Passing `kind=None` explicitly is confusing and fragile -- if `list_entries` ever changes to check `kind is not None` instead of truthiness, this breaks silently.
**Fix:** Only add keys to `filters` when they have meaningful values:
```python
filters = {}
if project_id:
    filters["project_id"] = project_id
entries = list_entries(**filters)
```

### WR-05: Double `.gitignore` read in `_update_gitignore`

**File:** `lib/commands.py:170-180`
**Issue:** On line 170-171, the gitignore file is read into `existing_lines`. On line 176, `gitignore_path.read_text()` is called again (and potentially a third time on the same line). This is wasteful and introduces a TOCTOU issue where the file could change between reads. More critically, the logic `if existing_lines and gitignore_path.read_text() and not gitignore_path.read_text().endswith("\n")` reads the file twice in one expression, which is both a performance issue and could yield inconsistent results if another process modifies the file between reads.
**Fix:**
```python
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

### WR-06: Extraction pipeline grants Bash tool access to the validator subprocess

**File:** `lib/extract.py:176`
**Issue:** The validation phase (`_phase2_validate`) passes `--allowedTools Read,Write,Edit,Glob,Grep,Bash` to the `claude` CLI. Granting `Bash` tool access to an AI-driven validation subprocess is a security concern -- a malicious candidate entry could trick the validator into executing arbitrary shell commands. The extractor phase (line 114) correctly omits `Bash` from its allowed tools.
**Fix:** Remove `Bash` from the allowed tools for the validator:
```python
["claude", "--print", "--model", "sonnet", "-p", prompt,
 "--allowedTools", "Read,Write,Edit,Glob,Grep"],
```

### WR-07: `_apply_validation_results` re-adds all existing entries to the index on every extraction

**File:** `lib/extract.py:231-239`
**Issue:** `_apply_validation_results` globs all `*.md` files in the engrams directory and calls `add_entry()` for each one. `add_entry()` does a load-index, filter, append, save-index cycle for every single file. This means if there are 20 existing entries, the index is loaded and saved 20 times. Each save acquires a lock, writes to temp, syncs, and renames. This is both slow and causes unnecessary I/O churn. It also re-adds entries that were already in the index, resetting their `last_observed` date to today (via `build_index_entry`), which corrupts confidence decay calculations.
**Fix:** Only add entries that are new (not already in the index), or batch the updates:
```python
def _apply_validation_results(project_id: str, results: dict) -> None:
    engrams_dir = get_engrams_dir(project_id)
    index = load_index()  # Load once
    existing_ids = {e["id"] for e in index["engrams"]}

    for entry_file in engrams_dir.glob("*.md"):
        entry = _parse_frontmatter(entry_file, project_id)
        if entry and entry["id"] not in existing_ids:
            index["engrams"].append(entry)
            existing_ids.add(entry["id"])

    # Handle deprecations
    for decision in results.get("decisions", []):
        for deprecated_id in decision.get("deprecates", []):
            index["engrams"] = [e for e in index["engrams"] if e["id"] != deprecated_id]

    save_index(index)  # Save once

    _rotate_observations(project_id)
```

### WR-08: Session transcript folder name derivation uses naive hyphen replacement

**File:** `lib/sessions.py:120-122`
**Issue:** When `cwd` cannot be extracted from the session file, the code derives it from the folder name by replacing hyphens with slashes: `cwd = folder.name.replace("-", "/")`. This is a lossy heuristic -- directory names that legitimately contain hyphens (e.g., `my-project`) will be incorrectly converted to paths with slashes (`my/project`). Claude Code's folder naming scheme encodes the full path, so paths like `/Users/gaurav/codes/my-project` become `-Users-gaurav-codes-my-project`, and the leading hyphen becomes a leading slash. But the replacement makes `/Users/gaurav/codes/my/project` which is wrong.
**Fix:** This heuristic is inherently lossy. At minimum, add a comment documenting the limitation. A more robust approach would be to verify the derived path exists:
```python
cwd = folder.name.replace("-", "/")
if not cwd.startswith("/"):
    cwd = "/" + cwd
# Validate the derived path exists
if not os.path.isdir(cwd):
    cwd = ""  # Fall back to unknown
```

## Info

### IN-01: `__init__.py` is empty

**File:** `lib/__init__.py:1`
**Issue:** The `lib/__init__.py` file contains only a blank line. This is fine for a namespace package, but adding a version string or brief docstring would improve introspection.
**Fix:** Add a module docstring:
```python
"""Prism library - zero-dependency knowledge layer for Claude Code."""
```

### IN-02: Duplicate sorting logic in `_collect_entries`

**File:** `lib/sync.py:216-228`
**Issue:** The entries list is sorted twice with overlapping criteria. The first sort (line 216) sorts by pinned descending, confidence descending, and last_observed. The second sort (line 223) re-sorts by pinned first, then confidence descending, which undoes the last_observed tiebreaker from the first sort. One sort is sufficient.
**Fix:** Keep only the second sort which captures the desired behavior, or merge both into one:
```python
entries.sort(key=lambda e: (
    not e.get("pinned", False),
    -e.get("confidence", 0),
    e.get("last_observed", ""),  # tiebreaker: older first for same confidence
))
```

### IN-03: Commented-out-style Prism comment marker pattern in `.gitignore` updates

**File:** `lib/commands.py:178`
**Issue:** The `_update_gitignore` function adds a `# Prism (auto-generated, machine-specific)` comment every time new entries need to be added, without checking if the comment block already exists. Running `prism init` multiple times with different entries missing from gitignore will produce duplicate comment blocks.
**Fix:** Check for existing comment before adding:
```python
if to_add:
    with open(gitignore_path, "a") as f:
        if existing_content and not existing_content.endswith("\n"):
            f.write("\n")
        if "# Prism (auto-generated" not in existing_content:
            f.write("# Prism (auto-generated, machine-specific)\n")
        for entry in to_add:
            f.write(entry + "\n")
```

### IN-04: `_read_entry_steps` function in `sync.py` is defined but never called

**File:** `lib/sync.py:264-290`
**Issue:** The `_read_entry_steps` function is defined but not referenced anywhere in the codebase. This is dead code, likely planned for procedure rendering in context files.
**Fix:** Remove the function or add a `# TODO: used in future procedure rendering` comment.

### IN-05: `prism` CLI wrapper always invokes via `__main__` guard

**File:** `prism:1-10`
**Issue:** The `prism` CLI wrapper imports `main` from `lib.cli` but only calls it inside `if __name__ == "__main__"`. When invoked via `python3 prism`, `__name__` is `"__main__"` so this works. However, when `_spawn_background` runs `[sys.executable, prism_cli]`, this also works because Python executes the file as `__main__`. The pattern is correct but worth noting: the `main()` call at module level (without the guard) would also work since this file is always meant to be the entry point.
**Fix:** No change needed -- current pattern is correct. Informational only.

---

_Reviewed: 2026-04-14T15:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
