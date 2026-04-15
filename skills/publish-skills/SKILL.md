---
name: publish-skills
description: Publish changed skills from _analysis/extracted_skills_codebase/ and _analysis/extracted_skills_history/ to the Prism registry via the Worker API with delta tracking. Only publishes skills whose content has changed since last publish unless --all is specified.
---

## When to use this skill

Use when the user wants to publish extracted or promoted skills to a Prism skill registry. Invoked as `/publish-skills`, optionally with flags: `--all` (publish everything regardless of delta state) or `--registry NAME` (target a named registry).

## Prerequisites

- Skills must exist in `_analysis/extracted_skills_codebase/` (created by `/extract-skills` or `prism promote`) and/or `_analysis/extracted_skills_history/` (created by `/run-history-pipeline`)
- Each skill directory must contain both `plugin.json` and `SKILL.md`
- A registry must be configured in `~/.prism/registries.json` (or legacy `~/.prism/config.json`)
- The `REGISTRY_TOKEN` environment variable or per-registry token in `registries.json` must be available

## Flags

| Flag | Effect |
|------|--------|
| `--all` | Publish all valid skills, ignoring delta state (force republish) |
| `--registry NAME` | Target a specific named registry from `registries.json`. If omitted, uses the default registry. The target must have `writable: true`. |

## Instructions

### Step 1 -- Resolve target registry

Resolve the target registry from `~/.prism/registries.json` (with fallback to legacy `~/.prism/config.json`). If `--registry NAME` was specified, use that name; otherwise use the default registry.

```python
python3 -c "
import json, os, sys
reg_path = os.path.expanduser('~/.prism/registries.json')
try:
    with open(reg_path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {'registries': [], 'default': None}
# Fall back to config.json migration
if not data.get('registries'):
    cfg_path = os.path.expanduser('~/.prism/config.json')
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
        url = cfg.get('registry_url', '')
        if url:
            print(json.dumps({'name': 'default', 'url': url, 'token': '', 'writable': True}))
            sys.exit(0)
    except: pass
    print('NOT_CONFIGURED')
    sys.exit(0)
# Resolve target: --registry NAME or default
target_name = None  # <-- set to registry name if --registry flag was provided
if target_name is None:
    target_name = data.get('default')
if not target_name:
    print('NO_DEFAULT')
    sys.exit(0)
for reg in data['registries']:
    if reg['name'] == target_name:
        if not reg.get('writable', True):
            print('READ_ONLY:' + target_name)
            sys.exit(0)
        print(json.dumps(reg))
        sys.exit(0)
print('NOT_FOUND:' + str(target_name))
"
```

If `--registry NAME` flag was provided, set `target_name` to that registry name in the script above.

Handle output:
- `NOT_CONFIGURED` -> tell user to run `prism registry add`
- `NO_DEFAULT` -> tell user to run `prism registry default NAME`
- `READ_ONLY:name` -> tell user the registry is read-only, cannot publish
- `NOT_FOUND:name` -> registry not found in registries.json

If the result is valid JSON, extract the `name`, `url`, and `token` fields from the JSON result. Resolve the final API token:
1. Check `REGISTRY_TOKEN` environment variable (backward compat, takes precedence)
2. If not set, use the `token` field from the resolved registry entry

Store the resolved token for use in Step 4. If both sources are empty, tell the user:

> **No API token found.** Set the `REGISTRY_TOKEN` environment variable or add a token to your registry:
> ```
> prism registry add NAME --url URL --token YOUR_TOKEN
> ```
> Or generate one: `prism registry token create NAME`

Then stop.

### Step 2 -- Discover valid skills

Scan both `_analysis/extracted_skills_codebase/` (from `/extract-skills` and `prism promote`) and `_analysis/extracted_skills_history/` (from `/run-history-pipeline`) for skill directories. Each valid skill directory must contain both `plugin.json` and `SKILL.md`.

```bash
for base_dir in _analysis/extracted_skills_codebase _analysis/extracted_skills_history; do
    [ -d "$base_dir" ] || continue
    for dir in "$base_dir"/*/; do
        [ -d "$dir" ] || continue
        if [ -f "$dir/plugin.json" ] && [ -f "$dir/SKILL.md" ]; then
            echo "VALID: $dir"
        else
            echo "SKIP (missing files): $dir"
        fi
    done
done
```

For each valid skill, read `plugin.json` and verify it has the required fields: `name`, `description`, `author`, `repository`, `category`, `source`, `commit_date`, `source_hash`.

```python
python3 << 'PYEOF'
import json, os, sys

required_fields = ["name", "description", "author", "repository", "category", "source", "commit_date", "source_hash"]
base_dirs = [
    "_analysis/extracted_skills_codebase",
    "_analysis/extracted_skills_history",
]

valid = []   # list of (skill_name, skill_dir)
invalid = []
seen_names = set()

for base in base_dirs:
    if not os.path.isdir(base):
        continue
    for skill_name in sorted(os.listdir(base)):
        skill_dir = os.path.join(base, skill_name)
        if not os.path.isdir(skill_dir):
            continue
        if skill_name in seen_names:
            print(f"SKIP (duplicate name, keeping first): {skill_dir}")
            continue
        plugin_path = os.path.join(skill_dir, "plugin.json")
        skillmd_path = os.path.join(skill_dir, "SKILL.md")
        if not (os.path.isfile(plugin_path) and os.path.isfile(skillmd_path)):
            invalid.append((skill_dir, "missing plugin.json or SKILL.md"))
            continue
        try:
            with open(plugin_path) as f:
                plugin = json.load(f)
            missing = [fld for fld in required_fields if fld not in plugin]
            if missing:
                invalid.append((skill_dir, f"missing fields: {', '.join(missing)}"))
            else:
                valid.append((skill_name, skill_dir))
                seen_names.add(skill_name)
        except (json.JSONDecodeError, OSError) as e:
            invalid.append((skill_dir, str(e)))

print(f"Found {len(valid)} valid skill(s):")
for name, path in valid:
    print(f"  - {name} ({path})")
if invalid:
    print(f"\nSkipped {len(invalid)} invalid skill(s):")
    for path, reason in invalid:
        print(f"  - {path}: {reason}")
if not valid:
    print("\nNo valid skills to publish.")
    sys.exit(1)
PYEOF
```

If no valid skills found, tell the user and stop.

### Step 3 -- Delta tracking (compute content hashes)

Read `_analysis/.published.json` if it exists. If it does not exist, start with an empty dict `{}`.

For each valid skill, compute a content hash: SHA256 of `plugin.json` bytes concatenated with `SKILL.md` bytes, then take the first 12 hex characters.

```python
python3 << 'PYEOF'
import hashlib, json, os

published_path = "_analysis/.published.json"

# Load existing published state
if os.path.isfile(published_path):
    with open(published_path) as f:
        published = json.load(f)
else:
    published = {}

# Compute hashes for all valid skills (list of (skill_name, skill_dir) from Step 2)
VALID_SKILLS = []  # <-- fill from Step 2 results as (skill_name, skill_dir) tuples

for skill_name, skill_dir in VALID_SKILLS:
    h = hashlib.sha256()
    for filename in ["plugin.json", "SKILL.md"]:
        filepath = os.path.join(skill_dir, filename)
        with open(filepath, "rb") as f:
            h.update(f.read())
    content_hash = h.hexdigest()[:12]

    # Check against published state for the target registry name
    registry_name = ""  # <-- set to resolved registry name from Step 1
    prev = published.get(skill_name, {}).get(registry_name, {})
    prev_hash = prev.get("content_hash", "")

    if content_hash == prev_hash:
        print(f"UNCHANGED: {skill_name} (hash: {content_hash})")
    else:
        print(f"CHANGED: {skill_name} (hash: {content_hash}, prev: {prev_hash or 'none'})")
PYEOF
```

**If `--all` flag was specified:** Skip the delta comparison entirely. Mark all valid skills for publishing.

**Otherwise:** Only include skills where the content hash differs from the `.published.json` entry for the `"default"` registry, or where no entry exists.

If all skills are unchanged and `--all` was not specified, tell the user:

> **All skills up to date.** Use `--all` to force republish.

Then stop.

### Step 4 -- Publish to registry

Build the request payload and POST to the registry Worker API. Use Python for the HTTP call (not curl/jq) to handle JSON encoding of SKILL.md content with special characters correctly.

```python
python3 << 'PYEOF'
import json, os, urllib.request, urllib.error

# Configuration (filled from Steps 1-3)
REGISTRY_URL = ""       # <-- from Step 1
TOKEN = ""              # <-- resolved token from Step 1 (REGISTRY_TOKEN env var or registry entry token)
SKILLS_TO_PUBLISH = []  # <-- list of (skill_name, skill_dir) from Step 3

skills_payload = []
for skill_name, skill_dir in SKILLS_TO_PUBLISH:
    with open(os.path.join(skill_dir, "plugin.json")) as f:
        plugin = json.load(f)
    with open(os.path.join(skill_dir, "SKILL.md")) as f:
        content = f.read()

    skills_payload.append({
        "name": plugin["name"],
        "description": plugin["description"],
        "author": plugin["author"],
        "repository": plugin["repository"],
        "category": plugin["category"],
        "source": plugin["source"],
        "commit_date": plugin["commit_date"],
        "source_hash": plugin["source_hash"],
        "content": content,
    })

payload = json.dumps({"skills": skills_payload}).encode("utf-8")

req = urllib.request.Request(
    f"{REGISTRY_URL}/api/skills/publish",
    data=payload,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Prism/1.0",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print(f"HTTP {resp.status}: Published {result.get('published', len(skills_payload))} skill(s)")
        if result.get("errors"):
            for err in result["errors"]:
                print(f"  Error: {err}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"HTTP {e.code}: {body}")
    if e.code in (401, 403):
        print("Registry authentication failed. Check your token (REGISTRY_TOKEN env var or registry entry).")
except urllib.error.URLError as e:
    print(f"Connection failed: {e.reason}")
    print(f"Check that registry_url is correct: {REGISTRY_URL}")
PYEOF
```

**Important:**
- The API endpoint is `POST {registry_url}/api/skills/publish`
- Auth header: `Authorization: Bearer {TOKEN}` (resolved token from Step 1)
- Include `User-Agent: Prism/1.0` to avoid Cloudflare bot detection
- The `content` field contains the raw SKILL.md text (not base64 encoded)
- All skills in a batch should have the same `repository` value

### Step 5 -- Update delta tracking

After a successful publish (HTTP 2xx), update `_analysis/.published.json` with the new content hashes and timestamps. Write atomically using a temp file and rename.

```python
python3 << 'PYEOF'
import json, os, hashlib
from datetime import datetime, timezone

published_path = "_analysis/.published.json"
tmp_path = "_analysis/.published.json.tmp"

# Load existing state
if os.path.isfile(published_path):
    with open(published_path) as f:
        published = json.load(f)
else:
    published = {}

# Update entries for each published skill
PUBLISHED_SKILLS = []  # <-- list of (skill_name, content_hash) from Steps 3-4

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

REGISTRY_NAME = ""  # <-- set to resolved registry name from Step 1

for skill_name, content_hash in PUBLISHED_SKILLS:
    if skill_name not in published:
        published[skill_name] = {}
    published[skill_name][REGISTRY_NAME] = {
        "published_at": now,
        "content_hash": content_hash,
    }

# Atomic write: write to .tmp then rename
with open(tmp_path, "w") as f:
    json.dump(published, f, indent=2)
    f.write("\n")
os.rename(tmp_path, published_path)

print(f"Updated {published_path} with {len(PUBLISHED_SKILLS)} entry/entries")
PYEOF
```

### Step 6 -- Summary

Print a summary of the publish operation:

```
Published {N} skill(s) to {registry_url}
Skipped {M} skill(s) (unchanged)
Failed {F} skill(s)
```

- If any skills were published: `"Published {N} skills to {registry_url}"`
- If all skills were unchanged: `"All skills up to date. Use --all to force republish."`
- If there were failures: list each failed skill name and error

### .published.json format reference

The delta tracking file at `_analysis/.published.json` has this structure:

```json
{
  "skill-name": {
    "default": {
      "published_at": "2026-04-14T12:00:00Z",
      "content_hash": "a1b2c3d4e5f6"
    }
  }
}
```

- Top-level keys are skill names
- Second-level keys are registry names (e.g., `"team"`, `"community"`, or `"default"` for legacy/migrated registries)
- `content_hash` is the first 12 hex characters of SHA256(`plugin.json` bytes + `SKILL.md` bytes)
- `published_at` is the UTC timestamp of the last successful publish

## Important differences from previous approaches

- **Worker-only publishing** -- skills are published via the registry Worker API (`POST /api/skills/publish`). There is no GitHub-direct publishing path.
- **Registry from registries.json** -- the target registry is resolved from `~/.prism/registries.json` (with fallback to legacy `config.json` `registry_url`). Use `--registry NAME` or the default registry.
- **Auth token resolution** -- checks `REGISTRY_TOKEN` env var first (backward compat), then per-registry token from `registries.json`. The resolved token is passed to the publish request directly.
- **Delta tracking** -- `.published.json` tracks content hashes so only changed skills are republished. This avoids unnecessary API calls and makes publish idempotent.
- **Atomic writes** -- `.published.json` is written via temp file + rename to prevent corruption.

## Output rules

- Report skill counts (published, skipped, failed) as a clear summary
- Show the registry URL that was published to
- If using `--all`, note that delta checking was bypassed
- Do not print full SKILL.md contents in the output
