---
phase: 260506-g5q
plan: 01
subsystem: index
tags: [reinforcement, confidence, sync, parity, mcp]
requires: []
provides:
  - "reinforce_entries with confidence boost matching _reinforce_batch"
affects:
  - "lib/sync.py (caller — behavior change: prism.md push layer now also boosts confidence)"
tech_added: []
patterns:
  - "Push-layer reinforcement matches MCP-query reinforcement for symmetry"
  - "Confidence boost capped at 0.95, default 0.5 for missing field, rounded to 3 decimals"
key_files_created: []
key_files_modified:
  - lib/index.py
  - /Users/lara.baseggio/.prism/lib/index.py
decisions:
  - "Match _reinforce_batch exactly: boost=0.02, cap=0.95, default=0.5, round=3 — no new constants introduced"
  - "Mirror installed copy (~/.prism/lib/index.py) so deployed sessions pick up fix without re-install"
metrics:
  duration: "<1min"
  completed: "2026-05-06"
  tasks_completed: 2
  files_changed: 2
---

# Quick Task 260506-g5q: reinforce_entries Confidence Boost Parity Summary

**One-liner:** Brought `reinforce_entries` to parity with MCP `_reinforce_batch` so prism.md push-layer engrams accrue confidence at the same rate as MCP-queried engrams.

## Asymmetry Fixed

Before this change, two reinforcement paths had divergent behavior:

| Path | evidence_count | last_observed | confidence |
|------|---------------:|---------------|-----------:|
| `_reinforce_batch` (MCP query, `lib/mcp_server.py:215`) | (not touched) | refreshed | **+0.02 (cap 0.95)** |
| `reinforce_entries` (prism.md push, `lib/index.py:146`) | +1 | refreshed | **(unchanged)** |

Effect: every MCP query nudged confidence upward, but engrams selected for the prism.md push layer never received that nudge — even though both paths represent the engram being actively used. Over time, MCP-queried engrams floated up the rankings and displaced push-layer engrams from selection, even when the push-layer engrams were still being read into context. This patch closes that asymmetry.

## Diff Applied

`lib/index.py` `reinforce_entries`:

```diff
 def reinforce_entries(entry_ids: list[str]) -> int:
-    """Increment evidence_count and refresh last_observed for a set of entries.
+    """Increment evidence_count, refresh last_observed, and boost confidence for a set of entries.

     Loads the index once, updates all matching entries, saves once. Used by
-    sync to credit engrams that were selected for the prism.md push layer —
+    sync to credit engrams that were selected for the prism.md push layer --
     otherwise context-injected engrams decay even while actively in use.

+    Confidence is boosted by +0.02 (capped at 0.95), matching `_reinforce_batch`
+    in mcp_server.py so push-layer engrams stay at parity with MCP-queried ones.
+
     Returns the number of entries actually updated.
     """
     if not entry_ids:
         return 0
     id_set = set(entry_ids)
     today = date.today().isoformat()
     index = load_index()
     updated = 0
     for e in index["engrams"]:
         if e["id"] in id_set:
             e["evidence_count"] = e.get("evidence_count", 0) + 1
             e["last_observed"] = today
+            old_conf = e.get("confidence", 0.5)
+            # Cap at 0.95 -- mirrors _reinforce_batch in mcp_server.py so prism.md
+            # push layer accrues confidence at the same rate as MCP queries
+            e["confidence"] = round(min(0.95, old_conf + 0.02), 3)
             updated += 1
     if updated:
         save_index(index)
     return updated
```

Notes:
- Default for missing `confidence`: `0.5` (matches `_reinforce_batch`).
- Cap: `0.95` — only explicit `prism learn` gets `0.9` starting confidence; reinforcement should not push past `0.95`.
- Rounding: `round(..., 3)` — matches `build_index_entry` precision (`lib/index.py:191`).
- Signature, return value, single load/save cycle, evidence_count increment, last_observed refresh: all unchanged.

## Installed Copy Mirrored

`~/.prism/lib/index.py` is the runtime copy loaded by `capture.py`, `sync.py`, and `mcp_server.py`. Repo edits do not propagate until the file is copied (or `install.sh` is re-run). Per the plan's quick-task scope, the installed copy was mirrored:

```bash
cp /Users/lara.baseggio/Documents/prism/lib/index.py /Users/lara.baseggio/.prism/lib/index.py
```

Confirmed byte-identical via `diff` (exit 0, no output).

## Verification Output

**Task 1 — behavior verification:**

```text
OK: reinforce_entries confidence parity verified
```

The verification script seeded three engrams at confidences 0.50, 0.94, 0.95 and confirmed:
- `0.50 -> 0.52` (boost applies)
- `0.94 -> 0.95` (cap holds, would be 0.96)
- `0.95 -> 0.95` (cap holds, would be 0.97)
- `evidence_count` still increments (`1 -> 2`, `5 -> 6`)
- Function returns `3` (count of updated entries)

**Phase-level checks:**

| # | Check | Result |
|---|-------|--------|
| 1 | `grep "min(0.95, old_conf + 0.02)" lib/index.py` | Match at line 171 |
| 2 | `diff lib/index.py ~/.prism/lib/index.py` | No output (in sync) |
| 3 | Behavior verification (Task 1 script) | Pass |
| 4 | Caller (`lib/sync.py:39`) still resolves | `from .index import ... reinforce_entries`; signature unchanged |

## Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Boost confidence in `reinforce_entries` (repo source) | `18998aa` |
| 2 | Mirror to installed copy at `~/.prism/lib/index.py` | (out-of-tree, not committed) |

Task 2 modified only `~/.prism/lib/index.py`, which lives under the user's home directory and is outside the git repo. Verification (byte-identical via `diff` + `grep` confirms boost line) is the artifact for Task 2.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- FOUND: `lib/index.py` — `min(0.95, old_conf + 0.02)` present at line 171
- FOUND: `~/.prism/lib/index.py` — byte-identical to repo source
- FOUND: commit `18998aa` (`feat(260506-g5q-01): boost confidence in reinforce_entries`)
