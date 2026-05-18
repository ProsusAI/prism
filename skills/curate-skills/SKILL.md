---
name: curate-skills
description: "Post-extraction quality pass over _analysis/extracted_skills_history/ and _analysis/extracted_skills_codebase/ — applies three tests to every skill and proposes keep, delete, merge, or rewrite. TRIGGER when: finishing `/extract-skills` (Claude Code) or `@extract-skills` (Cursor), `/synthesize` (Claude Code) or `@synthesize` (Cursor), or `/synthesize-decisions` (Claude Code) or `@synthesize-decisions` (Cursor), reviewing extracted skills before publishing, cleaning up duplicate or framework-specific skills, running `/curate-skills` (Claude Code) or `@curate-skills` (Cursor) after any extraction step."
---
## When to use this skill

Post-extraction cleanup pass over `_analysis/extracted_skills_history/` and `_analysis/extracted_skills_codebase/`. Applies three tests to every existing skill and proposes one of four actions: **keep**, **delete**, **merge**, or **rewrite**. Produces a curation report and waits for developer confirmation before making any file changes.

---

## Step 1 — Read all extracted skills

Read every `SKILL.md` file under `_analysis/extracted_skills_history/` and `_analysis/extracted_skills_codebase/`. If both directories are absent or empty, stop:

> "No skills found in `_analysis/extracted_skills_history/` or `_analysis/extracted_skills_codebase/`. Run `/run-history-pipeline` (Claude Code) or `@run-history-pipeline` (Cursor), or `/run-analysis-pipeline` (Claude Code) or `@run-analysis-pipeline` (Cursor), first."

For each skill, record:
- Name and file path (including which directory it came from)
- Description (the full description field — this determines when the skill loads)
- Format: failure-mode skill OR key-decisions skill
- The list of key decisions or failure modes (titles only)
- Status

Do not summarize or collapse at this stage — you need the full content of each skill to apply the tests.

---

## Step 2 — Apply Test 1: Would Claude already know this?

For each skill independently, ask: **can the correct decision be derived from official documentation, standard programming principles, or general production engineering knowledge — without having encountered this failure in production?**

Apply these three concrete checks:

1. **Documentation check** — is this behavior explicitly covered in the library or framework's official docs, migration guide, or getting-started tutorial? If the docs say "do X in this situation", the skill adds no value.

2. **First-principles check** — is this a standard pattern any experienced developer would reach by reasoning? Examples of things Claude already knows: connection pool lifecycle (close() clears a reference, not the pool), async isolation via ContextVar, fail-open for cache reads, RAII patterns, thread-safety in global state.

3. **Derivability check** — would a developer with no specific production experience with this technology reach the correct decision? If the skill requires a production failure to become obvious, it's worth keeping. If a careful developer reading the docs would get it right, it isn't.

If **all three checks say yes** → mark **DELETE**. The skill doesn't add value over what Claude brings to any conversation.
If **any check says no** → continue to Test 2.

**When in doubt, keep.** A false DELETE is more costly than a false KEEP — a deleted skill is gone; an extra skill just loads occasionally.

---

## Step 3 — Apply Test 2: Is this redundant?

Compare remaining skills against each other. Flag pairs where one skill is substantially subsumed by another.

Apply these checks for each pair:

1. **Decision overlap** — do they share more than half their key decisions or failure modes, teaching the same lesson at the same abstraction level?

2. **Subsumption** — would a developer who has read Skill A gain nothing new from Skill B? (One-directional: A might subsume B without B subsuming A.)

3. **TRIGGER collision** — do their description TRIGGER conditions overlap significantly, meaning they'd both load in the same situation?

If a pair is redundant → mark **MERGE**: identify the better skill to keep (better name, richer decisions, cleaner format), absorb any unique decisions from the weaker one, then delete the weaker file.

If no pair is redundant → continue to Test 3.

---

## Step 4 — Apply Test 3: Is the lesson framework-specific or just the evidence?

For each remaining skill, ask: **if you strip the framework class names, method names, and config flags, does the core lesson still hold — and would it apply to a developer using a different framework with the same structural pattern?**

Apply these checks:

1. **Name test** — does the skill name contain a framework name (e.g. `langgraph-`, `redis-`, `openai-`) that is load-bearing? Or is it incidental — the framework is just where the evidence comes from?

2. **Decision test** — restate each key decision without the framework-specific vocabulary. Does it still make sense? Example: "Call `.pop()` on LangGraph state flags before LLM invocation" restates as "consume one-turn signals destructively before the operation that reads them" — the framework is incidental, the lesson is about ephemeral signal lifecycle in any stateful system.

3. **Transfer test** — would a developer using a different framework with the same structural pattern (e.g. a different agent framework, a different cache library) benefit from this skill? If yes, the lesson generalizes.

If **lesson generalizes, evidence is framework-specific** → mark **REWRITE**:
- Broaden the title to name the pattern, not the framework (e.g. `stateful-agent-ephemeral-signals` instead of `langgraph-routing-signal-design`)
- Generalize description and TRIGGER conditions to fire for any framework with the pattern
- Keep the framework-specific code in the structural template as the primary example
- Add a note: "Evidence from: [framework/technology]"

If **lesson is genuinely framework-specific** — the framework's behavior is the thing being taught, not just the vehicle for a broader lesson → mark **KEEP as-is**. The framework name in the title is correct; the skill should only trigger for that framework.

**Edge case — partially generalizable:** If 2 of 4 decisions generalize and 2 are framework-specific, split into two concerns or keep as-is and note which decisions are transferable. Do not force a rewrite that dilutes the framework-specific decisions.

---

## Step 5 — Produce curation report

Before making any changes, present the full report. One entry per skill:

```
ACTION   skill-name
         Reason: {1-2 sentences — which test flagged it and why}
         {For MERGE: "Merge into: target-skill-name. Unique decisions to absorb: [list]"}
         {For REWRITE: "New name: proposed-name. Changes: [title, description, decisions — which change and how]"}
```

End with a summary count:
```
Summary: {N} keep, {N} delete, {N} merge ({N} skills → {N}), {N} rewrite
Net change: {N} skills before → {N} after
```

Then ask:
> "Confirm all actions, or tell me which ones to override. You can override individual actions — e.g. 'keep redis-connection-pool-close-semantics even though it would be deleted'."

Wait for the developer's response. Apply any overrides they specify. Then proceed to Step 6.

---

## Step 6 — Execute confirmed actions

Execute in this order to avoid path conflicts. Write all changes back to the same directory the skill was read from (`extracted_skills_history/` or `extracted_skills_codebase/`):

1. **Merges first** — write the merged SKILL.md to the target skill's file, then delete the source skill's directory
2. **Rewrites** — write the rewritten SKILL.md in place (same directory, updated content). Also update `plugin.json` in the same directory: set `name` to match the new skill name, and update `description` to match the new SKILL.md frontmatter description (which must contain the updated TRIGGER clause). Preserve all other `plugin.json` fields (`author`, `repository`, `category`, `source`, `commit_date`, `source_hash`). Rename the directory if the name changed.
3. **Deletes** — remove the skill directory entirely
4. **Keeps** — no action

---

## Step 7 — Report final state

Tell the developer:
- Final count of skills and their names

Do **not** update `incidents.md` or `design.md`. Curation operates only on `_analysis/extracted_skills_history/` and `_analysis/extracted_skills_codebase/`.
