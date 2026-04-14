---
name: run-analysis-pipeline
description: Run the codebase analysis pipeline — routes to agentic or general path, one step at a time, using /clear between steps to prevent context blowup.
---

## When to use this skill

Analyze a codebase and extract reusable skills from it. Routes to one of two paths based on whether the codebase uses LLMs/agents or is general-purpose:

- **Agentic path**: `/analyze-agent-codebase` → `/extract-skills` *(optionally extended with `/mine-design` → `/synthesize-decisions`)*
- **General path**: `/mine-design` → `/synthesize-decisions`

Both paths write extracted skills to `_analysis/extracted_skills/`.

Supports `--from [step-name]` to restart from a specific step, e.g. `/run-analysis-pipeline --from extract-skills`.

> **Design note:** This pipeline is a coordinator, not an executor. It never runs steps inline — it hands off to each step skill directly so every step runs in a clean context window. Each invocation of `/run-analysis-pipeline` either hands off to the next step or confirms the previous step completed and hands off to the one after it.

---

## Step 1 — Read pipeline state

Check for `_analysis/.analysis-pipeline-state`. Read it if it exists.

State file format:
```
mode: agentic
extended: true
completed: analyze-agent-codebase, extract-skills
next: mine-design
remaining: synthesize-decisions
published: false
```

Parse `mode`, `extended`, `completed`, `next`, `remaining`, and `published` fields. If the file doesn't exist, no steps are completed and you need to determine the mode (Step 2).

**Step sequences by mode:**
- `agentic` (standard): `analyze-agent-codebase` → `extract-skills`
- `agentic` (extended): `analyze-agent-codebase` → `extract-skills` → `mine-design` → `synthesize-decisions`
- `general`: `mine-design` → `synthesize-decisions`

If `--from [step-name]` was passed:
- Set `next` to the specified step
- Infer `mode` from the step name (agentic-specific: `analyze-agent-codebase`, `extract-skills`; either: `mine-design`, `synthesize-decisions`)
- Set `completed` to all steps that precede it in the appropriate sequence
- Set `remaining` to all steps that follow it
- Proceed with this overridden state

**Completion artifact check:**

If the state file has a `next` step, check whether that step already completed by looking for its artifact. This handles the case where the user ran a step directly (not through the pipeline) before returning here.

| Step | Artifact that confirms completion |
|---|---|
| `analyze-agent-codebase` | `_analysis/full_report.md` exists |
| `extract-skills` | skip auto-advance — artifact is ambiguous |
| `mine-design` | `_analysis/design.md` exists |
| `synthesize-decisions` | skip auto-advance — artifact is ambiguous |

If the artifact exists for the `next` step:
1. Move that step from `next` to `completed`; set `next` to the first remaining step
2. Write the updated state file
3. Repeat the artifact check for the new `next` step (continue until a step's artifact is absent or no steps remain)

If all steps are completed and `published: false` (or absent):

> "All pipeline steps are done. Skills are in `_analysis/extracted_skills_codebase/`.
>
> Run `/curate-skills` to review and clean up, then `/publish-skills` to create a PR."

Then stop.

If all steps are completed and `published: true`:

> "Pipeline complete and skills already published."
>
> "To re-run from a specific step: `/run-analysis-pipeline --from [step-name]`"

Then stop.

---

## Step 2 — Determine mode

If the state file already has a `mode` field, skip to Step 3.

Otherwise, ask:

> "Is this codebase **agentic** (uses LLMs, tools, or an agent framework like LangGraph, AutoGen, CrewAI, etc.) or **general-purpose** (a web API, CLI, background worker, data pipeline, etc.)?
>
> This determines which analysis path to run:
> - **Agentic** → `/analyze-agent-codebase` then `/extract-skills`
> - **General** → `/mine-design` then `/synthesize-decisions`"

Wait for their response. Accept `agentic`, `agent`, `yes`, or `y` as agentic.

**If agentic**, ask a follow-up:

> "Also run **extended analysis** (`/mine-design` → `/synthesize-decisions`) to extract general architecture practices from supporting infrastructure (API layer, storage, auth, queues)?
>
> [y/N] — adds 2 more steps with a /clear between each"

Accept `y`, `yes`, or `extended` for extended mode. Default is `n`.

Write the initial state file to `_analysis/.analysis-pipeline-state`:

For standard agentic:
```
mode: agentic
extended: false
completed:
next: analyze-agent-codebase
remaining: extract-skills
published: false
```

For extended agentic:
```
mode: agentic
extended: true
completed:
next: analyze-agent-codebase
remaining: extract-skills, mine-design, synthesize-decisions
published: false
```

For general:
```
mode: general
extended: false
completed:
next: mine-design
remaining: synthesize-decisions
published: false
```

---

## Step 3 — Display current state

Show the current pipeline:

**Standard agentic example:**
```
Pipeline state (agentic):
  → analyze-agent-codebase (next)
  · extract-skills (pending)
```

**Extended agentic example:**
```
Pipeline state (agentic, extended):
  ✓ analyze-agent-codebase (done)
  ✓ extract-skills (done)
  → mine-design (next)
  · synthesize-decisions (pending)
```

**General example:**
```
Pipeline state (general):
  ✓ mine-design (done)
  → synthesize-decisions (next)
```

Use `✓` for completed, `→` for next (about to run), `·` for pending.

---

## Step 4 — Run or hand off the current step

**If `next` is `analyze-agent-codebase`:**

Do **not** read or execute its SKILL.md. It loads 7 question files during execution and will blow up the context window if run inline.

Tell the developer:

> "---"
> "**Next: /analyze-agent-codebase**"
> ""
> "Type `/clear` to free context, then run `/analyze-agent-codebase` directly."
> "When it finishes, run `/run-analysis-pipeline` to continue."

Then stop. Do not proceed further in this invocation.

**For all other steps** (`extract-skills`, `mine-design`, `synthesize-decisions`):

Read the SKILL.md for the current step from `.claude/skills/[step-name]/SKILL.md` and execute it fully.

**Important:** Run the step as written — do not skip its human-in-the-loop stages, do not abbreviate its analysis, do not shortcut its confirmation checkpoints. The full interactive flow is the point.

If the developer provided context, use it to inform how you approach the step.

---

## Step 5 — Update state and prompt for /clear

*(This step applies only to inline steps — `extract-skills`, `mine-design`, `synthesize-decisions`. For `analyze-agent-codebase`, the pipeline stopped at Step 4.)*

After the step completes successfully:

1. Write the updated state to `_analysis/.analysis-pipeline-state`:
   - Move the just-completed step from `next` to `completed`
   - Set `next` to the first remaining step (if any)
   - Update `remaining` accordingly
   - Keep `mode` and `extended` unchanged
   - Always include `published: false` if not already present

2. If more steps remain:

   > "---"
   > "**[step-name] complete.**"
   > ""
   > "Type `/clear` to free context, then `/run-analysis-pipeline` to continue with **[next-step-name]**."

3. If all steps are done:

   Generate the report section:
   - Read `_analysis/.meta` for `repository` and `source`. Read every `plugin.json` under `_analysis/extracted_skills_codebase/*/plugin.json`.
   - For each file extract: `name`, `category` (join the array with `, `), and `description` (trim at first ` TRIGGER` occurrence)
   - Write or update `_analysis/report.md`:
     - If the file does not exist, create it
     - Replace content between `<!-- analysis-start -->` and `<!-- analysis-end -->` markers with the new section; if the markers are absent, append it
   - Section format:
     ```
     <!-- analysis-start -->
     # Extracted from: {repository} · {DD-MM-YYYY} · {source}

     ## Analysis Pipeline

     | Skill | Category | Description |
     |-------|----------|-------------|
     | {name} | {category} | {description} |
     <!-- analysis-end -->
     ```
   - If `_analysis/extracted_skills_codebase/` is empty or absent, write the table headers with a single row: `| — | — | No skills extracted. |`

   Then tell the developer:

   > "---"
   > "**Analysis pipeline complete.**"
   > ""
   > "N skill(s) written to `_analysis/extracted_skills_codebase/`. Report saved to `_analysis/report.md`."
   > ""
   > "Type `/clear` to free context, then run `/curate-skills` to review before publishing."

---

## Error handling

**If a required input file is missing** (e.g., `extract-skills` is `next` but `_analysis/full_report.md` doesn't exist, or `synthesize-decisions` is `next` but `_analysis/design.md` doesn't exist):

> "`_analysis/full_report.md` not found — `/analyze-agent-codebase` must run first."

Update the state file's `next` field to `analyze-agent-codebase` and stop.

**If the developer wants to skip a step:**

Update the state file to mark that step completed and proceed to the next. Note what the skipped step would have produced.

**If a step fails mid-way:**

The state file remains unchanged (`next` stays as the failed step). Run `/run-analysis-pipeline` again to retry from the same step.

> "If the step failed partway, run `/run-analysis-pipeline` to retry. The state file was not modified."

