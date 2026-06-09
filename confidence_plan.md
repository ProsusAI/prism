# Confidence & Context-Injection Protocol — Design Plan

Status: **proposal / design** (not yet implemented)
Branch: `confidence-score`
Last updated: 2026-06-09

---

## 1. Problem statement

Today's confidence mechanics make `prism.md` go stale:

- **Rich-get-richer loop** — `sync.py:54` calls `reinforce_entries()` on the engrams it just
  selected for `prism.md`. Placement *causes* the score that *caused* the placement. Circular.
  Fired once/UTC-day per project via `capture.py:268-324`.
- **Hard-ceiling compression** — `index.py:243` does `min(0.95, c + 0.02)`. Everything
  load-bearing piles at exactly 0.95, so confidence stops discriminating and a fresher engram
  can't displace a stale incumbent (they tie at the wall; incumbent wins).
- **Injection ≠ use** — an engram in `prism.md` is *injected* into context, never *queried*,
  so we never observe whether Claude actually applied it. The daily boost rewards mere presence.
  `last_observed` is also refreshed blindly, so `cmd_maintain` decay never touches it.
- **Multi-session inflation** — MCP reinforcement is `+0.02` *per call*, unbounded. N parallel
  sessions querying the same engram = `+0.02·N`/day. The "up" path is an event accumulator,
  which is inherently unsafe under concurrency.

Root cause: **confidence is boosted for being *placed* in `prism.md`, not for being *used*.**

---

## 2. Design principles

1. **Placement is a consequence of the score, never an input to it.** `sync.py` must never
   write confidence.
2. **One way up, one way down — identical for every engram.** No privileged channels.
3. **Confidence is a function of usage *timestamps*, not an event accumulator.** Timestamp-derived
   state is order-independent and concurrency-safe by construction.
4. **Only *real use* moves the score.** Injection alone is not use.
5. **Route by what each channel can structurally do** (see §5), not by a single confidence rank.

---

## 3. Resolved design questions

### Q1 — Cost of detecting *used* vs *injected* engrams

| Approach | Tokens/session | Latency | Cost (order of) | Signal |
|---|---|---|---|---|
| Standalone LLM judge | ~5–7K in / ~150 out | 3–10s (background) | ~$0.005–0.01 | "applied" ~85% |
| **Piggyback on `review.py`** | **+~500 marginal** | $0 extra (call already runs) | **~$0.0005** | ~85% |
| Pure heuristic (SQL/FTS overlap) | 0 | <100ms | **$0** | "relevant" ~70–80% |

Key fact: `review.py:46` **already** fires a per-session Haiku call and is already passed
"Existing Knowledge Triggers." Detection rides on a call we already make → token cost is a
non-issue. The real axis is accuracy: the heuristic detects *relevance to the session's domain*;
the LLM piggyback upgrades that to *actually applied*. Latency is irrelevant because detection
runs in the background (hard constraint: hooks never block the IDE).

### Q2 — 1×/day vs 10×/day getting the same boost

Decision: **keep daily-idempotent reinforcement as the default.**

- **Pros:** inflation-proof under concurrency (N sessions = 1 impulse); measures *persistence*
  ("used on 22 of last 30 days") not bursts; ungameable.
- **Cons:** loses intra-day intensity; slower to recognize a genuinely hot engram.
- **Optional mitigation** if simulation shows engrams climb too slowly: log-scaled intra-day
  credit `impulse = ALPHA·(1−c)·(1 + k·log(1+uses_today))` with a hard cap (~×1.5). Ship the
  flat version first.

### Q3 — Timestamp must advance only for *retrieved + used* engrams

- **Delete the blanket `last_observed` refresh.** The daily sync currently refreshes it for every
  injected engram regardless of use — this is why decay never reaches stale `prism.md` entries.
- **MCP-retrieved engrams:** a retrieval *is* a use event. Exact and free; `mcp_server.py` already
  knows the returned IDs.
- **Injected (`prism.md`) engrams:** need detection. Layer cheap → accurate:
  - Baseline (free, <100ms): FTS-match the engram's `trigger`/`tags`/`domain` against *this
    session's* observations in `observations_fts`. Overlap ⇒ fire `use_event`.
  - Upgrade (~free): piggyback on the `review.py` Haiku call to upgrade "relevant" → "applied".
- Be honest: the heuristic detects relevance, not application. Use it as a pre-filter; confirm
  with the piggyback judge for high-value engrams.

### Q4 — Pure-decay tournament (no `prism.md` boost; MCP risers replace decayers)

Rejected as a standalone design. Fatal flaw = **injection-starvation paradox:** once an engram
is in `prism.md` it's in context, so Claude stops querying it → it gets zero retrieval boost
*precisely because it's working* → decays → evicted → must be searched again → re-promoted →
stops being queried → decays. **Oscillation with period ≈ decay time, on your best engrams.**
Dampers (hysteresis, cooldown, asymmetric decay) reduce the flap but can't cure the root
blindness without a use-signal. Since Q3's use-signal is ~$0, Q4 buys nothing on cost while
adding thrash. Its *structure* (decay-driven rotation, no feedback loop) is kept in §5, paired
with the cheap signal it lacks.

---

## 4. What `prism.md` (push) is actually for

The irreducible gain of the push channel: **unprompted delivery of knowledge Claude doesn't know
to ask for.** MCP is *pull* — it only fires if Claude decides to search and writes a good query.
That fails for the highest-value category — **corrections, anti-patterns, "don't do X," project
conventions** — whose value exists *only* if present *before* Claude acts. You cannot pull what
you don't know to look for. (`sync.py` already force-pushes corrections with the comment "Claude
can't search for past mistakes" — that line is the entire justification for push.)

Pure-MCP would *eliminate* the staleness/detection problem entirely (every retrieval is a clean
use-event) but is **strictly weaker** on mistake-prevention and makes hit-rate hostage to the
model's query discipline (models empirically under-query). So: keep push, but narrow it to what
only push can do.

---

## 5. Recommended architecture — route by kind, with a measured cache lane

Stop treating `prism.md` as a confidence-ranked top-10. Split channels by structural capability:

- **Push lane (small, reserved):** corrections / anti-patterns / safety / hard project
  conventions. **Pushed on creation.** Value = present unprompted. The irreducible reason
  `prism.md` exists.
- **MCP (the bulk):** domain facts, procedures, solutions, reference. Relevance-gated,
  pay-per-use. **The only channel that writes confidence** — every retrieval is one clean
  use-event (daily-idempotent for concurrency-safety).
- **Cache lane (optional, earned):** non-correction engrams proven hot by *real retrieval*
  get promoted into `prism.md` as a latency/reliability optimization.

This collapses the confidence protocol to a single honest rule: **MCP retrieval is the sole
confidence input** — exact, free, concurrency-proof — while keeping the one thing push does that
pull cannot.

### Promotion / demotion (asymmetric signals to avoid thrash)

- **Promote** (cache lane) on retrieval *frequency*: retrieved on **≥N of the last M days**.
- **Demote** NOT on retrieval-drop (structurally zero after promotion) but on **domain-silence**
  (cheap observation-overlap heuristic) **or a tenure timeout**, with a **guaranteed minimum
  tenure** (e.g. 2 weeks) so nothing flaps.
- **Corrections bypass** the N-day wait — pushed on creation into the reserved lane.

### Unified confidence rule (for the MCP-tracked bulk)

State per engram: `confidence ∈ [floor, 1.0)`, `last_used` (date), plus `last_reinforced` guard.

Reinforcement (only way up), idempotent once per UTC-day per engram:
```
on use_event(engram):           # MCP retrieval; or detected application of an injected engram
    if last_used == today: return            # kills multi-session inflation
    c = c + ALPHA * (CEIL - c)               # diminishing returns, replaces hard 0.95 wall
    last_used = today
```

Decay (only way down), computed from `last_used` (idempotent — pure function of timestamps):
```
once/day (maintain, gated by last_maintained):
    idle_days = today - last_used
    if idle_days > GRACE:
        c = FLOOR + (c - FLOOR) * exp(-LAMBDA * idle_days)   # tune via half-life: LAMBDA = ln2 / half_life
```

Property worth noting: with impulse-up + exponential-down, an engram used every *D* days settles
at an equilibrium where `ALPHA·(1−c*) ≈ LAMBDA·(c*−FLOOR)·D`. **Equilibrium confidence encodes
usage frequency for free** — daily-used engrams settle near the top, monthly-used drift toward the
floor. This is the discrimination the flat-0.95 system destroyed.

---

## 6. Measure first (load-bearing prerequisite)

The whole direction leans harder on MCP, so quality is gated by **how often the model actually
queries MCP at the right moments.** Before redesigning the channel split:

- Instrument MCP query rate per session and whether queries precede the relevant work.
- If reliable → lean into MCP-primary confidently.
- If the model under-fires → keep the push lane broader, not narrower.

Do not commit the channel split until this number is observed.

---

## 7. Implementation map

| File | Change |
|---|---|
| `sync.py:54` | **Delete** `reinforce_entries()` call — selection becomes read-only |
| `capture.py:268-324` | Sync still regenerates `prism.md`, but carries no reinforcement purpose; stop blind `last_observed` refresh |
| `index.py:243` | Replace `min(0.95, c+0.02)` with `c + ALPHA*(1-c)`; add `last_used==today` idempotency guard; add `last_used` field to `build_index_entry` |
| `commands.py:806` | Replace linear decay with `FLOOR + (c-FLOOR)*exp(-LAMBDA*idle_days)`, gated by `GRACE`; compute from `last_used` |
| `mcp_server.py` | Keep firing `reinforce` on retrieval — now daily-gated, so parallel sessions can't inflate |
| `review.py` / `reviewer.md` | Add detection of which injected engrams were *applied*; emit IDs; fire `use_event`. Piggybacks on the existing Haiku call |
| `sync.py` (selection) | Implement kind-based routing: corrections force-pushed; cache lane = promoted hot engrams; demotion on silence + min-tenure |
| `config.py` | New tunables (below) + new engram field `last_used` |

### New config defaults (to tune via simulation)

```
reinforce_alpha        ≈ 0.15      # impulse fraction of remaining headroom
confidence_ceiling     = 1.0       # (or 0.99) — no hard wall at 0.95
decay_half_life_weeks  ≈ 4         # LAMBDA = ln2 / half_life
decay_grace_days       ≈ 3
reinforce_window       = daily     # once/UTC-day per engram
promote_days_N         = 3         # retrieved on ≥N of last M days → cache lane
promote_window_M       = 7
demote_min_tenure_days ≈ 14
```

---

## 8. Validate before touching live mechanics

Build a **simulation harness** first: synthetic 60-day, multi-session usage traces (parallel
sessions, bursty days, abandoned engrams, steadily-hot engrams). Assertions:

- The push/cache set **rotates** — stale engrams leave, freshly-hot ones enter.
- No confidence inflation under N parallel sessions/day.
- Equilibrium confidence tracks usage frequency (daily > weekly > monthly).
- No promote/demote flap for a steadily-hot engram (min-tenure holds).

Tune `ALPHA` / half-life / `N,M` / min-tenure against these before any GSD implementation.

---

## 9. Open decisions

- Use-signal for injected engrams: heuristic-only (free, ~75%) vs heuristic + piggyback judge
  (~free, ~85%). Recommendation: heuristic pre-filter + piggyback confirm.
- Cache lane: ship now, or start with "push corrections only, everything else MCP" and add
  promotion later once MCP query-rate is measured. Recommendation: measure first, then decide.
- Intra-day intensity: flat daily impulse (default) vs log-scaled credit.
