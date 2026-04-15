---
phase: 04-registry
session_id: uat-04-20260415
status: in_progress
started: 2026-04-15
tester: lara.baseggio
---

# Phase 4 UAT: Registry

Testing the registry management layer built in Phase 4. Validates `prism registry` CLI commands, registry template bundle, multi-registry reads/writes, and slash command updates.

**Phase Success Criteria:**
1. `prism registry create` guided wizard walks user through team registry setup
2. `prism registry add/remove/list/default` + `prism registry token create/revoke` all work
3. Multi-registry reads merge from all sources with 24h TTL cache, results tagged with `[registry-name]`
4. `/advise-skills` and `/audit-code` search all registries; `/publish-skills` tracks deltas per-registry

---

## Test Results

| # | Test | Status | Notes |
|---|------|--------|-------|
| T-01 | `prism registry add` creates registries.json entry | PASS | |
| T-02 | `prism registry list` shows registered entries with masked tokens | PASS | |
| T-03 | `prism registry default` sets write target | PASS | |
| T-04 | `prism registry remove` removes entry, auto-clears default | PASS | |
| T-05 | `prism registry token create` generates token + wrangler instructions | PASS | |
| T-06 | `prism registry token revoke` shows revocation instructions | PASS | |
| T-07 | `prism registry create` launches guided wizard | PASS (bug fixed) | `wrangler deploy` → `npm run deploy`, `wrangler secret put` → `npx wrangler secret put` |
| T-08 | Registry template bundle deploys and serves health + registry endpoints | PASS | Full Worker deployed to https://prism-registry.prism-flume.workers.dev |
| T-09 | `/advise-skills` handles empty registry correctly | PASS (bug fixed) | Empty registry now returns "no skills yet" instead of falling through to local sources; `REGISTRY_EMPTY` vs `NO_REGISTRIES` distinction added |
| T-10 | `/publish-skills` resolves target from registries.json | - | |

---

## Test Details

