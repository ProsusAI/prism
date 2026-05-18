# Prism

A knowledge layer for Claude Code adn Cursor. Prism watches how you work, learns your preferences, and makes Claude/Cursor remember them across sessions. For teams, it lets you share proven architectural knowledge through a shared registry.

**One install. Zero config for personal use. Registry config for teams.**

## What it does

**Personal learning** — Prism observes your sessions through hooks. When it sees recurring patterns (you always prefer TypeScript strict mode, you correct a certain approach, you follow a specific deployment procedure), it extracts those into "engrams" — living knowledge units that strengthen with evidence and decay without use.

**Team knowledge** — Promote your best engrams into publishable skills, or run slash commands to mine your codebase and git history for architectural patterns. Publish them to a team registry so everyone benefits.

## Get started

This walkthrough takes you from install to your first extracted knowledge using Claude Code, same applies for Cursor. Follow steps in order — each has a check so you know it worked.

### 1. Install

```bash
git clone https://github.com/ProsusAI/prism.git && cd prism
./install.sh
```

Requirements: Python 3.12+, git, [Claude Code](https://claude.ai/code) or [Cursor](https://cursor.com). The installer creates `~/.prism/` and symlinks the `prism` CLI to `~/.local/bin/prism`. Safe to re-run on upgrades.

**Check:** `prism --help` prints usage. If you get "command not found", add `~/.local/bin` to your PATH — the installer will have warned you if it's missing.

### 2. Initialize in an active project

Pick a project you're actively working on. Prism learns from real sessions, so choose somewhere you'll actually use it this week.

```bash
cd ~/your-project
prism init
```

**Check:** `.claude/settings.local.json` contains a `PreToolUse` hook pointing to `~/.prism/hooks/capture.sh`. That hook is how Prism observes your sessions.

### 3. Teach a preference

Before waiting for automatic extraction, teach Prism something you know you always want.

```bash
prism learn "always use conventional commits in this project"
```

**Check:** `cat .claude/prism.md` shows the preference. `prism status` lists it with confidence `0.90` — that's the manual-teach starting confidence.


### 4. Let Prism learn from your previous sessions

If you have existing sessions, mine them immediately with commands below. If not, run two or three sessions on the project first. Prism will automatically start learning your behaviour

```bash
prism analyze-sessions --last 5   # prints session IDs with observation counts
prism extract                     # runs the extraction pipeline
```

Then check what came out:

```bash
prism status              # active engrams grouped by kind, with confidence scores. More details in prism.md
prism log --extractions   # validation decisions (APPROVED / REJECTED / MODIFIED) and why
prism log --rejected      # rejected candidates with failing gate reasons
```

### 5. Correct a preference

Corrections are more powerful than teaches — they replace a specific engram and bump confidence. Try it now so you know how it works before you need it.

```bash
prism status          # copy the ID of the entry you just created
prism correct <id> "always use conventional commits, never squash merge"
prism status          # old entry gone, new one at confidence 0.90
```

### 6. Search a past session

Prism can retrieve something specific you discussed in a past Claude session — useful for decisions you remember making but can't find. Search runs SQLite full-text under the hood, so use concrete words rather than paraphrased intent: `"retry backoff"` finds more than `"how we handle failures"`.

```bash
prism analyze-sessions "something specific you discussed" --last 10
```

> This is a newer feature. Try it with something you genuinely discussed — note what works well and where it misses, that feedback is valuable.

### 7. Promote an engram to a skill

Once you have an engram with real evidence, promote it into a publishable skill.

```bash
prism status           # find an engram with confidence >= 0.7 and evidence >= 3
prism promote <id>     # creates _analysis/extracted_skills_codebase/<skill-name>/ with plugin.json and SKILL.md
```

The skill directory is ready to publish to your team registry or contribute upstream.

---

## Commands

**Manage knowledge**

```bash
prism learn "Always use pnpm, never npm"    # teach a preference
prism correct <id> "Use vitest not jest"    # replace an engram
prism forget <id>                           # remove an engram
prism status                                # show active engrams with confidence scores
```

**Observe and extract**

```bash
prism log --last 20                # recent observations
prism log --extractions            # extraction validation decisions
prism log --rejected               # rejected candidates with failing gate reasons
prism extract                      # run the extraction pipeline
prism analyze-sessions --last 10   # mine past Claude sessions
```

## Team skills

```bash
prism promote <engram-id>      # promote a well-validated engram to a publishable skill

# Slash commands in Claude Code
/run-analysis-pipeline    # full codebase analysis
/run-history-pipeline     # git history to skills
/extract-skills           # analysis reports to skills
/curate-skills            # quality pass
/publish-skills           # publish to team registry
/advise-skills            # query registry for advice
/audit-code               # audit code against known patterns
```

## How it works

Prism has two channels for getting knowledge into Claude Code or Cursor:

**Push** — `.claude/prism.md` and `.cursor/rules/prism.md` are auto-generated with your highest-priority knowledge (corrections, pinned items, top preferences). Claude Code and Cursor read this at session start.

**Pull** — An MCP server exposes `prism_search`, `prism_get`, `prism_relevant`, and `prism_record` tools. Claude and Cursor queries these mid-session when they need specific knowledge.

Engrams have a lifecycle: they start at a base confidence, strengthen when the same pattern is observed again, and decay slowly without reinforcement. Run `prism maintain` periodically to keep things fresh.

## Configuration

```bash
prism config                        # show all settings
prism config extract_threshold 20   # change a setting
```

Key settings: `extract_threshold` (observations before auto-extraction), `decay_rate_per_week`, `max_context_lines` (prism.md size), `registry_url` (team registry). Config lives at `~/.prism/config.json`.

## Project structure

```
~/.prism/
  config.json          # Settings
  global/engrams/      # Cross-project knowledge
  projects/<hash>/     # Per-project observations + knowledge
  lib/                 # Python library
  hooks/               # Claude Code hooks
  agents/              # AI agent prompts (extractor, validator, reviewer)
  skills/              # Slash commands
  schemas/             # Validation schemas
```

## See also

[DOCS.md](DOCS.md) -- Comprehensive technical documentation covering architecture, data formats, extraction pipeline, MCP protocol, slash commands, and configuration reference.

[prism_commands.md](prism_commands.md) -- Comprehensive list of user commands, claude skills and MCP tools. 
