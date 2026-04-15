---
phase: 04-registry
fixed_at: 2026-04-14T12:30:00Z
review_path: .planning/phases/04-registry/04-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-04-14T12:30:00Z
**Source review:** .planning/phases/04-registry/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9
- Fixed: 9
- Skipped: 0

## Fixed Issues

### CR-01: Path Traversal in Worker `/file/` Endpoint

**Files modified:** `templates/registry/worker/src/index.ts`
**Commit:** 57b0dc1
**Applied fix:** Added `decodeURIComponent()` for path decoding, path traversal rejection (blocks `..`, leading `/`, double `//`), and restriction to `skills/` directory only. Unauthenticated file access outside the skills tree is now impossible.

### CR-02: Timing-Attack-Vulnerable Token Comparison

**Files modified:** `templates/registry/worker/src/index.ts`
**Commit:** d920ff3
**Applied fix:** Added `timingSafeEqual()` function that performs constant-time XOR comparison of strings. Replaced `Array.includes()` in `authenticate()` with `Array.some()` using `timingSafeEqual()`. Length differences are handled by comparing against a dummy to avoid leaking length info via timing.

### CR-03: TOCTOU Race on Temp File Permissions in `save_registries()`

**Files modified:** `lib/registry.py`
**Commit:** aec410f
**Applied fix:** Replaced `open(tmp, "w")` + post-rename `os.chmod()` with `os.open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0o600)` + `os.fdopen(fd, "w")`. The temp file is now created with 0o600 permissions from the start, eliminating the window where tokens were world-readable. Added try/except to clean up temp file on failure.

### WR-01: File Handle Leak in `cmd_status()`

**Files modified:** `lib/commands.py`
**Commit:** 1925539
**Applied fix:** Wrapped bare `open(obs_path)` in a `with` context manager so the file handle is explicitly closed after counting lines.

### WR-02: Registry Name Validation Allows Single-Character Names Through Without Full Check

**Files modified:** `lib/registry.py`
**Commit:** fe7224b
**Applied fix:** Rewrote the validation logic in `add_registry()` to have clear, non-overlapping branches: empty string raises immediately, single-char validates alphanumeric only, multi-char validates against `_NAME_RE`. The previous convoluted nested-if structure allowed empty strings to fall through without raising an error.

### WR-03: Worker `authenticate()` Parses `Authorization` Header Incorrectly

**Files modified:** `templates/registry/worker/src/index.ts`
**Commit:** 6f5cada
**Applied fix:** Replaced `authHeader.replace("Bearer ", "")` with `authHeader.replace(/^Bearer\s+/i, "")` which is case-insensitive, anchored to start, and handles variable whitespace. Added early return if token is empty after stripping.

### WR-04: Worker Skill Name Regex Rejects Single-Segment Names

**Files modified:** `templates/registry/worker/src/index.ts`
**Commit:** 9d53f58
**Applied fix:** Changed Worker validation regex from `/^[a-z0-9][a-z0-9-]*[a-z0-9]$/` to `/^[a-z][a-z0-9]*(-[a-z0-9]+)+$/` to match `plugin.schema.json`. This ensures names accepted by the Worker API will also pass CI schema validation, preventing confusing failure modes.

### WR-05: `build_registry.py` Does Not Validate Required Fields Before Accessing Them

**Files modified:** `templates/registry/scripts/build_registry.py`
**Commit:** a6db7ff
**Applied fix:** Added validation of required fields (`name`, `description`, `author`, `repository`) before accessing them. Missing fields are reported as errors and the skill is skipped, preventing `KeyError` crashes on malformed `plugin.json` files that bypass PR validation.

### WR-06: `PrismPublishRequest` Interface Has Required `repository` Field But Validation Derives It

**Files modified:** `templates/registry/worker/src/index.ts`
**Commit:** 2415dab
**Applied fix:** Added clarifying comment to the `repository` field in `PrismPublishRequest` interface documenting that it is derived from `skills[0].repository` by `validatePrismPublish`, not provided by the client.

## Skipped Issues

None -- all findings were fixed.

---

_Fixed: 2026-04-14T12:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
