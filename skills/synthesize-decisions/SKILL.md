---
name: synthesize-decisions
description: "Promote design decisions from _analysis/design.md into normative practice skills — guidance that loads before a developer makes the wrong choice. TRIGGER when: _analysis/design.md exists and is ready to promote, running `/synthesize-decisions` (Claude Code) or `@synthesize-decisions` (Cursor) after `/mine-design` (Claude Code) or `@mine-design` (Cursor), extracting design-decision practices from a codebase snapshot analysis."
---

## When to use this skill

Promote design decisions from `_analysis/design.md` into normative practices — guidance that loads **before** a developer makes the wrong choice, not after they hit a bug. Complements `/synthesize` (Claude Code) or `@synthesize` (Cursor) (which promotes failure-mode practices from incident history and assembled cross-subsystem patterns).

Run this after `/mine-design` (Claude Code) or `@mine-design` (Cursor). Run `/synthesize` (Claude Code) or `@synthesize` (Cursor) separately for incident-history practices.

---

## Step 1 — Read inputs

Read `_analysis/design.md` fully. If it doesn't exist, stop and tell the developer:

> "`_analysis/design.md` not found. Run `/mine-design` (Claude Code) or `@mine-design` (Cursor) first."

Read all sections: decisions, trade-offs, non-obvious behaviors, structural anti-patterns, and the `## Architectural patterns` section. Record every finding.

Also list all directories under `_analysis/extracted_skills_codebase/`. Read the `description` field from each existing `SKILL.md`. Any decision already covered by an existing practice is skipped — do not duplicate.

---

## Step 2 — Apply 7 concern lenses

Re-read every design.md finding through each of these 7 lenses. A finding can be relevant to more than one lens. Collect findings into concern clusters — you are grouping by *class of problem*, not by subsystem.

The probes 7–9 findings from mine-design are especially relevant here (explicit non-defaults, framework departures, deliberate failure prevention) — start with those.

---

### Concern 1: Shared state and isolation
*Where state that should be scoped to one request, coroutine, or session accidentally escapes into a wider scope.*

Look for: process-global state set per-request, shared mutable objects accessed concurrently, missing per-coroutine isolation in async frameworks, global registries modified at runtime.

**Framing question:** What breaks under concurrent load that single-threaded testing never reveals?

---

### Concern 2: Error handling and degradation
*Where the system's choice to absorb, propagate, or retry errors is non-obvious.*

Look for: exceptions caught and silently swallowed, fail-open vs. fail-closed decisions, which error subtypes trigger retry vs. fail-fast, custom error handling in place of framework defaults.

**Framing question:** What fails in production under real error rates when using standard propagation or blanket retry?

---

### Concern 3: Persistence and ephemerality
*Where something persists longer than it should, or expires earlier than expected.*

Look for: signals consumed with `.pop()` instead of `.get()`, TTL defaults that are wrong for some callers, data written to persistent state that should be transient, state that accumulates across sessions when it should be reset.

**Framing question:** What accumulates incorrectly or expires too early when using the same persistence default everywhere?

---

### Concern 4: Framework defaults
*Where the framework's recommended or default behavior is wrong for this use case.*

Look for: settings explicitly overridden from their documented default, custom classes built instead of using framework built-ins, framework features intentionally bypassed, probe-8 findings (framework departures).

**Framing question:** What fails when all framework settings are left at their getting-started defaults?

---

### Concern 5: Security 
*Where standard practices leave gaps specific to this system's shape.*

Look for: input validation that is deliberately limited or disabled, security measures that require multiple components to be effective, capability gating decisions, error response shaping to prevent information leakage.

**Framing question:** What attack surface remains after standard validation, given how this system specifically processes input?

---

Before applying Concerns 6 and 7, ask the user:

> "Apply optional lenses?
> - **Concern 6: Load and connection behavior** — connection pools, buffering, concurrency under load. Relevant for services with concurrent request handling.
> - **Concern 7: Fan-out and pipeline resilience** — parallel subtasks, deduplication, rate limit exhaustion, partial failure recovery. Relevant for systems with recursive processing, parallel workers, or multi-step pipelines."

Apply only the lenses the user confirms. Skip any the user declines and move to Step 3.

### Concern 6: Load and connection behavior
*Where behavior changes at scale or under concurrent load in ways that local testing doesn't reveal.*

Look for: connection pool semantics, buffering decisions (what is held in memory vs. streamed), initialization timing (startup vs. first-use), behavior under concurrent requests.

**Framing question:** What behavior is wrong under concurrent or sustained load but passes all single-request tests?

---

### Concern 7: Fan-out and pipeline resilience
*Where a system spawns concurrent or recursive subtasks and must control redundant work, partial failures, and resource exhaustion.*

Look for: deduplication state shared (or not shared) across spawned instances, caching of external calls scoped to a pipeline run, concurrency controls sized to external API limits rather than local compute, checkpointing of intermediate results, semaphore + rate limiter combinations.

**Framing question:** When subtasks each manage their own state and limits independently, what gets duplicated, what exhausts external rate limits, and what is lost on partial failure?

This concern applies to any system with recursive processing, parallel workers, or multi-step pipelines — not just AI agents.

---

## Step 3 — Apply the normative quality bar

For each concern cluster, evaluate against this bar.

**Required — all must be true:**

1. **Natural default is wrong.** There is an obvious or documented approach that produces incorrect behavior specifically in this context. The mistake is not a careless error — it is what a careful developer would do by following standard guidance.

2. **Fails in production, not in tests.** The wrong approach passes unit tests and integration tests with controlled inputs. It only fails under production conditions: concurrent load, long-running sessions, specific error rates, real input variation.

3. **Actionable at design time.** A developer can act on this before making the mistake. It changes how they design or configure the system, not just how they debug after the fact.

**Scope rule:**
`[codebase]`-tagged findings may be promoted if the underlying concern generalizes to other codebases facing the same design decision. Strip all codebase-specific names from the output.

**Disqualifiers:**
- The framework explicitly documents the correct choice as its recommendation — skip, it's already covered
- The failure would be caught in unit tests with reasonable test coverage — skip
- The correct choice depends on this codebase's specific business rules — skip
- Already covered by an existing practice in `_analysis/extracted_skills_codebase/` — skip

**Verdicts:**
- **Qualifies** — meets all 3 required criteria, no disqualifiers
- **Framework-documented** — the framework recommends the correct approach; name the doc
- **Observable in tests** — caught before production; skip
- **Business-specific** — depends on this team's domain rules; skip
- **Already covered** — note which existing practice covers it

---

## Step 4 — Collect metadata

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
- `category` → suggested per practice based on concern type; applied directly

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

## Step 5 — Write each practice

Write two files to `_analysis/extracted_skills_codebase/{practice-name}/`:

---

### SKILL.md

Frontmatter: `name` and `description` only. All registry metadata lives in `plugin.json`.

```markdown
---
name: {practice-name}
description: "{1-sentence summary of what this skill enables or prevents}. TRIGGER when: {comma-separated coding/design moments — name the action, not the symptom; e.g. 'configuring error handling for a service with an external cache dependency', 'choosing between framework-provided and custom session state', 'designing TTL policy for a multi-endpoint service'}."
---

# {Practice Title}
*{1-sentence: what this practice prevents or enables.}*

## Key decisions

1. {Decision statement — imperative voice.} Without this, {failure description — include the condition that triggers it in production and why testing misses it}.

2. {Decision statement.} Without this, {failure description.}

{3–6 decisions total — no sub-headers, no **Why:** blocks, just the decision and its inline consequence}

## Anti-patterns

- **What**: {What a developer would naturally do — phrased as the action}
- **Why**: {The mechanism — why this fails in this specific context, not generically}
- **Symptom**: {Observable failure — when it appears, what the developer or user sees}

{one entry per key decision — keep each to 3 lines}

## Structural template

\`\`\`
{Pseudocode showing the correct shape — not runnable, structural.
Show: non-default settings in place, correct call-site patterns, prevention mechanisms positioned correctly.
Aim for 15–30 lines.}
\`\`\`
```

**Format rules:**
- Decisions are 2-3 sentences each: the choice + the inline consequence. No headers, no bold labels.
- TRIGGER conditions name *actions* a developer takes, not symptoms they observe.
- Anti-patterns are 3 lines each. The symptom must include *when* it manifests.
- The structural template is a skeleton — show decisions made concrete, not full implementations.

---

### plugin.json

Read `~/.prism/schemas/plugin.schema.json` for the authoritative field specification, required fields, valid category enum, and format patterns. Write one `plugin.json` per practice that validates against it.

---

**Stripping rules** — read `~/.prism/skills/_shared/stripping-rules.md` and apply before writing.

