---
name: publish-skills
description: Publish changed skills from _analysis/extracted_skills_codebase/ to the Prism registry via the Worker API with delta tracking. Only publishes skills whose content has changed since last publish unless --all is specified.
---

## When to use this skill

Use when the user wants to publish extracted or promoted skills to a Prism skill registry. Invoked as `/publish-skills`, optionally with flags: `--all` (publish everything regardless of delta state) or `--registry NAME` (target a named registry).

## Prerequisites

- Skills must exist in `_analysis/extracted_skills_codebase/` (created by `/extract-skills` or `prism promote`)
- Each skill directory must contain both `plugin.json` and `SKILL.md`
- A registry must be configured in `~/.prism/config.json`
- The `REGISTRY_TOKEN` environment variable must be set

## Flags

| Flag | Effect |
|------|--------|
| `--all` | Publish all valid skills, ignoring delta state (force republish) |
| `--registry NAME` | Target a specific named registry. In Phase 3, this is informational -- the command uses the `registry_url` from `~/.prism/config.json`. Multi-registry support (selecting from `registries.json`) is available in Phase 4. |

## Instructions

### Step 1 -- Resolve configuration

Read the Prism config file at `~/.prism/config.json` and extract the `registry_url` value.

```bash
python3 -c "
import json, os
config_path = os.path.expanduser('~/.prism/config.json')
try:
    with open(config_path) as f:
        config = json.load(f)
    url = config.get('registry_url', '')
    print(url if url else 'NOT_CONFIGURED')
except (FileNotFoundError, json.JSONDecodeError):
    print('NOT_CONFIGURED')
"
```

If the result is `NOT_CONFIGURED` or empty, tell the user:

> **No registry configured.** Set your registry URL:
> ```
> prism config registry_url https://your-worker.workers.dev
> ```

Then stop.

Check the `REGISTRY_TOKEN` environment variable:

```bash
echo "${REGISTRY_TOKEN:+set}"
```

If not set (empty output), tell the user:

> **No API token found.** Set the `REGISTRY_TOKEN` environment variable with your registry API token:
> ```
> export REGISTRY_TOKEN="your-api-token"
> ```

Then stop.

### Step 2 -- Discover valid skills

Scan `_analysis/extracted_skills_codebase/` for skill directories. Each valid skill directory must contain both `plugin.json` and `SKILL.md`.

```bash
for dir in _analysis/extracted_skills_codebase/*/; do
    [ -d "$dir" ] || continue
    if [ -f "$dir/plugin.json" ] && [ -f "$dir/SKILL.md" ]; then
        echo "VALID: $(basename "$dir")"
    else
        echo "SKIP (missing files): $(basename "$dir")"
    fi
done
```

For each valid skill, read `plugin.json` and verify it has the required fields: `name`, `description`, `author`, `repository`, `category`, `source`, `commit_date`, `source_hash`.

```python
python3 << 'PYEOF'
import json, os, sys

required_fields = ["name", "description", "author", "repository", "category", "source", "commit_date", "source_hash"]
base = "_analysis/extracted_skills_codebase"

valid = []
invalid = []

for skill_name in sorted(os.listdir(base)):
    skill_dir = os.path.join(base, skill_name)
    if not os.path.isdir(skill_dir):
        continue
    plugin_path = os.path.join(skill_dir, "plugin.json")
    skillmd_path = os.path.join(skill_dir, "SKILL.md")
    if not (os.path.isfile(plugin_path) and os.path.isfile(skillmd_path)):
        invalid.append((skill_name, "missing plugin.json or SKILL.md"))
        continue
    try:
        with open(plugin_path) as f:
            plugin = json.load(f)
        missing = [fld for fld in required_fields if fld not in plugin]
        if missing:
            invalid.append((skill_name, f"missing fields: {', '.join(missing)}"))
        else:
            valid.append(skill_name)
    except (json.JSONDecodeError, OSError) as e:
        invalid.append((skill_name, str(e)))

print(f"Found {len(valid)} valid skill(s):")
for name in valid:
    print(f"  - {name}")
if invalid:
    print(f"\nSkipped {len(invalid)} invalid skill(s):")
    for name, reason in invalid:
        print(f"  - {name}: {reason}")
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

base = "_analysis/extracted_skills_codebase"
published_path = "_analysis/.published.json"

# Load existing published state
if os.path.isfile(published_path):
    with open(published_path) as f:
        published = json.load(f)
else:
    published = {}

# Compute hashes for all valid skills (list populated from Step 2)
VALID_SKILLS = []  # <-- fill from Step 2 results

for skill_name in VALID_SKILLS:
    skill_dir = os.path.join(base, skill_name)
    h = hashlib.sha256()
    for filename in ["plugin.json", "SKILL.md"]:
        filepath = os.path.join(skill_dir, filename)
        with open(filepath, "rb") as f:
            h.update(f.read())
    content_hash = h.hexdigest()[:12]

    # Check against published state for "default" registry
    prev = published.get(skill_name, {}).get("default", {})
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
TOKEN = os.environ["REGISTRY_TOKEN"]
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
        print("Registry authentication failed. Check your REGISTRY_TOKEN.")
except urllib.error.URLError as e:
    print(f"Connection failed: {e.reason}")
    print(f"Check that registry_url is correct: {REGISTRY_URL}")
PYEOF
```

**Important:**
- The API endpoint is `POST {registry_url}/api/skills/publish`
- Auth header: `Authorization: Bearer {REGISTRY_TOKEN}`
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

for skill_name, content_hash in PUBLISHED_SKILLS:
    if skill_name not in published:
        published[skill_name] = {}
    published[skill_name]["default"] = {
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
- Second-level keys are registry names (`"default"` for the single registry in Phase 3; named registries in Phase 4)
- `content_hash` is the first 12 hex characters of SHA256(`plugin.json` bytes + `SKILL.md` bytes)
- `published_at` is the UTC timestamp of the last successful publish

## Important differences from previous approaches

- **Worker-only publishing** -- skills are published via the registry Worker API (`POST /api/skills/publish`). There is no GitHub-direct publishing path.
- **Registry URL from config** -- the target registry is read from `~/.prism/config.json` key `registry_url`, not from environment variables.
- **Auth token from env** -- the API token comes from `REGISTRY_TOKEN` environment variable (not stored in config to avoid accidental commits).
- **Delta tracking** -- `.published.json` tracks content hashes so only changed skills are republished. This avoids unnecessary API calls and makes publish idempotent.
- **Atomic writes** -- `.published.json` is written via temp file + rename to prevent corruption.

## Output rules

- Report skill counts (published, skipped, failed) as a clear summary
- Show the registry URL that was published to
- If using `--all`, note that delta checking was bypassed
- Do not print full SKILL.md contents in the output
