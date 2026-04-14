---
phase: 04-registry
reviewed: 2026-04-14T12:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - install.sh
  - lib/cli.py
  - lib/commands.py
  - lib/registry.py
  - skills/advise-skills/SKILL.md
  - skills/audit-code/SKILL.md
  - skills/publish-skills/SKILL.md
  - templates/registry/README.md
  - templates/registry/ci/build-registry.yml
  - templates/registry/ci/validate-pr.yml
  - templates/registry/schemas/plugin.schema.json
  - templates/registry/scripts/build_registry.py
  - templates/registry/scripts/validate.py
  - templates/registry/worker/package.json
  - templates/registry/worker/src/index.ts
  - templates/registry/worker/tsconfig.json
  - templates/registry/worker/wrangler.toml
findings:
  critical: 3
  warning: 6
  info: 3
  total: 12
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-04-14T12:00:00Z
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Reviewed the Phase 4 registry implementation across the CLI (`lib/registry.py`, `lib/cli.py`, `lib/commands.py`), installer, Cloudflare Worker (`templates/registry/worker/src/index.ts`), CI scripts, and skill definitions. The code is well-structured overall with good patterns (atomic writes, cache TTL, multi-registry merge, delta tracking). However, there are three critical security issues: path traversal in the Worker's `/file/` endpoint, a timing-attack-vulnerable token comparison, and a TOCTOU race on temp file permissions. There are also several warnings around file handle leaks, name validation bypass, and missing input sanitization.

## Critical Issues

### CR-01: Path Traversal in Worker `/file/` Endpoint

**File:** `templates/registry/worker/src/index.ts:310-313`
**Issue:** The `/file/*` endpoint passes user-controlled input directly to `fetchFromGitHub()` without sanitizing path traversal sequences. An authenticated attacker can send `GET /file/../../../etc/passwd` or `GET /file/../../other-repo-secrets`. While GitHub's Contents API scopes to the repo, paths like `../` or encoded variants could be used to access unexpected files within the repo (e.g., `.github/workflows/` secrets in workflow files, or the `.git/` directory via certain API behaviors).
**Fix:**
```typescript
// GET /file/* -- generic file proxy (for fetching specific skill files)
if (path.startsWith("/file/") && request.method === "GET") {
  const filePath = decodeURIComponent(path.replace("/file/", ""));
  if (!filePath) return badRequest("File path required");

  // Sanitize: reject path traversal attempts
  if (filePath.includes("..") || filePath.startsWith("/") || filePath.includes("//")) {
    return badRequest("Invalid file path");
  }

  // Restrict to skills/ directory only
  if (!filePath.startsWith("skills/")) {
    return badRequest("File access restricted to skills/ directory");
  }

  const resp = await fetchFromGitHub(env, filePath);
  // ...
}
```

### CR-02: Timing-Attack-Vulnerable Token Comparison

**File:** `templates/registry/worker/src/index.ts:47-54`
**Issue:** The `authenticate()` function uses `Array.includes()` for token comparison, which relies on JavaScript's `===` string comparison. This is not constant-time and is vulnerable to timing side-channel attacks. An attacker can measure response times to brute-force the token character by character. While Workers have some timing noise, this is a well-known security anti-pattern for secret comparison.
**Fix:**
```typescript
/** Constant-time string comparison */
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) {
    // Compare against dummy to avoid leaking length info via timing
    b = a;
  }
  let result = a.length ^ b.length; // will be non-zero if lengths differ
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return result === 0;
}

function authenticate(request: Request, env: Env): boolean {
  const authHeader = request.headers.get("Authorization");
  if (!authHeader) return false;

  const token = authHeader.replace("Bearer ", "").trim();
  const validTokens = env.REGISTRY_TOKENS.split(",").map((t) => t.trim());
  return validTokens.some((valid) => timingSafeEqual(token, valid));
}
```

### CR-03: TOCTOU Race on Temp File Permissions in `save_registries()`

**File:** `lib/registry.py:73-78`
**Issue:** The temp file is created with default permissions (typically 0o644), then `os.rename()` moves it to the final path, and only then `os.chmod()` restricts to 0o600. Between `rename` and `chmod`, the file containing plaintext API tokens is world-readable. On multi-user systems, another process could read the tokens during this window. Additionally, the temp file itself is world-readable during its entire lifetime.
**Fix:**
```python
def save_registries(data: dict) -> None:
    """Atomic write of registries.json with 0o600 permissions (T-04-01)."""
    REGISTRIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Use os.open with restrictive permissions from the start
    tmp = str(REGISTRIES_PATH) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.rename(tmp, str(REGISTRIES_PATH))
    except Exception:
        os.unlink(tmp)
        raise
```

## Warnings

### WR-01: File Handle Leak in `cmd_status()`

**File:** `lib/commands.py:238`
**Issue:** `open(obs_path)` is called without a context manager (`with` statement). The file handle is never explicitly closed, relying on garbage collection. On CPython this usually works, but on other Python implementations (PyPy), the handle may remain open indefinitely.
**Fix:**
```python
with open(obs_path) as f:
    obs_count = sum(1 for _ in f)
```

### WR-02: Registry Name Validation Allows Single-Character Names Through Without Full Check

**File:** `lib/registry.py:87-97`
**Issue:** The validation logic has a convoluted structure that allows single-character alphanumeric names (e.g., `"a"`) to pass validation even though the regex `_NAME_RE` requires at least 2 characters (`^[a-z0-9][a-z0-9-]*[a-z0-9]$`). More critically, the outer `if not name` check means an empty string `""` passes the first condition (triggering the error) but the logic flow is confusing and the empty-string case is not handled cleanly -- `not name` is True for `""`, so it enters the block, but then `len(name) == 1` is False and `len(name) > 1` is False, so neither inner branch raises ValueError, and execution falls through to `load_registries()` with an empty-string name.
**Fix:**
```python
def add_registry(name: str, url: str, token: str = "", writable: bool = True) -> None:
    if not name:
        raise ValueError("Registry name is required.")
    # Allow single-char alphanumeric names; require kebab-case for multi-char
    if len(name) == 1:
        if not name.isalnum():
            raise ValueError(
                f"Invalid registry name '{name}'. Must be alphanumeric."
            )
    elif not _NAME_RE.match(name):
        raise ValueError(
            f"Invalid registry name '{name}'. Use kebab-case: [a-z0-9][a-z0-9-]*[a-z0-9]"
        )
    # ... rest of function
```

### WR-03: Worker `authenticate()` Parses `Authorization` Header Incorrectly

**File:** `templates/registry/worker/src/index.ts:51`
**Issue:** `authHeader.replace("Bearer ", "")` only replaces the first occurrence. If a malicious client sends `Authorization: Bearer Bearer actual_token`, the result would be `"Bearer actual_token"` which would fail auth. More importantly, `replace("Bearer ", "")` is case-sensitive and does not handle `bearer ` (lowercase) which some HTTP clients might send. The header value should be parsed with a proper prefix check.
**Fix:**
```typescript
const token = authHeader.replace(/^Bearer\s+/i, "").trim();
if (!token) return false;
```

### WR-04: Worker Skill Name Regex Rejects Single-Segment Names

**File:** `templates/registry/worker/src/index.ts:218-219`
**Issue:** The regex `/^[a-z0-9][a-z0-9-]*[a-z0-9]$/` requires at least 2 characters, but also note the schema's `plugin.schema.json` uses `^[a-z][a-z0-9]*(-[a-z0-9]+)+$` which requires at least one hyphen (2+ words). These two regexes are inconsistent -- the Worker is more permissive than the schema. A name like `"ab"` passes the Worker but fails schema validation, meaning it would be accepted by the Worker API but then fail CI validation, creating a confusing failure mode.
**Fix:** Align the Worker validation regex with the schema:
```typescript
if (!/^[a-z][a-z0-9]*(-[a-z0-9]+)+$/.test(s.name)) {
  return { ok: false, error: `${p}'${s.name}' must be kebab-case with at least two words (e.g., 'retry-backoff')` };
}
```

### WR-05: `build_registry.py` Does Not Validate Required Fields Before Accessing Them

**File:** `templates/registry/scripts/build_registry.py:43-53`
**Issue:** After loading `plugin.json`, the script accesses `plugin["name"]`, `plugin["description"]`, etc. without checking they exist. If a `plugin.json` passes the JSON parse but lacks required keys (e.g., a minimal `{}`), this crashes with a `KeyError`. The `validate.py` script runs in CI on PRs, but `build_registry.py` runs on merge to main -- if validation is skipped (e.g., direct push), the build script will crash.
**Fix:**
```python
required = ["name", "description", "author", "repository"]
missing = [k for k in required if k not in plugin]
if missing:
    errors.append(f"{label}: missing required fields: {', '.join(missing)}")
    continue

skills.append({
    "name": plugin["name"],
    # ...
})
```

### WR-06: `PrismPublishRequest` Interface Has Required `repository` Field But Validation Derives It

**File:** `templates/registry/worker/src/index.ts:186-190`
**Issue:** The `PrismPublishRequest` interface declares `repository: string` as a top-level field, but the `validatePrismPublish` function extracts `repository` from the first skill's `repository` field (line 243: `const repository = [...repos][0]`). The publish handler then uses `data.repository` (line 369) but the `repository` variable from destructuring shadows any potential issue. The `body.repository` top-level field is never read or validated, and the README's example payload does not include it at the top level either. The interface definition is misleading and the extracted `repository` is unused (the handler uses `skill.repository` directly on line 374). This is dead code that masks the actual data flow.
**Fix:** Remove `repository` from the interface since it's derived, or document clearly that it's extracted from skills:
```typescript
interface PrismPublishRequest {
  skills: PrismSkillPayload[];
  description: string;
  repository: string;  // derived from skills[0].repository
}
```

## Info

### IN-01: Bare `except: pass` in Skill SKILL.md Python Snippets

**File:** `skills/advise-skills/SKILL.md:49,67,93` and `skills/audit-code/SKILL.md:49,67,93`
**Issue:** The inline Python scripts in the SKILL.md files use bare `except: pass` which silences all exceptions including `KeyboardInterrupt` and `SystemExit`. While these are shell-embedded scripts meant for transient use, they set a poor example.
**Fix:** Use `except Exception: pass` instead of bare `except: pass`.

### IN-02: `cmd_registry_create()` Assumes Workers.dev Subdomain Pattern

**File:** `lib/registry.py:425`
**Issue:** The wizard auto-registers the URL as `https://{name}.workers.dev` which assumes the Cloudflare Worker will be deployed with the same name as the registry. This may not match the actual Worker name or custom domain. The wizard does print "Update the URL after deploying" (line 434), but auto-registering a likely-wrong URL could cause confusion.
**Fix:** Consider not auto-registering, or prompting the user for the actual URL after deployment. At minimum, make the auto-registered URL more clearly provisional.

### IN-03: Unused `branchLabel` Parameter in `createPullRequest()`

**File:** `templates/registry/worker/src/index.ts:78`
**Issue:** The `branchLabel` parameter is passed to `createPullRequest()` but never used in the function body. The branch name is generated from `Date.now()` on line 83 instead.
**Fix:** Remove the unused parameter or use it in the branch name generation:
```typescript
async function createPullRequest(
  env: Env,
  files: { path: string; content: string }[],
  title: string,
  description: string
): Promise<Response> {
```

---

_Reviewed: 2026-04-14T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
