---
name: mine-history
description: "Mine a repository's git history for institutional knowledge — failure modes, architectural decisions, and codebase directives. TRIGGER when: starting the history analysis pipeline, running /mine-history before /synthesize, extracting practices from git history, looking for what has broken in this codebase and why."
---
## When to use this skill

Mine this repository's git history for institutional knowledge the team accumulated while building it. Produce codebase directives (Type 1) that prevent AI assistants from repeating mistakes, and raw incident clusters (Type 2 candidates) for practice synthesis.

---

## Step 1 — Verify and orient

Confirm we're inside a git repository:

```bash
git rev-parse --is-inside-work-tree
```

If this fails, stop and tell the developer this skill requires a git repository.

Get the repo name and rough size so you can calibrate the analysis window:

```bash
git rev-list --count HEAD
git log --format="%ad" --date=short | tail -1
git log --oneline -5
```

Tell the developer:
- Repo name and total commit count
- Date of oldest commit
- What you're about to do: classify commits, read diffs for hot subsystems, synthesize directives, ask them what git missed

---

## Step 2 — Select analysis window and read commits

**Goal: land in the 150–400 commit range.** This is enough history to find patterns without too much noise to classify. Adjust the window iteratively until you're in range — don't just apply a fixed time cutoff.

**Starting point by repo size:**
- < 200 total commits → start with all commits
- 200–2000 total commits → start with last 6 months
- > 2000 total commits → start with last 3 months

**Then count and adjust:**

```bash
git log --oneline --after="6 months ago" | wc -l
```

- If count > 400: halve the window (6 months → 3 months → 6 weeks) and recount
- If count < 100: double the window (3 months → 6 months → 1 year → all) and recount
- Stop when you're in the 150–400 range, or when you've hit the full repo history

If the full repo history is still under 150 commits, use all of it and note that the repo is young or low-velocity.

Run the final window:

```bash
git log --format="%H %ad %s" --date=short --after="{final_window}"
# or without --after for full history
```

Tell the developer the window you landed on (e.g. "last 10 weeks, 287 commits") and offer to extend it after completing the analysis.

**Classify each commit — do NOT grep, read and classify directly:**

| Category | What qualifies |
|---|---|
| **Revert** | Explicit reversal ("revert", "undo", "rollback") or "this didn't work" phrasing |
| **Bug fix / hotfix / incident** | Fixing broken behavior, production errors, crashes, data corruption |
| **Migration / deprecation / replacement** | Technology or pattern switch ("replace X with Y", "migrate to", "remove X", "deprecate") |
| **Architectural decision** | Structural change, service split/merge, major refactor with stated rationale |
| **Workflow change** | Changes to scripts, CI/CD, Makefile, deployment process |
| **Not interesting** | Docs, chores, version bumps, test-only changes, formatting, dependency updates without context |

For each commit classified as interesting, note:
- Commit hash
- Date
- Category
- Which paths/files it likely touches (infer from message if possible; confirm with `git show --stat {hash}`)

**Identify hot subsystems:** Group bug fix and hotfix commits by the paths they touch. Any path prefix with 3+ fix commits is a hot subsystem. Record the top 5 by fix density.

After classification, tell the developer: "I found [N] interesting commits spanning [earliest date] to [latest date]. Before I read diffs, do you want me to extend the window?"

---

## Step 3 — Architectural evolution pass

This step catches technology decisions that never had an explanatory commit — additions and removals that show up only in dependency file changes.

Find when dependency files changed:

```bash
git log --format="%H %ad" --date=short -- package.json requirements.txt go.mod Pipfile pyproject.toml Gemfile cargo.toml 2>/dev/null | head -40
```

Read current dependency file vs. a snapshot from approximately 1 year ago (use the commit hash closest to 1 year back from the list above):

```bash
git show HEAD:package.json 2>/dev/null || git show HEAD:requirements.txt 2>/dev/null || git show HEAD:go.mod 2>/dev/null
git show {hash_from_1yr_ago}:package.json 2>/dev/null
```

Compare the two snapshots. Note:
- What was present 1 year ago and is now gone → possible failed experiment or completed migration
- What appeared and disappeared within the window → short-lived technology, likely abandoned
- What is new and still present → active adoption

Check for removed directories (merged services, dropped backends):

```bash
git log --all --diff-filter=D --name-only --format="" 2>/dev/null | grep "/" | sort | uniq -c | sort -rn | head -20
```

Any directory with multiple file deletions in a single commit is a likely service removal or structural change worth noting.

---

## Step 4 — Read diffs for hot subsystems

For each hot subsystem identified in Step 2 (top 5 by fix density):

```bash
git log --follow --oneline -- {path}
```

For each interesting commit in that path (focus on reverts, bug fixes, and architectural decisions):

```bash
git show --stat {hash}
git show {hash}
```

Read diffs chronologically. For each subsystem, identify:
- What broke (the failure mode)
- What the fix was (the specific change)
- Whether the same failure recurred (repeated fix pattern = strong directive signal)
- Whether the fix involved a third-party library, resource management, or distributed systems mechanics (Type 2 signal)

Also read diffs for any revert commits from Step 2 regardless of subsystem — these are the clearest signals for directives.

---

## Step 5 — Synthesize findings

For each finding, produce a directive in one of these forms:

**"Don't" form:** `Don't [do X] in [subsystem/context] — [reason]. Evidence: commit {hash} ({date})`

**"Always" form:** `Always [do Y] not [Z] — [reason]. Evidence: {pattern across commits}`

**"Status" form:** `[Technology/pattern] is [deprecated/in-progress/abandoned] — [context]. Evidence: commit {hash} ({date})`

Group directives by subsystem or technology area.

**Number each directive sequentially** (`D1`, `D2`, ...) across the entire output — unique IDs that persist as cross-references.

**Annotate recurrence:** If the same failure mode appears in multiple distinct commits, list all evidence commits and add `(×N)` at the end. A single-occurrence directive has no annotation.

**Add scope tag:**
- `[codebase]` — applies only to this repo's internals (specific data model, internal API, particular config). Won't transfer to another team.
- `[technology]` — about a third-party library/protocol/tool behavior that any team using this tech could hit. Pre-flags this directive as likely Type 2 material.

When building Type 2 clusters, record which directive IDs contributed.

Flag which directive clusters are Type 2 candidates. A cluster qualifies if it meets **two or more** of:
- Mentions a third-party tool, library, database, or protocol (not internal product names)
- Problem is about resource management (memory, connections, file handles, locks)
- Problem is about distributed systems mechanics (ordering, consistency, timeouts, retries)
- Same failure mode recurred 3+ times across distinct commits

For technology decisions from Step 3, produce "Status" form directives: what technology was removed, why (if inferrable), and what the current state is.

---

## Step 6 — Human-in-the-loop

Ask the developer:

> "I've analyzed [N] commits across [date range] and found [M] directives across [K] subsystems. Before I write the output, are there critical mistakes or knowledge gaps that never made it into a commit? For example:
> - Architectural decisions that were reversed verbally or in a design doc
> - Known footguns in specific files or subsystems
> - Deprecated patterns that are still in the codebase but should never be added to
> - In-progress migrations where the safe path isn't obvious from code alone"

Wait for their response. Incorporate any additions into the output, marking them clearly as "Added by developer" in the output files.

---

## Step 7 — Write output

Create the `_analysis/` directory in the repository root and write three files.

### `_analysis/directives.md`

```markdown
# Codebase Directives
*Generated by /mine-history on {date}. Analysis window: {window} ({N} commits, {earliest_date} – {latest_date}). Review quarterly.*
*Note: commits before {earliest_date} were not analyzed — extend the window to cover older history.*

## {Subsystem / Technology Area}
- **D{N} · [Directive statement]** `[codebase|technology]` — [reason]. Evidence: commit {hash} ({date})[, commit {hash} ({date})] [(×N if >1)]

## Added by developer
- {any directives from Step 6}
```

Rules for directives:
- Each directive must be actionable: a developer or AI assistant reading it knows exactly what to do or avoid
- Include the evidence commit hash so the reader can verify
- Group by subsystem — don't mix database, queue, and auth directives in one flat list
- If a directive came from the developer in Step 6 (not from git), put it in "Added by developer"

### `_analysis/architecture.md`

```markdown
# Architectural Context
*Things Claude cannot infer from current code alone. Generated by /mine-history on {date}. Analysis window: {window} ({earliest_date} – {latest_date}).*

## Technology decisions
- **[Technology] was [added/removed/replaced] ([date range])** — [reason if known]. [Current state and what to do].

## Structural evolution
- **[Structural change] ([date])** — [what changed and why].

## Active migrations (in progress)
- **[Migration description]** — [current state]. [Safe path forward].
```

Only include entries where the current code state would mislead a developer without this context. If the code clearly reflects its own state, skip it.

### `_analysis/incidents.md`

```markdown
# Type 2 Candidates — Incident Raw Material
*Analysis window: {window} ({earliest_date} – {latest_date}). Older incidents not covered.*

## {Technology/Subsystem Name} ({N} directives, {signal type})
**Signals that generalize:** [list the third-party tech, resource type, or distributed systems mechanic]
**Source directives:** D{N}, D{N}, D{N}
**Chronological findings:**
1. [Failure mode] — commit {hash} ({date}) [D{N}]
2. [Failure mode] — commit {hash} ({date}) [D{N}]
...
**Candidate practice:** "[What to expect when building X]"
**Status:** seed (1 team) — promote when second team confirms
```

Only include clusters that pass the Type 2 threshold from Step 5. Do not include business-logic-specific incidents that won't generalize.

---

## Quality checks before finishing

Before writing the files, verify:
- [ ] Every directive has an evidence commit hash (or is labeled "Added by developer")
- [ ] No directive is so vague it could apply to any codebase ("don't use blocking I/O")
- [ ] Architecture.md only contains things the current code cannot communicate
- [ ] Incidents.md clusters mention at least one third-party technology or general systems concept
- [ ] The human-in-the-loop step fired and the developer's response was incorporated (or they had nothing to add)

After writing, tell the developer:
- Where the files were written
- How many directives were produced
- Which subsystems had the highest fix density
- Which clusters are Type 2 candidates and why
