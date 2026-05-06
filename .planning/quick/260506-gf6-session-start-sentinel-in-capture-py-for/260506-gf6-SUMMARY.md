---
phase: 260506-gf6
plan: 01
subsystem: capture-hook
tags: [hook, sync, reinforcement, capture]
requires: ["lib/capture.py main()", "_spawn_background helper", "260506-g5q reinforcement boost"]
provides: ["per-project per-day session-start sync trigger", "_check_session_sync helper"]
affects: ["lib/capture.py", "~/.prism/lib/capture.py"]
tech_stack_added: []
patterns_added: ["filesystem sentinel with O_CREAT|O_EXCL atomic create"]
key_files_created: []
key_files_modified:
  - lib/capture.py
  - ~/.prism/lib/capture.py (deployed, byte-identical mirror)
decisions:
  - Sentinel path lives in /tmp (per-machine, auto-cleared on reboot, no permissions issues)
  - UTC date suffix matches existing observation timestamp convention (line 50)
  - Hot path is single os.path.exists() — no stat/open/read overhead on every PreToolUse
  - Cleanup of stale sentinels runs only on slow path (first call of the day)
  - Atomic O_CREAT|O_EXCL handles concurrent capture races (loser returns silently)
metrics:
  duration: ~10min
  completed_date: 2026-05-06
  tasks: 2
  files_modified: 1
---

# Quick Task 260506-gf6: Session-Start Sentinel in capture.py for Daily Sync

**One-liner:** Daily-gated background `prism sync` from `capture.py` via `/tmp` sentinel,
restoring +0.02 confidence-boost parity between push-layer and MCP-queried engrams.

## Sentinel Path Scheme

```
/tmp/prism_synced_{project_id}_{YYYYMMDD-UTC}
```

- `{project_id}`: 12-hex SHA256 prefix (or env-supplied) — namespaces per-project so
  multiple projects on the same machine each get their own sync.
- `{YYYYMMDD-UTC}`: `datetime.now(timezone.utc).strftime("%Y%m%d")` — matches existing
  `_build_observation` UTC convention (capture.py line 50).
- Lives in `/tmp` so it auto-clears on reboot and never pollutes `~/.prism/`.

## Why /tmp (vs PRISM_HOME)

| Consideration | /tmp (chosen) | PRISM_HOME |
|---|---|---|
| Per-machine | Yes (machine-local boundary) | Yes |
| Auto-cleared on reboot | Yes | No (would need cron/decay) |
| Permission risk | Low (1777 sticky-bit by default) | Depends on user setup |
| Pollutes prism state dir | No | Would mix runtime sentinels with persistent data |
| Performance | Equivalent (single `os.path.exists`) | Equivalent |

`/tmp` is the canonical location for ephemeral per-session state on POSIX. Reboots
naturally re-fire sync (which is the intended behavior — a fresh OS session is a
new "day" in user-experience terms).

## The Asymmetry Being Fixed

Before this fix, two engram retrieval pathways had diverging confidence trajectories:

| Path | Confidence flow | Reinforcement |
|---|---|---|
| **MCP query** (`prism_search`, `prism_relevant`) | Engram returned to LLM | `+0.02` per match (capped 0.95) — implemented in `mcp_server.py` reinforce_entries call |
| **Push layer** (engrams in `.claude/prism.md`) | Engram silently injected as project instructions | NO reinforcement — push-layer engrams quietly decayed across sessions |

Push-layer engrams are arguably MORE valuable (they're so high-confidence they merit
unconditional injection) but were the only ones missing reinforcement signal. Over
time, an engram used heavily via push (but never directly queried via MCP) would
decay below the prism.md threshold and drop out — even though it was actively
informing the agent every session.

`prism sync` calls `sync_claude_code` which now (post 260506-g5q) calls
`reinforce_entries` on the engrams it pushes. By firing `prism sync` at the start
of each day's first PreToolUse, push-layer engrams receive the same `+0.02` boost
once per session, restoring symmetry.

## Confirmation: +0.02 Parity Restored

- **MCP path**: Each search call → `reinforce_entries` → `+0.02` per matched engram.
- **Push path** (this fix): First PreToolUse per project per day → background
  `prism sync` → `sync_claude_code` → `reinforce_entries` → `+0.02` per pushed engram.

Both paths now boost confidence at granularity appropriate to their event rate
(per-search for MCP, per-session for push). Engrams used exclusively via push no
longer silently decay relative to MCP-queried engrams.

## Implementation Notes

- **No new imports**: `os`, `sys`, `datetime`, `timezone`, `Path` are already imported
  at module top. `subprocess` and `shutil` remain lazily imported in `_spawn_background`
  (reused, not duplicated). Stdlib-only constraint preserved.
- **Hot-path cost**: One `os.path.exists()` per PreToolUse after the first daily call.
  Measured at well under 1ms — within the capture.py performance budget.
- **Concurrency**: Two simultaneous PreToolUse hooks racing → first wins via
  `O_CREAT | O_EXCL`; loser swallows `FileExistsError` and returns silently. Only
  one sync is spawned. (Concurrent spawn duplicates would also be harmless — `prism
  sync` is idempotent — but we prevent them anyway.)
- **Robustness**: All exception paths are swallowed. `/tmp` unwritable, `os.listdir`
  failure, race losses, generic `Exception` at the outer level — none crash
  capture.py. The OBS-05 invariant (capture.py exit 0 always) is preserved.
- **Stale sentinel cleanup**: Runs only on the slow path (when today's sentinel is
  absent). Lists `/tmp` once, filters by project-prefix, unlinks any non-today
  matches. Cheap and self-healing — yesterday's sentinels are gone within seconds
  of the first PreToolUse on a new day.

## Wire-up

`main()` invokes `_check_session_sync(prism_home, project_id)` immediately before
`_check_triggers(...)`. The sync gate is therefore independent of observation count
— it fires on the very first hook of the day, even before extraction or review
thresholds are evaluated.

## Deployed Copy

`~/.prism/lib/capture.py` is byte-identical to the repo copy, verified via
`diff -q` (zero output, exit 0). Smoke test confirmed:

- Installed `capture.py pre` exits 0 on a synthetic Read-tool payload within 2s.
- Sentinel `/tmp/prism_synced_smoketest1234gf6_20260506` was created on first call.

## Deviations from Plan

**1. [Tooling adaptation] `timeout` command unavailable on macOS (no GNU coreutils)**
- **Found during:** Task 2 smoke test
- **Issue:** Plan's verify command uses `timeout 2 python3 ...` but macOS lacks the
  `timeout` binary (and Homebrew's `gtimeout` was not installed).
- **Fix:** Replaced with `python3 -c "subprocess.run(..., timeout=2)"` shim — same
  semantics (2-second hard timeout), no host-tooling dependency.
- **Files modified:** None (verification-time workaround only)
- **Commit:** N/A (test-runner adjustment, not code change)

No code-level deviations. Plan executed exactly as written.

## Verification

- Task 1 verify command: prints `OK: _check_session_sync sentinel gate works correctly`
- Task 2 verify command: prints `OK: installed copy identical, smoke test passed, sentinel created`
- Both pass.

## Self-Check: PASSED

- `lib/capture.py` exists in worktree and contains `_check_session_sync` (verified)
- `~/.prism/lib/capture.py` byte-identical to worktree copy (`diff -q` empty)
- Commit `2ebd3be` exists in `git log` (verified)
- `main()` calls `_check_session_sync` before `_check_triggers` (verified by inspection)
- Sentinel path scheme implemented as `/tmp/prism_synced_{project_id}_{YYYYMMDD-UTC}`
- All verification commands print expected `OK: ...` messages
