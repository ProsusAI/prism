---
name: run-history-pipeline
description: Mine this repository's git history for failure-mode practices and extract them as reusable skills, one step at a time, using /clear between steps to prevent context blowup.
---

## When to use this skill

Extract failure-mode practices from a repository's git history. Runs two steps in order, with a `/clear` between them:

1. `mine-history` → reads git log, produces `_analysis/directives.md`, `_analysis/architecture.md`, and `_analysis/incidents.md`
2. `synthesize` → reads `_analysis/incidents.md`, produces `_analysis/extracted_skills_history/*/SKILL.md` + `plugin.json`

Supports `--from [step-name]` to start from a specific step, e.g. `/run-history-pipeline --from synthesize`.

> **Note:** This pipeline is optional. If you only want to analyze the codebase's current design (not its history), run `/run-analysis-pipeline` instead.

---

## Step 1 — Read pipeline state

Check for `_analysis/.history-pipeline-state`. Read it if it exists.

State file format:
```
completed: mine-history
next: synthesize
remaining:
published: false
```

Parse `completed`, `next`, `remaining`, and `published` fields. If the file doesn't exist, all steps are pending and `mine-history` is next.

If `--from [step-name]` was passed:
- Set `next` to the specified step
- Set `completed` to all steps that precede it in the pipeline order
- Set `remaining` to all steps that follow it
- Proceed with this overridden state (do not require a state file to exist)

If the state file shows both steps completed and `published: false` (or `published` field absent):

> "All 2 pipeline steps are done. Skills are in `_analysis/extracted_skills_history/`.
>
> Run `/curate-skills` to review and clean up, then `/publish-skills` to create a PR."

Then stop.

If the state file shows all steps completed and `published: true`:

> "Pipeline complete and skills already published."
>
> "To re-run from a specific step: `/run-history-pipeline --from [step-name]`"

Then stop.

Tell the developer the current state:
```
Pipeline state:
  ✓ mine-history (done)
  → synthesize (next)
```

Use `✓` for completed, `→` for next (about to run), `·` for pending.

---

## Step 2 — Run the current step

Read the SKILL.md for the current step from `.claude/skills/[step-name]/SKILL.md` and execute it fully.

**Step name mapping:**
- `mine-history` → `.claude/skills/mine-history/SKILL.md`
- `synthesize` → `.claude/skills/synthesize/SKILL.md`

**Important:** Run the step as written — do not skip its human-in-the-loop stages, do not abbreviate its analysis, do not shortcut its confirmation checkpoints. The full interactive flow is the point.

If the developer provided context in Step 2, use it to inform how you approach the step — treat it as additional background that the step's skill didn't have.

---

## Step 3 — Update state and prompt for /clear

After the step completes successfully:

1. Write the updated state to `_analysis/.history-pipeline-state`:
   - Move the just-completed step from `next` to `completed`
   - Set `next` to the first remaining step (if any)
   - Update `remaining` accordingly
   - Always include `published: false` if not already present

   Example after completing `mine-history`:
   ```
   completed: mine-history
   next: synthesize
   remaining:
   published: false
   ```

   After completing `synthesize`:
   ```
   completed: mine-history, synthesize
   next:
   remaining:
   published: false
   ```

2. If more steps remain:

   > "---"
   > "**[step-name] complete.**"
   > ""
   > "Type `/clear` to free context, then `/run-history-pipeline` to continue with **[next-step-name]**."

3. If all 2 steps are done:

   Generate the report section:
   - Read `_analysis/.meta` for `repository` and `source`. Read every `plugin.json` under `_analysis/extracted_skills_history/*/plugin.json`.
   - For each file extract: `name`, `category` (join the array with `, `), and `description` (trim at first ` TRIGGER` occurrence)
   - Write or update `_analysis/report.md`:
     - If the file does not exist, create it
     - Replace content between `<!-- history-start -->` and `<!-- history-end -->` markers with the new section; if the markers are absent, append it
   - Section format:
     ```
     <!-- history-start -->
     # Extracted from: {repository} · {DD-MM-YYYY} · {source}

     ## Git History Pipeline

     | Skill | Category | Description |
     |-------|----------|-------------|
     | {name} | {category} | {description} |
     <!-- history-end -->
     ```
   - If `_analysis/extracted_skills_history/` is empty or absent, write the table headers with a single row: `| — | — | No skills extracted. |`

   Then tell the developer:

   > "---"
   > "**History pipeline complete.**"
   > ""
   > "N skill(s) written to `_analysis/extracted_skills_history/`. Report saved to `_analysis/report.md`."
   > ""
   > "Type `/clear` to free context, then run `/curate-skills` to review before publishing."
