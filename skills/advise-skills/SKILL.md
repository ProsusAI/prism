---
name: advise-skills
description: Query the skill registry to find relevant architectural skills matching what the user wants to build. Searches across configured registries with graceful fallback to local sources.
---

## When to use this skill

Use when the user wants to find skills relevant to a task or architectural decision. Invoked as `/advise-skills <query>` (Claude Code) or `@advise-skills <query>` (Cursor).

## Configuration

- **Primary source:** All configured registries in `~/.prism/registries.json` (with per-registry caching and source tagging)
- **Fallback 1:** Local `skill-registry.json` in the current project directory
- **Fallback 2:** Local `_analysis/extracted_skills_codebase/` skill directories
- **Authentication:** `REGISTRY_TOKEN` environment variable (global override) or per-registry token from `registries.json`

> Skills from multiple registries are merged and each result is tagged with `[registry-name]` (e.g., `[team]`, `[community]`) to identify the source.

## Instructions

### Step 1 -- Resolve skill registry source

Read `~/.prism/skills/_shared/registry-fetch.md` and follow its instructions. It resolves all configured registries with ETag caching and local fallbacks, returning a skills array where each entry is tagged with `_registry`.

Outcomes:
- Valid JSON array → use as the skills list, proceed to Step 2
- `REGISTRY_EMPTY` → registry reached but empty, proceed to Step 2
- `NO_REGISTRIES` → no registry reachable, stop (the shared file handles the user message)

### Step 2 -- Check for empty registry

If the `skills` array from the resolved source is empty, respond with: "No skills have been published to the registry yet." and stop.

### Step 3 -- Extract trigger clauses

For each entry in the `skills` array, extract the `TRIGGER when` clause from its `description` field. This clause defines the scenarios where the skill is relevant.

### Step 4 -- Match and rank

Compare the user's query against each trigger clause semantically. A skill matches if the user's intent aligns with at least one trigger scenario. Require genuine semantic alignment -- do not match on superficial keyword overlap.

Rank matches by relevance to the user's query.

### Step 5 -- Respond with match table

Respond with a table using only registry metadata (no fetching yet). If the skill has a `_registry` field, prefix the skill name with `[registry-name]` to show the source:

| Skill Name | Repository | Why it matches |
|---|---|---|
| [registry-name] {name} | {repository} | {why it matches this query} |

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

If a fetch succeeds for a remote skill, save the content to `~/.prism/skills/{name}/SKILL.md` using the Write tool so it is available locally next time.

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
# /advise-skills (Claude Code) or @advise-skills (Cursor) Results
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
