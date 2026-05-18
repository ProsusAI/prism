---
name: synthesize
description: "Promote qualifying incident clusters from git history into reusable practice skills. TRIGGER when: _analysis/incidents.md exists and is ready to promote, running `/synthesize` (Claude Code) or `@synthesize` (Cursor) after `/mine-history` (Claude Code) or `@mine-history` (Cursor), extracting failure-mode practices from a mined repository."
---

## When to use this skill

Promote qualifying Type 2 seed clusters from `_analysis/incidents.md` into practice skills. Writes `_analysis/extracted_skills_history/{name}/SKILL.md` and `_analysis/extracted_skills_history/{name}/plugin.json` in the current repo with all team-specific details stripped.

---

## Step 1 — Read incidents.md

Read `_analysis/incidents.md`. This is the required input.

If it doesn't exist, stop and tell the developer:

> "`_analysis/incidents.md` not found. Run `/mine-history` (Claude Code) or `@mine-history` (Cursor) first to extract incident clusters from your git history."

Read the file fully. Note each cluster: its name, the directives/findings listed, their dates, and its current status line.

Also check for `_analysis/design.md`. If it exists, read it fully. Note **all** findings — both `[technology]`-tagged and `[codebase]`-tagged — recording each one's subsystem, category (decision / non-obvious behavior / structural anti-pattern), and the technology or pattern it concerns. Do not skip `[codebase]`-tagged findings at this stage. If design.md doesn't exist, continue without it.

Pay particular attention to the `## Architectural patterns` section of design.md, if present. These are pre-assembled cross-subsystem patterns from Phase 3c of `/mine-design` (Claude Code) or `@mine-design` (Cursor). Treat them as first-class candidates with their own promotion path and key-decisions output format (see Step 3 and Step 5).

Individual design seeds that don't reach the assembled-pattern threshold may be better candidates for `/synthesize-decisions` (Claude Code) or `@synthesize-decisions` (Cursor). Flag them as such rather than marking them "too thin".

---

## Step 2 — Auto-discover supplementary docs

Without asking the developer, look for documentation that might contain additional failure modes or lessons learned:

```bash
ls docs/ 2>/dev/null
ls adr/ 2>/dev/null
ls decisions/ 2>/dev/null
find . -name "ADR*.md" -not -path "*/node_modules/*" 2>/dev/null | head -10
find . -name "ARCHITECTURE*.md" -not -path "*/node_modules/*" 2>/dev/null | head -5
find . -name "CONTRIBUTING*.md" -not -path "*/node_modules/*" 2>/dev/null | head -5
cat CLAUDE.md 2>/dev/null
```

Read any files found. Extract findings that match: decision made, reason given, current state. Note which docs were found and which clusters they reinforce.

---

## Step 3 — Evaluate clusters against promotion threshold

For each cluster in `incidents.md`, each doc-sourced finding, and each finding from `design.md`, apply the promotion criteria.

**Required — all must be true:**
1. Pattern generalizes to any team facing the same technical situation — not tied to this team's data model, business rules, or internal architecture.
2. Problem is technology-level, not business-specific.
3. Practice encodes knowledge a coding assistant cannot reliably derive from documentation alone — a production failure mode or trap that requires having encountered it.

**Depth threshold — at least one must be true:**
- 5+ directives/findings in the cluster, OR
- 3+ directives that each recurred across multiple dates

**Disqualifiers:**
- Fix requires understanding the team's specific data model
- Cluster mentions internal product concepts without a generalizable technology pattern above them
- Problem is about business rules or product requirements
- Failure mode only makes sense in the context of this team's architecture

**Verdicts:**
- **Qualifies** — meets all required criteria and depth threshold, no disqualifiers
- **Too thin** — meets required criteria but not depth threshold (list what's missing)
- **Strong candidate** — below depth threshold but passes signal quality check. Requires developer decision.
- **Design seed** — qualifying finding from design.md, code-substantiated. Requires developer decision.
- **Assembled pattern** — cross-subsystem pattern from `## Architectural patterns` in design.md. Requires developer decision.
- **Too specific** — fails required criteria (explain which concept makes it non-generalizable)
- **Documented — skip** — clearly documented and findable in a quick search; note where
- **Already promoted** — status line already points to `_analysis/extracted_skills/`

**Signal quality check (for thin clusters only):**
If ALL THREE are true, mark as "Strong candidate" instead of "Too thin":
1. Root cause explains internal technology behavior not prominently documented
2. Any team doing this pattern with this technology will hit it
3. Generalizable principle articulable in 1–2 sentences from existing evidence

**For design.md findings:** 1+ qualifying finding is sufficient to seed a practice.

**For assembled patterns:** qualifies if it meets required criteria 1–3, spans 2+ subsystems or encodes a deliberate non-default decision, a structural template is demonstrable, and passes the "would you say this unprompted?" test.

Show the developer the verdict table:

```
CLUSTER                          VERDICT          NOTE
redis-connection-exhaustion      Qualifies        3 recurrences, resource management pattern
auth-token-refresh-race          Too specific     Depends on internal session model
postgres-advisory-locks          Strong candidate 2 directives, structural pattern clear
```

---

## Step 4 — Developer gate (borderline cases only)

**Skip this step entirely if no clusters are Strong candidate, Design seed, or Assembled pattern.** Proceed directly to Step 5.

Combine all borderline questions in a single message:

For **Strong candidates**:
> "**[cluster name]** is below the depth threshold (N directive(s)), but the mechanism is non-obvious and structural. Promote as a thin seed?"

For **Design seeds**:
> "**[finding title]** is code-substantiated but thin by incident standards. Promote it?"

For **Assembled patterns**:
> "**[pattern name]** is a cross-subsystem pattern from design.md ([N] findings across [subsystems]). Promotes as key-decisions format. Proceed?"

Wait for one response covering all borderline cases.

---

## Step 5 — Collect metadata

First, check for a cached session file:

```bash
cat _analysis/.meta 2>/dev/null
```

If `_analysis/.meta` exists, read `author`, `repository`, `source_hash`, and `source` from it. Set `commit_date` to today in `DD-MM-YYYY` format. Skip the rest of this step.

If the file does not exist, auto-detect:

```bash
git config user.name 2>/dev/null
git remote get-url origin 2>/dev/null
git rev-parse --short HEAD 2>/dev/null
```

Set automatically (no confirmation):
- `author` → git config user.name (or "unknown" if absent)
- `repository` → last path segment of remote URL with `.git` stripped, or directory name if no remote
- `source_hash` → short hash from git rev-parse (or null)
- `commit_date` → today in `DD-MM-YYYY` format
- `category` → suggested per practice based on technology and failure type; applied directly

**Ask once:**

> "Is this an internal (your organization) or external (open-source) repo?
> If external, please provide the GitHub repo URL."

**Do not proceed until the user answers.**

Set `source` to `internal` or `external <url>` based on the answer.

Write `_analysis/.meta`:

```
author: {value}
repository: {value}
source_hash: {value}
source: {value}
```

---

## Step 6 — Write all practices

For each confirmed practice (Qualifies + confirmed borderline cases):

Determine a practice name: lowercase, hyphenated, technology-first (e.g. `redis-fair-queue-hardening`, `postgres-mvcc-cte-snapshot`).

Write two files to `_analysis/extracted_skills_history/{practice-name}/`:

---

### SKILL.md

Frontmatter: `name` and `description` only. All registry metadata lives in `plugin.json`.

```markdown
---
name: {practice-name}
description: "{technology} {use-case}: failure modes in order of encounter when building for production. TRIGGER when: writing any code that touches {technology} for {use-case}, debugging {specific symptom}, starting a new project with {technology} — even if the user hasn't explicitly mentioned these failure modes yet."
---

# {Practice Title}
*What to expect when building {X} in production — failure modes in the order you will encounter them.*

## Who this is for
Teams building {X} with {technology}. These failure modes appear in sequence as scale or load increases.

## Failure mode 1: {name}
**Symptom:** {observable behavior — no internal names}
**Mechanism:** {technical root cause at the {technology} level}
**Fix:** {technology-level fix, no internal class or table names}
**Evidence:** {anonymized org type} — {month and year only}

## Failure mode 2: {name}
...

{repeat chronologically}

## Design insight {N}: {name}
**Behavior:** {what isn't obvious}
**Why it's non-obvious:** {what mental model leads developers astray}
**What callers must know:** {concrete consequence}
**Evidence:** {anonymized org type} — {month and year}

{omit section if no design.md findings were promoted}

## The underlying pattern
{1 paragraph: the generalizable insight.}
```

For assembled patterns, use the key-decisions format:

```markdown
---
name: {practice-name}
description: "{technology or concern}: architectural decisions for building {X} correctly in production. TRIGGER when: designing or reviewing {X}, a team member asks why {specific non-obvious choice was made}, starting a new project with {technology}."
---

# {Practice Title}
*Architectural decisions for building {X} correctly — what to choose and why.*

## Who this is for
Teams building {X} with {technology}. These decisions are non-obvious without production experience.

## Key decisions

### 1. {Decision statement}
**Why:** {The non-obvious reason.}
**What breaks without it:** {Concrete failure mode.}

### 2. {Decision statement}
...

## Anti-patterns

- **What:** {The tempting wrong path}
  **Why it fails:** {The mechanism}
  **Symptom:** {Observable outcome}

## Structural template

\`\`\`
{Pseudocode showing the correct implementation shape — structural, not runnable.}
\`\`\`

## Underlying principle
{1 paragraph: the generalizable insight.}
```

---

### plugin.json

```json
{
  "name": "{practice-name}",
  "description": "{same as SKILL.md frontmatter description — must contain TRIGGER when: clause}",
  "author": "{auto-detected}",
  "repository": "{auto-detected}",
  "category": ["{suggested primary}", "{optional secondary}"],
  "source": "{internal | external <url>}",
  "commit_date": "{DD-MM-YYYY}",
  "source_hash": "{short git hash | null}"
}
```

Valid categories: `architecture`, `execution-control`, `state-memory`, `persistence`, `networking`, `tools`, `RAG`, `data-learning`, `security`, `monitoring-evaluation`, `operations-deployment`.

---

**Stripping rules — apply before writing:**
- Remove all internal product names, class names, table names, domain concepts
- Replace with generics: "job queue", "task runner", "order", "user", "record"
- Keep: technology names (Redis, Postgres, Celery), general patterns, observable symptoms, fix mechanics
- Use month+year for dates, never full commit hashes

---

## After finishing
Tell the developer:
- Which practices were written (file paths under `_analysis/extracted_skills_history/`, categories assigned)
- Which clusters were skipped and why
- What the `description` field says for each practice, so they know when it will auto-load
