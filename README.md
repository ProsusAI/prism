# Prism

A knowledge layer for Claude Code. Prism watches how you work, learns your preferences, and makes Claude remember them across sessions. For teams, it lets you share proven architectural knowledge through a shared registry.

**One install. Zero config for personal use. Registry config for teams.**

## What it does

**Personal learning** -- Prism observes your Claude Code sessions through hooks. When it sees recurring patterns (you always prefer TypeScript strict mode, you correct a certain approach, you follow a specific deployment procedure), it extracts those into "engrams" -- living knowledge units that strengthen with evidence and decay without use.

**Team knowledge** -- Promote your best engrams into publishable skills, or run slash commands to mine your codebase and git history for architectural patterns. Publish them to a team registry so everyone benefits.

## Install

```bash
git clone <repo-url> && cd prism
./install.sh
```

Requirements: Python 3.12+, git, [Claude Code](https://claude.ai/code)

The installer creates `~/.prism/`, copies everything it needs, and symlinks the `prism` CLI to `~/.local/bin/prism`. Safe to re-run on upgrades.

## Quick start

```bash
# Initialize Prism in your project
cd your-project
prism init

# That's it. Prism is now:
# - Observing your Claude Code sessions via hooks
# - Available as an MCP server for mid-session queries
# - Syncing knowledge to .claude/prism.md for session context
```

## Teach it directly

```bash
# Teach a preference
prism learn "Always use pnpm, never npm"

# Correct something
prism correct <engram-id> "Use vitest not jest for this project"

# Remove something
prism forget <engram-id>
```

## See what it knows

```bash
# Current knowledge for this project
prism status

# Recent observations
prism log --last 20

# Run extraction from accumulated observations
prism extract

# Bootstrap from past Claude Code sessions
prism analyze-sessions --last 10
```

## Team skills

```bash
# Promote a well-validated engram to a publishable skill
prism promote <engram-id>

# Run analysis pipelines (slash commands in Claude Code)
/run-analysis-pipeline    # Full codebase analysis
/run-history-pipeline     # Git history to skills
/extract-skills           # Analysis reports to skills
/curate-skills            # Quality pass
/publish-skills           # Publish to team registry
/advise-skills            # Query registry for advice
/audit-code               # Audit code against known patterns
```

## How it works

Prism has two channels for getting knowledge into Claude Code:

**Push** -- `.claude/prism.md` is auto-generated with your highest-priority knowledge (corrections, pinned items, top preferences). Claude Code reads this at session start.

**Pull** -- An MCP server exposes `prism_search`, `prism_get`, `prism_relevant`, and `prism_record` tools. Claude queries these mid-session when it needs specific knowledge.

Knowledge has a lifecycle: engrams start at a base confidence, strengthen when the same pattern is observed again, and decay slowly without reinforcement. Run `prism maintain` periodically (or let it happen automatically) to keep things fresh.

## Configuration

```bash
prism config                        # Show all settings
prism config extract_threshold 20   # Change a setting
```

Key settings: `extract_threshold` (observations before auto-extraction), `decay_rate_per_week`, `max_context_lines` (prism.md size), `registry_url` (team registry).

Config lives at `~/.prism/config.json`.

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
