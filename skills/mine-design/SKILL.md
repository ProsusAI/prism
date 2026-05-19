---
name: mine-design
description: "Extract design decisions, trade-offs, and non-obvious behaviors from a codebase's current source code. TRIGGER when: starting the design analysis pipeline, running `/mine-design` (Claude Code) or `@mine-design` (Cursor) before `/synthesize-decisions` (Claude Code) or `@synthesize-decisions` (Cursor), capturing the reasoning behind current architectural choices, analyzing a codebase snapshot for patterns that would surprise a developer arriving cold."
---

## When to use this skill

Snapshot-based design decisions for any codebase. Extract the reasoning behind current architectural choices, trade-offs made, and non-obvious system behaviors that live in the code itself — not in commit messages. Produce `_analysis/design.md`.

---

## Step 1 — Orient

Check if `_analysis/index.md` already exists:

```bash
test -f _analysis/index.md && echo "FOUND" || echo "NOT_FOUND"
```

**If `_analysis/index.md` exists:** Also check for cluster files:

```bash
ls _analysis/cluster_*.md 2>/dev/null
```

Then ask the user:

> "Found existing analysis files in `_analysis/`:
> - `index.md`
> {- `cluster_*.md` (list found files, if any)}
>
> Use these for orientation, or run a fresh codebase scan? (Files may be outdated if the code has changed.)"

- **Use existing** → Read `_analysis/index.md`. It contains the directory map, framework, entry points, and key file registry. Use it as your structural map and skip the bash commands below — go directly to the `_analysis/directives.md` check.
- **Fresh scan** → Run the bash commands below.

**If `_analysis/index.md` does not exist:** Run the following to build a structural picture from scratch:

```bash
cat README.md 2>/dev/null || cat readme.md 2>/dev/null
cat CLAUDE.md 2>/dev/null
cat package.json 2>/dev/null || cat go.mod 2>/dev/null || cat requirements.txt 2>/dev/null || cat Cargo.toml 2>/dev/null
ls -1
```

Check if `_analysis/directives.md` already exists. If it does, skim it to note what subsystems it covers — you'll avoid producing directive-style content (imperative rules from git history) in this analysis.

---

## Step 2 — Discover subsystems

From the directory structure and README, identify **4–8 major subsystems or concerns**. Before proposing clusters, read at least one entry-point file (main file, index, CLI root, or server start) to confirm the runtime structure matches the directory structure.

**If the user chose to use existing files in Step 1** and cluster files were found, skim them to extract subsystem names and their assigned files. Use these as the starting point — adjust or merge only where the cluster divisions do not map cleanly to design concerns.

Examples by system type:
- Job queue: "Queue Engine", "Concurrency Manager", "Tenant Dispatch", "Worker Pool"
- Agent: "Agent Core", "Tool System", "Memory Layer", "Safety Layer"
- Web API: "Auth Layer", "Request Pipeline", "Data Access Layer", "Background Jobs"
- CLI: "Command Parser", "Config Resolution", "Output Renderer", "Plugin System"

Rules for cluster discovery:
- Name clusters after what they *do*, not what they *are* — not "database" but "state persistence layer"
- 4 clusters minimum, 8 maximum — combine thin concerns, split fat ones
- Each cluster should have a clear owner: a directory or set of files you can read
- If a concern spans multiple files with no clear owner, it's probably not a cluster — it's a cross-cutting concern, note it separately

Tell the developer the subsystems you found and offer to adjust before proceeding. **Wait for their response.**

---

## Step 3 — Analyze each subsystem

Analysis runs one subsystem at a time. Complete Phase 3a and 3b for a subsystem, write its section to `_analysis/design.md`, then stop referencing its source files before moving to the next. Phase 3c runs after all subsystems are written, reading back from the file rather than from memory.

**Before starting the loop** — write the file header. Create `_analysis/` if it doesn't exist. Write (overwrite if the file already exists):

```markdown
# Design Decisions
*Snapshot analysis of current code state as of {date}.*
*Distinct from `architecture.md` (historical evolution) and `directives.md` (what to avoid from git history).*
*Captures the reasoning behind current architectural choices, trade-offs made, and non-obvious system behaviors.*

---
```

Then process each subsystem in sequence as described below.

---

### Phase 3a — Structured reading (probe questions)

For the current subsystem, read its core files (entry points and main logic — skip tests, generated code, and vendor directories). While reading, answer these probe questions. These probes work for any codebase — they don't require domain knowledge.

1. **Ordering constraints** — What must happen before X? What sequencing is enforced that isn't signaled by the function name?
2. **Limits and sentinels** — What values are compared, truncated, or capped? Why those specific thresholds?
3. **Bypass paths** — What code paths skip the normal flow? What triggers them?
4. **Resource asymmetry** — Where is something acquired in one place and released in another (or not at all)?
5. **Non-obvious routing** — Where does an operation get dispatched to something that isn't the obvious destination?
6. **Silent failure modes** — Where is a failure swallowed, transformed, or re-routed without the caller knowing?
7. **Explicit non-defaults** — What configuration values, flags, or parameters are set to something other than the framework/library default? For each: what would break if it were left at default?
8. **Framework departures** — Where does this code build custom machinery to do something the framework already provides? What does the custom version do that the built-in version doesn't?
9. **Deliberate failure prevention** — What code exists whose sole purpose is to prevent a specific known failure? Identify the mechanism and the failure it prevents. How would a developer know this mechanism was necessary without the context?
10. **Decision reframing** — For every mechanism found in probes 1–9, ask: *what decision does this mechanism represent?* Restate it as a choice between two alternatives — "this code chose A over B." Then ask: *what would break if B were chosen instead?* This converts a neutral observation ("the code does X") into a charged decision ("the code chose X over Y because Y causes Z"). Apply this especially to findings that describe structure without explaining why the structure exists.

Record concrete findings for each probe that fires. Format each finding as:

> **[Probe N]** [one sentence describing what you found]. Evidence: `path/to/file.ext:Lxx` — `quoted_snippet`

If a probe produces no findings for a subsystem, write "none" — don't skip it. Absence is a signal too.

---

### Phase 3b — Synthesis (extract from findings)

From the Phase 3a findings, extract four categories:

#### Decisions

What choices were made that a competent developer building from scratch would not arrive at without experience?

**Calibration — what qualifies:**
- "Token consumed at item-processed, not at queue-claim — callers assuming dequeue = consumption will build broken rate limit dashboards"
- "Sandbox name is derived from hostname then truncated to shell limit — callers must use the truncated form, not the raw input"

**Calibration — what does not qualify (skip these):**
- "Uses environment variables for secrets"
- "Validates input at the boundary"
- "Adds retry logic to external calls"

Each decision must be:
- **Self-contained** — understandable without reading the code
- **Atomic** — one decision, not a section summary
- **Non-obvious** — generic best practices don't qualify (see above)
- **Backed by evidence** — file path, line number, and a direct code quote

#### Trade-offs

Where two valid approaches existed, which was chosen, and what are the structural consequences?

Only include trade-offs where choosing wrong has architectural consequences — not just performance differences or style preferences.

Format as a table:
| Decision point | Choose A when... | Choose B when... | This codebase chose | Structural consequence |

#### Non-obvious behaviors

What does this subsystem do that would surprise a developer unfamiliar with it? These are behaviors that are **correct and intentional**, but invisible unless you know to look.

**Calibration — what qualifies:**
- *"Two-level tenant dispatch routes work over a single master queue using a priority envelope — consumers that read the queue directly will miss tenant isolation"* ✓

**Calibration — what does not qualify:**
- *"Returns an error on invalid input"* ✗
- *"Uses a connection pool"* ✗

#### Structural anti-patterns

Where the **current code** is missing a mechanism, has a disabled fallback, or has a pattern that will fail under identifiable conditions. These are not git-history rules — they are structural problems visible in the code today.

Each entry:
- **What's wrong** (one sentence): the specific code structure or absence
- **What breaks in production** (one sentence): the identifiable failure mode
- **What the correct structure looks like** (one sentence): the fix

Note: anti-patterns belong here only if they're structural — embedded in how the code is currently written. If the pattern comes from a git history incident ("we added this rule after X broke"), it belongs in `directives.md`, not here.

---

### Write and release — after each Phase 3b

Immediately after completing Phase 3b for the current subsystem:

1. **Append** this subsystem's section to `_analysis/design.md`:

```markdown
## {Subsystem Name}

### Decisions
- **[Decision statement]** `[codebase|technology]` — [what it prevents; what goes wrong without it]. Evidence: `path/to/file.ext:Lxx` — `quoted_snippet`

### Trade-offs
| Decision point | Choose A when... | Choose B when... | This codebase chose | Structural consequence |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

### Non-obvious behaviors
- **[Behavior description]** `[codebase|technology]` — [why it works this way and what a developer calling into this subsystem needs to know]. Evidence: `path/to/file.ext:Lxx` — `quoted_snippet`

### Structural anti-patterns
- **[What's wrong]** — [What breaks in production]. Correct structure: [one sentence]. Evidence: `path/to/file.ext:Lxx` — `quoted_snippet`

---
```

Omit any section that has no qualifying findings. Do not write empty headers.

2. **Release** — stop referencing this subsystem's source files. Do not re-read them. Move to the next subsystem and repeat from Phase 3a.

---

### Phase 3c — Cross-subsystem pattern assembly

After all subsystems have been written to disk, read `_analysis/design.md` in full. Look **across** the written subsystem sections for patterns.

Ask one question: **Do any 2+ findings from different subsystems all serve the same architectural concern?**

For each group found:
- Name the concern (e.g. "context degradation prevention", "security layering", "deterministic operation optimization")
- List the contributing subsystems and which finding from each contributes
- Write 2–3 sentences on how the pieces work together as a coherent approach
- Note which single finding would be most misleading if promoted alone, without the others

Also identify: what are the **3–5 most important architectural decisions** in this codebase overall — not per subsystem, but globally? These are the decisions where getting it wrong would require rearchitecting a significant portion of the system.

Record each assembled pattern as:

> **Pattern: {concern name}**
> Subsystems: {list}
> How they compose: {2–3 sentences}
> What breaks without any one piece: {1 sentence per contributing finding}
> Scope: [technology|codebase]

If no cross-subsystem patterns emerge — all findings are genuinely independent — write "none" and continue. Do not force patterns where they don't exist.

---

Tag each finding with scope:
- `[technology]` — the pattern applies to any team in a similar technical situation, regardless of their data model, business rules, or product. The evidence may cite internal names, but the lesson does not depend on them.
- `[codebase]` — the pattern is genuinely system-specific: understanding it requires knowing this team's data model, business rules, or internal architecture. Another team would not benefit from it.

**Tiebreaker:** If unsure, ask — "would a coding assistant get this wrong without being told, even on a different codebase with the same technical setup?" If yes, tag `[technology]`.

---

## Step 4 — Finalize `_analysis/design.md`

All subsystem sections were written during the Phase 3a+3b loop. This step appends the remaining sections.

**If Phase 3c found assembled patterns**, append:

```markdown
## Architectural patterns

### {Pattern name}
**Concern:** {what problem this pattern solves}
**Subsystems involved:** {list}
**How they compose:** {2–3 sentences — how the pieces work together as a coherent system}
**What breaks without any one piece:** {1 sentence per contributing finding}
**Scope:** [technology|codebase]
```

Omit this section entirely if Phase 3c found none.

**Rules that apply to all written content (enforce during the loop, not only here):**
- No imperative rules ("don't do X", "always do Y") — those belong in `directives.md`
- No historical evolution ("was added in March", "replaced X in 2024") — that belongs in `architecture.md`
- Every entry needs a file:line reference **and** an inline code quote — a reference without a quote is insufficient
- Trade-off table: only include rows where the wrong choice has structural consequences
- Skip any subsystem where all findings are obvious best practices — write nothing rather than write noise
- Structural anti-patterns: only include patterns visible in the current code, not patterns derived from git history

---

## Quality checks before finishing

- [ ] Every decision entry is non-obvious — would a competent developer arriving cold arrive at this without production experience?
- [ ] Every structural anti-pattern identifies a production failure mode, not just a style concern
- [ ] Phase 3a probe findings were written before Phase 3b synthesis — synthesis came from findings, not from the expectation of findings
- [ ] Each subsystem section was written and source files released before moving to the next subsystem
- [ ] Phase 3c (cross-subsystem synthesis) ran — either assembled patterns are recorded in `## Architectural patterns`, or "none" was explicitly noted
- [ ] Probes 7–9 (non-defaults, framework departures, failure prevention) were applied — absence of findings for each was explicitly noted, not silently skipped
- [ ] Probe 10 (decision reframing) was applied — every significant mechanism finding has been restated as "chose A over B, because B causes Z"

After writing, tell the developer:
- How many decisions, trade-offs, non-obvious behaviors, and structural anti-patterns were found
- Which subsystems had the highest decision density
- Which findings are `[technology]`-scoped and may be worth feeding into `/synthesize` (Claude Code) or `@synthesize` (Cursor)
- How many assembled patterns were found in Phase 3c, and their names — these are strong `/synthesize` (Claude Code) or `@synthesize` (Cursor) candidates and should be promoted as units, not as individual findings
