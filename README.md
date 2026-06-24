<div align="center">

<img src="assets/prism.png" alt="Prism" width="520" />

# Prism

**Your work, refracted into knowledge AI coding tools remember**

[Get started](#get-started) · [How it works](#how-it-works) · [Configuration](#configuration) · [Commands](#commands) 

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Dependencies: stdlib only](https://img.shields.io/badge/dependencies-stdlib--only-green.svg)](#)

</div>

A knowledge layer for Claude Code and Cursor. Prism watches how you work, learns your preferences, and makes Claude/Cursor remember them across sessions. Are you working in a team? Share learnings in form of reusable skills. 

**One install. Zero config for personal use. Registry config for teams.**

> 💡 Run `prism dashboard` to explore your projects and engrams in a local web UI.

## What it does

**Personal learning** — Prism observes your sessions through hooks (`tool_start` observations only). When the extraction pipeline finds recurring patterns, it proposes engrams — living knowledge units whose confidence rises on **use events** (MCP retrieval, session-review overlap), validator output, or extraction merge, and decays without use.

**Team knowledge** — Promote your best engrams into publishable skills, or run slash commands to mine your codebase and git history for architectural patterns. Publish them to a team registry so everyone benefits.

## Get started

This walkthrough takes you from install to your first extracted knowledge using Claude Code, same applies for Cursor. Follow steps in order — each has a check so you know it worked.

### 1. Install

```bash
git clone https://github.com/ProsusAI/prism.git && cd prism
./install.sh
```

Requirements: Python 3.12+, git, [Claude Code](https://claude.ai/code) or [Cursor](https://cursor.com). The installer creates `~/.prism/` and symlinks the `prism` CLI to `~/.local/bin/prism`. Safe to re-run on upgrades.

> **Extraction needs an IDE agent CLI — only the one you use.** Observations are captured automatically; engrams require either the **`claude` CLI** (Claude Code: fast `haiku` + strong `sonnet`) or the **`agent` CLI** (Cursor: `composer-2.5[fast=false]` + `claude-4.6-sonnet-medium`). You do **not** need both CLIs, the Anthropic SDK, cursor-sdk, or API keys — just IDE CLI login:
> - **Claude Code:** `claude login`
> - **Cursor:** `curl https://cursor.com/install -fsS | bash` then `agent login`

**Check:** `prism --help` prints usage. If you get "command not found", add `~/.local/bin` to your PATH — the installer will have warned you if it's missing.

### 2. Initialize in an active project

Pick a project you're actively working on. Prism learns from real sessions, so choose somewhere you'll actually use it this week.

```bash
cd ~/your-project
prism init
```

**Check:** `prism init` wires both IDEs (unused integration is harmless). Verify the hook for the IDE you use:
- **Claude Code:** `.claude/settings.local.json` has a `PreToolUse` hook → `capture.sh` (plus `SessionStart` → `prism maintain --quiet`)
- **Cursor:** `.cursor/hooks.json` has a `preToolUse` hook → `capture_cursor.sh`

### 3. Teach a preference

Before waiting for automatic extraction, teach Prism something you know you always want.

```bash
prism learn "always use conventional commits in this project"
```

**Check:** Context file shows the preference — `.claude/prism.md` (Claude Code) or `.cursor/rules/prism.mdc` (Cursor). `prism status` lists it with confidence `0.8` — the manual-teach starting confidence.


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
prism status          # old entry gone, new one at confidence 0.8
```

### 6. Search a past session

Prism can retrieve something specific you discussed in a past session — useful for decisions you remember making but can't find. Search runs SQLite full-text under the hood, so use concrete words rather than paraphrased intent: `"retry backoff"` finds more than `"how we handle failures"`. Works for Claude Code and Cursor session transcripts.

```bash
prism analyze-sessions "something specific you discussed" --last 10
```

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
prism log --last 20                      # recent observations
prism log --extractions                  # extraction validation decisions
prism log --rejected                     # rejected candidates with failing gate reasons
prism extract [--backend claude|cursor]  # run extraction (backend auto-detected by default)
prism analyze-sessions --last 10         # mine past Claude Code or Cursor sessions
prism sync                               # regenerate context files from active engrams
prism maintain                           # run confidence decay (Claude Code: also at session start)
```

## Team skills

```bash
prism promote <engram-id>      # promote a well-validated engram to a publishable skill

# Slash commands in Claude Code (Cursor: same skills as rules in .cursor/rules/)
/run-analysis-pipeline    # full codebase analysis
/run-history-pipeline     # git history to skills
/extract-skills           # analysis reports to skills
/curate-skills            # quality pass
/publish-skills           # publish to team registry
/advise-skills            # query registry for advice
/audit-code               # audit code against known patterns
```

### Public registry

Prism ships with a public read-only registry (`prism-open-source`) pre-configured at **install** (`~/.prism/registries.json`). No project setup required — query it after install:

```bash
prism registry list           # confirm prism-open-source is configured
/advise-skills                # query the registry for patterns relevant to your question
/audit-code                   # surface registry skills that apply to the current codebase
```

It is read-only — you cannot publish to it. To share your own team's skills, [set up a private registry](DOCS.md).

## How it works

Prism has two channels for getting knowledge into Claude Code or Cursor:

**Push** — `.claude/prism.md` and `.cursor/rules/prism.mdc` are auto-generated with your highest-priority knowledge: pinned entries, corrections, then preferences (up to 10 entries by kind — not by confidence score). The IDE reads these at session start. Placement does **not** boost confidence.

**Pull** — An MCP server exposes `prism_search`, `prism_get`, `prism_relevant`, and `prism_record` tools. The model queries these mid-session when it needs specific knowledge. MCP retrieval fires a daily-idempotent confidence boost on matched engrams.

Engrams have a lifecycle: they start at a base confidence, strengthen on use events (MCP retrieval or session-review overlap for pushed knowledge), via validator output or extraction merge — **not** on each repeated hook observation — and decay exponentially toward a floor without use. Run `prism maintain` periodically — Claude Code runs this automatically at session start (once per day); Cursor users should run it manually. See [DOCS.md](DOCS.md#engram-lifecycle) for the full model.

**Observation compression** — before any observation reaches the database, it goes through a compression pass that strips fillers, hedges, pleasantries, and articles from prose while leaving code blocks, file paths, URLs, commands, identifiers, version numbers, and dates completely unchanged. This reduces storage noise and keeps the context fed into the extraction pipeline tighter. All observations are stored at `intensity='lite'` by default. The compression logic is a modified version of [Cavemem](https://github.com/JuliusBrussee/cavemem)'s approach.

### Claude Code, Cursor, or both

Prism supports three usage patterns on the same project:

| Pattern | What you need | Extraction CLI |
|---------|---------------|----------------|
| **Claude Code only** | `claude` + `claude login` | `claude` (`haiku` / `sonnet`) |
| **Cursor only** | `agent` + `agent login` | `agent` (configured `cursor_models`) |
| **Mixed** (team uses both IDEs) | Whichever CLIs your team uses | Auto: hook uses the **calling IDE**; manual `prism extract` picks unanimous pending source, or `mixed_backend_preference` when sources are mixed |

Observations are tagged `claude_code` or `cursor` at capture time. `prism status` shows pending source mix when relevant. Override anytime: `prism extract --backend claude` or `--backend cursor`.

## Configuration

```bash
prism config                        # show all settings
prism config extract_threshold 20   # change a setting
```

Key settings: `extract_threshold` (observations before auto-extraction), `agent_backend` (`auto`, `claude`, or `cursor`), `mixed_backend_preference` (which CLI to prefer when pending observations are mixed), `cursor_models` (fast/strong model IDs for the `agent` CLI), `reinforce_alpha` / `confidence_ceiling` (use-event boost), `decay_half_life_weeks` / `decay_grace_days` / `decay_floor` (idle decay), `max_context_lines` (context file size). Team registries live in `~/.prism/registries.json`. Effective defaults are merged at runtime from `lib/config.py` — a fresh `config.json` from `install.sh` may list only a subset. Full reference in [DOCS.md](DOCS.md#configuration-reference).

## Project structure

```
~/.prism/
  config.json          # Settings
  prism.db             # SQLite database — all observations + FTS5 index (shared across projects)
  global/engrams/      # Cross-project knowledge
  projects/<hash>/     # Per-project engrams
  lib/                 # Python library
  hooks/               # Claude Code + Cursor capture hooks
  agents/              # AI agent prompts (extractor, validator, reviewer)
  skills/              # Slash commands
  schemas/             # Validation schemas
  index.json           # Master engram index
  registries.json      # Team registry configuration (seeded at install)
```

## See also

[DOCS.md](DOCS.md) -- Comprehensive technical documentation covering architecture, data formats, extraction pipeline, MCP protocol, slash commands, and configuration reference.

[prism_commands.md](prism_commands.md) -- Comprehensive list of user commands, claude skills and MCP tools. 

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, the test command, and the project's architectural constraints. All participation is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Please report security vulnerabilities privately — see [SECURITY.md](SECURITY.md). Do not open public issues for security reports.

## License

Prism is licensed under the [Apache License 2.0](LICENSE). Copyright © 2025 MIH AI B.V.
