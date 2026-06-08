---
name: audit-code
description: Query the skill registry to find relevant architectural skills matching the user codebase, then audit the code against matched skill recommendations.
---

## When to use this skill

Use when the user wants to improve their codebase architecture by checking it against skills present in the registry. Invoked as `/audit-code` (Claude Code) or `@audit-code` (Cursor).

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

### Step 2.5 -- Check for existing analysis files

Check which analysis files exist:

```bash
for f in _analysis/full_report.md _analysis/design.md _analysis/directives.md _analysis/incidents.md; do
  test -f "$f" && echo "FOUND: $f" || echo "MISSING: $f"
done
```

If **at least one file is found**, list them and ask the user:

> "Found existing analysis files in `_analysis/`:
> {list found files}
>
> Use these for matching, or run a fresh codebase scan?"

- **Fresh scan chosen** → skip to Step 3, Path B.
- **Use existing files chosen** → read all found files now (see table below), then continue to Step 3, Path A.
- **No files found** → skip to Step 3, Path B.

**What to extract from each found file:**

| File | Extract |
|---|---|
| `full_report.md` | Tech stack, all architectural clusters, patterns present and absent |
| `design.md` | Design decisions, trade-offs, non-obvious behaviors, structural anti-patterns |
| `directives.md` | Known failure modes and rules derived from git history |
| `incidents.md` | Incident patterns and what has broken historically |

### Step 3 -- Build codebase summary

**Path A — Targeted scan** (user chose to use existing files in Step 2.5)

Each `_analysis/` file covers specific scan sections. Only scan sections whose covering file is **missing**.

| Missing file | Scan sections required |
|---|---|
| `full_report.md` | Sections 1 and 5 (always) |
| `full_report.md` AND `design.md` both missing | Also sections 2, 3, 4 — and sections 6–9 if agentic |
| `directives.md` | Nothing to scan — this file comes from git history, not code |
| `incidents.md` | Nothing to scan — this file comes from git history, not code |

Run only the sections indicated. Ask the user whether the codebase is agentic before running sections 6–9.

Section definitions:

1. **Dependency manifests** (pyproject.toml, requirements.txt, package.json, go.mod) -- identify tech stack, frameworks, key dependencies.
2. **Entry points** (main.py, app.py, index.ts, or files referenced in manifests) -- identify application structure, routing, execution flow.
3. **State and data management** -- look for persistence layers, caching strategies, data flow.
4. **Safety and security patterns** -- look for input validation, authentication, authorization, error handling.
5. **Configuration and deployment** (docker-compose.yml, .env.example, CI/CD files) -- identify operational patterns.
6. **LLM and orchestration stack** -- identify LLM provider SDKs, orchestration frameworks (LangChain, LangGraph, CrewAI, etc.), agent execution flow. *(agentic only)*
7. **Tool definitions and use** -- look for tool/function definitions, calling patterns, result handling. *(agentic only)*
8. **Context and memory management** -- look for conversation history handling, context window strategies, memory persistence. *(agentic only)*
9. **Agentic safety patterns** -- look for prompt injection defenses, output validation, authentication on tool calls. *(agentic only)*

---

**Path B — Full scan** (no existing files, or user chose fresh scan)

Ask the user:

> "Is this an agentic codebase (uses LLMs, tools, or AI orchestration)?"

Wait for the user's response, then run all sections:

- Sections 1–5 for all codebases.
- Sections 6–9 additionally if the codebase is agentic.

Section definitions are the same as Path A above.

---

After reading files (Path A) and running any required scan sections, produce a concise internal codebase summary: what the code does, which architectural patterns are present, and which concerns are addressed or absent. This summary is not shown to the user -- it is used in Step 4 for matching.

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
skill_path = ""    # <-- path field from registry entry

# Resolve token: env var override → registries.json entry for this registry
token = os.environ.get("REGISTRY_TOKEN", "")
if not token:
    try:
        reg_path = os.path.expanduser("~/.prism/registries.json")
        with open(reg_path) as f:
            regs = json.load(f)
        for r in regs.get("registries", []):
            if r.get("url", "").rstrip("/") == registry_url.rstrip("/"):
                token = r.get("token", "")
                break
    except Exception:
        pass

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

If a fetch succeeds for a remote skill, cache it and link it into the project: read `~/.prism/skills/_shared/cache-skill.md` and follow its steps. This saves the content to `~/.prism/skills/{name}/SKILL.md` and creates the `.claude/skills/{name}` symlink so the skill is immediately usable and fetchable.

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
# /audit-code (Claude Code) or @audit-code (Cursor) Results
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
