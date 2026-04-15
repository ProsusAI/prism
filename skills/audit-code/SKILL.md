---
name: audit-code
description: Query the skill registry to find relevant architectural skills matching the user codebase, then audit the code against matched skill recommendations.
---

## When to use this skill

Use when the user wants to improve their codebase architecture by checking it against skills present in the registry. Invoked as `/audit-code`.

## Configuration

- **Primary source:** All configured registries in `~/.prism/registries.json` (with per-registry caching and source tagging)
- **Fallback 1:** Local `skill-registry.json` in the current project directory
- **Fallback 2:** Local `_analysis/extracted_skills_codebase/` skill directories
- **Authentication:** `REGISTRY_TOKEN` environment variable (global override) or per-registry token from `registries.json`

> Skills from multiple registries are merged and each result is tagged with `[registry-name]` (e.g., `[team]`, `[community]`) to identify the source.

## Instructions

### Step 1 -- Resolve skill registry source

Try to load a skill registry in this order. Stop at the first successful source.

**1a. All configured registries (preferred):**

Fetch from ALL configured registries in `~/.prism/registries.json`, merge results, and tag each skill with its source registry name:

```python
python3 -c "
import json, os, time, sys
import urllib.request, urllib.error
reg_path = os.path.expanduser('~/.prism/registries.json')
cache_dir = os.path.expanduser('~/.prism/cache')
try:
    with open(reg_path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {'registries': []}
# Fall back to config.json migration
if not data.get('registries'):
    cfg_path = os.path.expanduser('~/.prism/config.json')
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
        url = cfg.get('registry_url', '')
        if url:
            data = {'registries': [{'name': 'default', 'url': url, 'token': ''}]}
    except: pass
all_skills = []
registry_reached = False
for reg in data.get('registries', []):
    name = reg['name']
    url = reg['url'].rstrip('/')
    token = os.environ.get('REGISTRY_TOKEN', reg.get('token', ''))
    cache_path = os.path.join(cache_dir, f'{name}.json')
    # Check cache (24h mtime TTL = 86400 seconds)
    try:
        if os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < 86400:
                with open(cache_path) as f:
                    cached = json.load(f)
                registry_reached = True
                for s in cached.get('skills', []):
                    s['_registry'] = name
                    all_skills.append(s)
                continue
    except: pass
    # Fetch fresh
    try:
        headers = {'User-Agent': 'Prism/1.0'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        req = urllib.request.Request(f'{url}/api/skills/registry', headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            fetched = json.loads(resp.read().decode())
        os.makedirs(cache_dir, exist_ok=True)
        tmp = cache_path + '.tmp'
        with open(tmp, 'w') as f: json.dump(fetched, f)
        os.rename(tmp, cache_path)
        registry_reached = True
        for s in fetched.get('skills', []):
            s['_registry'] = name
            all_skills.append(s)
    except Exception as e:
        print(f'Warning: could not reach {name}: {e}', file=sys.stderr)
        # Try stale cache
        try:
            if os.path.exists(cache_path):
                with open(cache_path) as f:
                    cached = json.load(f)
                registry_reached = True
                for s in cached.get('skills', []):
                    s['_registry'] = name
                    all_skills.append(s)
        except: pass
if all_skills:
    print(json.dumps(all_skills))
elif registry_reached:
    print('REGISTRY_EMPTY')
else:
    print('NO_REGISTRIES')
"
```

If the result is valid JSON (an array of skills), use it as the skills list. Each skill has a `_registry` field indicating its source.

If the result is `REGISTRY_EMPTY`, the registry was reached but has no skills yet. Skip fallback sources and go directly to Step 2.

If the result is `NO_REGISTRIES`, no registry was configured or reachable. Proceed to fallback sources.

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
> 1. Add a registry: `prism registry add NAME --url URL --token TOKEN`
> 2. Place `skill-registry.json` in the project root
> 3. Run `/extract-skills` to create local skills

Then stop.

### Step 2 -- Check for empty registry

If the `skills` array from the resolved source is empty, respond with: "No skills have been published to the registry yet." and stop.

### Step 3 -- Analyse user codebase

Ask the user:

> "Is this an agentic codebase (uses LLMs, tools, or AI orchestration)?"

Wait for the user's response, then perform a lightweight architectural scan. Read:

**For all codebases:**

1. **Dependency manifests** (pyproject.toml, requirements.txt, package.json, go.mod) -- identify the tech stack, frameworks, and key dependencies.
2. **Entry points** (main.py, app.py, index.ts, or files referenced in manifests) -- identify application structure, routing, and execution flow.
3. **State and data management** -- look for persistence layers, caching strategies, and how data flows through the system.
4. **Safety and security patterns** -- look for input validation, authentication, authorization, and error handling.
5. **Configuration and deployment** (docker-compose.yml, .env.example, CI/CD files) -- identify operational patterns.

**Additionally, if the user confirmed the codebase is agentic:**

6. **LLM and orchestration stack** -- identify LLM provider SDKs, orchestration frameworks (LangChain, LangGraph, CrewAI, etc.), and agent execution flow.
7. **Tool definitions and use** -- look for tool/function definitions, tool calling patterns, and how results are handled.
8. **Context and memory management** -- look for conversation history handling, context window strategies, and memory/state persistence across turns.
9. **Agentic safety patterns** -- look for prompt injection defenses, output validation, and authentication on tool calls.

Produce a concise internal summary of: what the code does, which architectural patterns are present, and which concerns are addressed or absent. This summary is not shown to the user -- it is used in Step 4 for matching.

### Step 4 -- Match codebase to skills in registry

For each skill in the registry:

1. Extract the `TRIGGER when:` clause from its `description` field.
2. Compare each trigger scenario against the codebase summary from Step 3. A skill matches if:
   - The codebase operates in a domain where the skill's trigger conditions apply (e.g., the codebase has multi-turn tool calling and the skill addresses context overflow in that scenario), **AND**
   - The codebase does not already fully implement the pattern the skill teaches, or implements it partially / with anti-patterns the skill addresses.
3. Do **not** match skills whose trigger scenarios do not apply to this codebase's architecture (e.g., do not suggest a search-relevancy skill if the code has no search functionality).
4. If no skills match, state that the codebase does not exhibit patterns addressed by the registry.

If few or no skills match that is ok. It is better to match few highly relevant skills than many loosely related ones.

Rank matched skills by impact: skills addressing gaps or anti-patterns in the codebase rank higher than skills that would refine already-adequate implementations.

### Step 4b -- Verify matched skills (second pass)

Review the ranked list from Step 4 and apply a strict relevance check to each skill. For every matched skill, answer these two questions:

1. **Concrete evidence**: Can you point to a specific file, function, or pattern in the codebase that the skill directly addresses? If the connection is only thematic (e.g., "both involve LLMs") rather than architectural (e.g., "the codebase has no token budget and the skill adds one"), remove the skill.
2. **Marginal value**: Does the skill teach something the codebase genuinely lacks or does poorly, or would adopting it be a minor refinement with low practical impact? Remove skills whose benefit is marginal.

Drop any skill that fails either question. Do not try to preserve a minimum number of results -- zero matches is a valid outcome.

For each surviving skill, classify it into one of two categories:

- **Immediate**: The skill addresses an active gap, anti-pattern, or risk in the codebase that could cause failures, security issues, or significant inefficiency in its current state. These are things that should be fixed now.
- **Long-term**: The skill would improve robustness, scalability, or maintainability, but the codebase functions adequately without it today. These are improvements to plan for.

### Step 5 -- Load each matched skill's SKILL.md

For each matched skill, try to load its full SKILL.md content.

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

If a fetch fails, note the failure in the output but continue processing other matched skills.

### Step 6 -- Output results and save to file

Output the results to `_analysis/registry-audit.md`, replacing it if it already exists.

Auto-detect repo name and date:

```bash
git remote get-url origin 2>/dev/null | sed 's/.*\///;s/\.git$//'
date +%d-%m-%Y
```

Use this format:

```markdown
# /audit-code Results
# {repository} -- {DD-MM-YYYY}

## Immediate attention

| Skill Name | Repository | Why and how the skill can improve the current code |
|---|---|---|
| [registry-name] {name} | {repository} | {gap or anti-pattern it addresses} |

## Long-term improvements

| Skill Name | Repository | Why and how the skill can improve the current code |
|---|---|---|
| [registry-name] {name} | {repository} | {improvement it enables} |
```

Do not write a section entirely if it has no entries.
If no skills are matched, state that the codebase does not exhibit patterns addressed by the registry and stop -- do not write a file.

## Output rules

- Only respond with tables. Do not render the full SKILL.md files below the tables.
- Do not add commentary or analysis beyond what is in the SKILL.md.
- Do not suggest skills that do not have a clear trigger match.
- Order results by relevance, strongest match first.
- **Skill Name** must be the plain skill name from the registry `name` field. Do not embed links, repository URLs, or any other markup in the Skill Name column.
