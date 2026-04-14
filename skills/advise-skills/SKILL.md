---
name: advise-skills
description: Query the skill registry to find relevant architectural skills matching what the user wants to build. Searches across configured registries with graceful fallback to local sources.
---

## When to use this skill

Use when the user wants to find skills relevant to a task or architectural decision. Invoked as `/advise-skills <query>`.

## Configuration

- **Primary source:** Remote registry at the URL configured in `~/.prism/config.json` key `registry_url`
- **Fallback 1:** Local `skill-registry.json` in the current project directory
- **Fallback 2:** Local `_analysis/extracted_skills_codebase/` skill directories
- **Authentication:** `REGISTRY_TOKEN` environment variable (required for remote registry access)

> **Phase 3 scope:** Full multi-registry support (searching across multiple named registries with source tagging) is available when multiple registries are configured. Currently queries the configured registry or local skills.

## Instructions

### Step 1 -- Resolve skill registry source

Try to load a skill registry in this order. Stop at the first successful source.

**1a. Remote registry (preferred):**

Read `~/.prism/config.json` and check for a non-empty `registry_url` value:

```python
python3 -c "
import json, os
config_path = os.path.expanduser('~/.prism/config.json')
try:
    with open(config_path) as f:
        config = json.load(f)
    url = config.get('registry_url', '')
    print(url if url else '')
except (FileNotFoundError, json.JSONDecodeError):
    print('')
"
```

If `registry_url` is configured, fetch the registry index:

```python
python3 << 'PYEOF'
import json, os, urllib.request, urllib.error

registry_url = ""  # <-- from config
token = os.environ.get("REGISTRY_TOKEN", "")

req = urllib.request.Request(
    f"{registry_url}/api/skills/registry",
    headers={"User-Agent": "Prism/1.0"},
)
if token:
    req.add_header("Authorization", f"Bearer {token}")

try:
    with urllib.request.urlopen(req) as resp:
        registry = json.loads(resp.read().decode())
        skills = registry.get("skills", [])
        print(f"Loaded {len(skills)} skill(s) from remote registry")
except urllib.error.HTTPError as e:
    if e.code in (401, 403):
        print("AUTH_FAILED")
    else:
        print(f"FETCH_FAILED: HTTP {e.code}")
except urllib.error.URLError as e:
    print(f"FETCH_FAILED: {e.reason}")
PYEOF
```

If the fetch returns `AUTH_FAILED`, tell the user:

> **Registry requires authentication.** Set the `REGISTRY_TOKEN` environment variable:
> ```
> export REGISTRY_TOKEN="your-api-token"
> ```

Then stop.

If the fetch fails for other reasons, proceed to fallback sources.

**1b. Local skill-registry.json (fallback):**

Check if `skill-registry.json` exists in the current project directory:

```bash
test -f skill-registry.json && echo "FOUND" || echo "NOT_FOUND"
```

If found, read it and use its `skills` array. Note in the output: "Using local skill-registry.json (no remote registry configured or reachable)."

**1c. Local _analysis/ skills (fallback):**

Check if `_analysis/extracted_skills_codebase/` has skill directories with `plugin.json`:

```bash
ls _analysis/extracted_skills_codebase/*/plugin.json 2>/dev/null | head -20
```

If found, build a temporary registry from the local `plugin.json` files:

```python
python3 << 'PYEOF'
import json, os

base = "_analysis/extracted_skills_codebase"
skills = []
for name in sorted(os.listdir(base)):
    plugin_path = os.path.join(base, name, "plugin.json")
    if os.path.isfile(plugin_path):
        with open(plugin_path) as f:
            skills.append(json.load(f))
print(f"Built local registry from {len(skills)} extracted skill(s)")
PYEOF
```

Note in the output: "Using local extracted skills (no remote registry or skill-registry.json available)."

**1d. No source available:**

If none of the above sources are available, tell the user:

> **No skill registry available.** Options:
> 1. Configure a registry: `prism config registry_url <URL>`
> 2. Place `skill-registry.json` in the project root
> 3. Run `/extract-skills` to create local skills

Then stop.

### Step 2 -- Check for empty registry

If the `skills` array from the resolved source is empty, respond with: "No skills have been published to the registry yet." and stop.

### Step 3 -- Extract trigger clauses

For each entry in the `skills` array, extract the `TRIGGER when` clause from its `description` field. This clause defines the scenarios where the skill is relevant.

### Step 4 -- Match and rank

Compare the user's query against each trigger clause semantically. A skill matches if the user's intent aligns with at least one trigger scenario. Require genuine semantic alignment -- do not match on superficial keyword overlap.

Rank matches by relevance to the user's query.

### Step 5 -- Respond with match table

Respond with a table using only registry metadata (no fetching yet):

| Skill Name | Repository | Why it matches |
|---|---|---|
| {name} | {repository} | {why it matches this query} |

If no skills match the query, state that clearly and list all available skill names with their one-line descriptions so the user can see what is available and refine their query. Stop here.

Then ask:

> "Fetch full skill details for all N match(es), or would you like to adjust the list first?"

Wait for the user's response. If they want to adjust, accept a revised list of skill names and proceed with those. If they confirm all, proceed with the full matched set.

### Step 6 -- Load confirmed skills' SKILL.md

For each confirmed skill, try to load its full SKILL.md content.

**If the skill was loaded from a remote registry:** Fetch the individual skill's SKILL.md using the `path` field from the registry entry:

```python
python3 << 'PYEOF'
import json, os, urllib.request, urllib.error

registry_url = ""  # <-- from Step 1
token = os.environ.get("REGISTRY_TOKEN", "")
skill_path = ""    # <-- path field from registry entry

req = urllib.request.Request(
    f"{registry_url}/file/{skill_path}/SKILL.md",
    headers={"User-Agent": "Prism/1.0"},
)
if token:
    req.add_header("Authorization", f"Bearer {token}")

try:
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode()
        print(content)
except urllib.error.HTTPError as e:
    print(f"FETCH_FAILED: HTTP {e.code}")
except urllib.error.URLError as e:
    print(f"FETCH_FAILED: {e.reason}")
PYEOF
```

**If the skill was loaded from local sources:** Read `_analysis/extracted_skills_codebase/{name}/SKILL.md` directly.

If a fetch succeeds for a remote skill, save the content to `.claude/skills/{name}/SKILL.md` using the Write tool so it is available locally next time.

If a fetch fails, note the failure in the output but continue processing other confirmed skills.

### Step 7 -- Save results to file

Write `_analysis/registry-advice.md`, replacing it if it already exists.

Include only skills whose SKILL.md was successfully loaded in Step 6 (skip any that failed to fetch). Use the same match reasoning from the Step 5 table.

Auto-detect repo name and date:

```bash
git remote get-url origin 2>/dev/null | sed 's/.*\///;s/\.git$//'
date +%d-%m-%Y
```

```markdown
# /advise-skills Results
# {repository} -- {DD-MM-YYYY}

> Query: {the user's original query}

| Skill Name | Repository | Why it matches |
|---|---|---|
| {name} | {repository} | {why it matches this query} |
```

If no skills were successfully loaded, do not write the file.

## Output rules

- Only respond with a table. Do not render the full SKILL.md files below the table.
- Do not add commentary or analysis beyond what is in the SKILL.md.
- Do not suggest skills that do not have a clear trigger match.
- Order results by relevance, strongest match first.
