# Changelog

All notable changes to **Prism** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet publish semantic version tags, so entries are grouped
by merge date and pull request. Only changes that affect how Prism is used —
new capabilities and significant fixes — are listed.

## [2026-06-22] — Confidence scoring (#12)

### Added
- Confidence scoring for observations and engrams, with reworked `prism.md`
  context-push logic.

### Changed
- Relaxed extraction/promotion gates so more useful patterns surface.
- Extraction and session review now run through IDE-native CLIs (`claude --print`
  for Claude Code, `agent -p` for Cursor) with automatic backend resolution.
- Open-source release: license, NOTICE, refreshed docs, and new banner.

### Fixed
- Cursor auto-extraction resolves the `claude` CLI from the hook PATH, and
  `prism disable` now works for the Cursor command.

## [2026-06-10] — Dashboard & retrieval analytics

### Added
- Local web dashboard (`prism dashboard`).
- `prism stats` — MCP retrieval analytics.

## [2026-06-03] — Cursor, registry & engram fixes (#9, #10, #11)

### Fixed
- Cursor observation capture, hook payload handling, path slugs, and the
  uninstall flow.
- `last_observed` engram field now updates correctly.
- Registry token resolution and compatibility with older Python versions.

## [2026-05-26] — SQLite storage + compression (#8)

### Added
- SQLite-backed observation storage (replacing flat-file JSONL) with
  lexicon-based compression.

### Changed
- Existing JSONL observations migrate to SQLite via a one-time script. After
  upgrading, run `python3 migrate_observations.py` (use `--dry-run` to preview);
  JSONL files are archived only after a successful import.

## [2026-05-18] — Cursor integration (#3–#7)

### Added
- Cursor IDE integration (hooks, MCP, rules).

## [2026-05-11] — GitLab registry integration (#2)

### Added
- GitLab registry backend support alongside GitHub, including a CI pipeline
  template.

## [2026-04-20] — Session analysis & lifecycle commands (#1)

### Added
- `analyze-sessions` query option with `--since`, `--last`, and `--list` flags.
- Lifecycle commands: `prism enable`, `prism disable`, `prism uninstall`, and
  `prism reset`.

## [2026-04-14] — Initial release

### Added
- Core Prism: hook-based observation capture, two-phase extraction pipeline
  (fast proposes, strong validates), and living/decaying engrams.
- MCP stdio server (`prism_search`, `prism_get`, `prism_relevant`,
  `prism_record`) with `[global]` / `[project]` scope tags.
- Multi-registry fetch/cache/merge and a registry creation wizard.
- Secret scrubbing and path-traversal guards on engram/MCP file reads.
