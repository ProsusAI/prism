# Confidence & Context-Injection Protocol — Design Plan

Status: **v1 implemented** on branch `confidence-score` (token-cost-balanced subset — see §10)
Branch: `confidence-score`
Last updated: 2026-06-10

---

## 0. Final protocol (as built)

Constants (config.py): `ALPHA=0.15`, `CEIL=1.0`, `FLOOR=0.1`, `HALF_LIFE=28d` (4w),
`GRACE=3d`, `overlap_min_terms=2`, push-lane cap `=10`, start confidence: corrections/preferences
`=0.8`, other kinds `=0.9`.

**1 — Route by kind (placement is NOT by confidence).** `prism.md` is a *push subset*, not a
separate store — **MCP search spans the entire index (all 6 kinds)**.
- **prism.md push lane (a subset that is *also* in MCP):** `correction` + `preference`
  (+ anything manually pinned). They're pushed because of their *kind*, not their score. Capped
  at 10, priority **pinned → corrections → preferences**; confidence is only a tiebreak *within*
  a tier. A correction at 0.3 still outranks a preference at 0.9. (Not "top-10 by confidence.")
- **MCP pull (everything):** all kinds are retrievable on demand —
  `solution`/`domain_fact`/`error_recipe`/`procedure` live *only* here, while corrections and
  preferences live here *too*. So any correction/preference beyond the top-10 push cap is still
  reachable, and MCP-retrieving one fires the same daily impulse (`_reinforce_batch` credits
  whatever is returned, regardless of kind).

**2 — One impulse up (a *use-event*), daily-idempotent.** Same formula for both lanes; only the
trigger differs.
```
if last_used == today: return                  # N calls / N sessions = 1 impulse
confidence = confidence + ALPHA * (CEIL - confidence)   # NOT flat +0.02; no 0.95 wall
last_used  = today
```
- Background engram's use-event = **MCP retrieval** (once/day, not +0.02 per call).
- Push engram's use-event = **term overlap** between its `domain`/`tags`/`trigger` and this
  session's observations (≥ `overlap_min_terms` shared significant terms). Identical impulse.

**3 — One curve down (decay), from `last_used`.** Recomputed each run from `confidence_base` (the
value at last use), so it never compounds:
```
idle = today - last_used
if idle > GRACE:
    confidence = FLOOR + (confidence_base - FLOOR) * exp(-ln2/HALF_LIFE * (idle - GRACE))
```
Corrections/preferences decay too (for bookkeeping) but are **never auto-archived** — only
background kinds archive when they fall below `0.2`.

**4 — Initial award.** New corrections/preferences start at **0.8** (other kinds 0.9), but since
placement is by kind, that number only affects within-lane ordering and later promotion/publish —
never whether the engram appears in prism.md.

Equilibrium (free property of impulse-up + decay-down): an engram used every *D* days settles
near `ALPHA·(1−c*) ≈ (ln2/HALF_LIFE)·(c*−FLOOR)·D` — daily-used ≈ 0.997, weekly ≈ 0.637,
monthly ≈ 0.352.

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

1. **Placement never writes confidence** (no feedback loop) — `sync.py` must never write the
   score. Cache-lane placement is a *consequence* of the score; push-lane placement is a
   consequence of *kind* (see §5). Neither is ever an *input* to the score.
2. **One impulse up, one curve down — identical math for every engram.** Channels differ only in
   what *triggers* the impulse (retrieval vs detected application), never in the formula. No
   privileged channels.
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
- **MCP-retrieved engrams:** a retrieval *is* a use event — there is no matching to compute.
  The query already matched inside FTS to build the result set; reinforcement simply credits
  whatever was returned. `mcp_server.py` already knows the returned IDs. **Trigger = "returned
  by a query."**
- **Injected (`prism.md`) engrams:** there is no query — that's the defining property of push —
  so detection *cannot* overlap against a user query. It overlaps against *session activity*.
  Layer cheap → accurate:
  - Baseline (free, <100ms): FTS-match the engram's `trigger`/`tags`/`domain` against *this
    session's observations* — the recorded **tool activity** in `observations_fts`, i.e. what
    Claude actually *did*, not what the user typed. Overlap ⇒ the engram's domain was active ⇒
    fire `use_event`.
  - Upgrade (**marginal token cost, small build cost — not free**): extend the existing
    `review.py` Haiku call to also report which injected engrams were *applied*, upgrading
    "relevant" → "applied". The call already runs and is already handed the trigger list, but
    today it emits only *new* insights — this needs a `reviewer.md` prompt change, a new parse
    branch, and a `use_event` sink.
- Be honest: the overlap heuristic detects *relevance* ("the domain was active"), not
  *application* ("Claude followed it"). Use it as a pre-filter; confirm with the piggyback judge
  for high-value engrams.
- **Cadence caveat:** `run_review` is *not* session-end — `capture.py:197-208` auto-spawns it
  roughly **every 5 captures** (`review_interval`), throttled by a **30-min per-session cooldown**
  (`review_cooldown_seconds`) and a sentinel lock, over the last 50 observations. So the piggyback
  fires **multiple times per session**, which makes the daily-idempotent `last_used==today` guard
  load-bearing, not just a concurrency nicety: without it, repeated reviews in one session would
  fire the same `use_event` several times and re-inflate the very score this plan is trying to fix.

### Q4 — Pure-decay tournament (no `prism.md` boost; MCP risers replace decayers)

Rejected as a standalone design. Fatal flaw = **injection-starvation paradox:** once an engram
is in `prism.md` it's in context, so Claude stops querying it → it gets zero retrieval boost
*precisely because it's working* → decays → evicted → must be searched again → re-promoted →
stops being queried → decays. **Oscillation with period ≈ decay time, on your best engrams.**
Dampers (hysteresis, cooldown, asymmetric decay) reduce the flap but can't cure the root
blindness without a use-signal. Since Q3's use-signal is near-zero *token* cost (it rides a call
we already make), Q4 buys nothing on cost while adding thrash. Its *structure* (decay-driven rotation, no feedback loop) is kept in §5, paired
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
  conventions / preferences. **Placement is by *kind*, not by confidence** — pushed on creation,
  and they stay until a kind-level lifecycle event evicts them (correction resolved/obsolete, or a
  tenure cap). Confidence still decays in the background for bookkeeping, but **a low score never
  removes a push-lane engram from `prism.md`.** Value = present unprompted. The irreducible reason
  `prism.md` exists.
- **MCP (the bulk):** domain facts, procedures, solutions, reference. Relevance-gated,
  pay-per-use. The primary channel that writes confidence — every retrieval is one clean
  use-event (daily-idempotent for concurrency-safety).
- **Cache lane (optional, earned):** non-correction engrams proven hot by *real retrieval* get
  promoted into `prism.md` as a latency/reliability optimization. **This is the only lane that
  decays out of `prism.md` and recycles back via MCP** — and the only place the "fall to
  background → re-retrieved → re-promoted" cycle is safe, because the asymmetric promote/demote
  rules below prevent the Q4 oscillation that same cycle would cause for kind-pinned entries.

This collapses the confidence protocol to a single honest rule: **confidence moves only on real
use-events** — for the MCP bulk that's a *retrieval*; for an injected engram it's a *detected
application*. Both fire the identical impulse (below); they differ only in **trigger**, never in
the formula. Crucially, **push-lane placement is decoupled from confidence entirely** — so
corrections/preferences need no boost to stay placed, and the only place a use-signal drives
placement is the earned cache lane. This keeps the one thing push does that pull cannot, without
ever rewarding mere presence.

### Promotion / demotion (asymmetric signals to avoid thrash)

- **Promote** (cache lane) on retrieval *frequency*: retrieved on **≥N of the last M days**.
- **Demote** NOT on retrieval-drop (structurally zero after promotion) but on **domain-silence**
  (cheap observation-overlap heuristic) **or a tenure timeout**, with a **guaranteed minimum
  tenure** (e.g. 2 weeks) so nothing flaps.
- **Corrections bypass** the N-day wait — pushed on creation into the reserved lane.

### Unified confidence rule (for every use-tracked engram)

State per engram: `confidence ∈ [floor, 1.0)`, `last_used` (date), plus `last_reinforced` guard.

Reinforcement (only way up), idempotent once per UTC-day per engram:
```
on use_event(engram):           # fired by: MCP retrieval (returned by query)
                                #        OR detected application of an injected engram
                                #           (session-activity overlap, optionally LLM-confirmed)
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
| `mcp_server.py` | **Behavior change, not a no-op:** today `_reinforce_batch` fires *ungated* on every search/get/relevant call (`:319/332/347`). Add the `last_used==today` guard so parallel sessions can't inflate |
| `review.py` / `reviewer.md` | Add detection of which injected engrams were *applied*; emit IDs; fire `use_event`. Rides the existing Haiku call, but **not free**: needs a `reviewer.md` prompt change, a new parse branch (today it emits only new insights), and a `use_event` sink |
| `sync.py` (selection) | Kind-based routing: push lane placed by **kind, not confidence** (placement decoupled from score); cache lane = promoted hot engrams; demotion on silence + min-tenure |
| `sync.py:200` | **Drop the `confidence >= 0.8` gate on corrections** — kind-routing pushes them on creation, before they have any usage history |
| `extract.py` / classifier | Make `preference` an **actually-classified kind**. Today `sync.py:61` defines `preferences` as the residual ("everything selected that isn't correction/pinned/validated") — if push routes by kind, that catch-all silently swallows the MCP bulk |
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
  (marginal token cost + small build cost, ~85%). Recommendation: heuristic pre-filter + piggyback
  confirm. Note: if push-lane placement is kind-pinned (§5), the push lane needs *no* use-signal to
  stay placed — so this detection only has to be built for the **cache lane** (promote/demote
  lifecycle), which sharply narrows where the unbuilt, accuracy-limited work has to land.
- Cache lane: ship now, or start with "push corrections only, everything else MCP" and add
  promotion later once MCP query-rate is measured. Recommendation: measure first, then decide.
- Intra-day intensity: flat daily impulse (default) vs log-scaled credit.

---

## 10. v1 implementation (shipped on this branch)

Resolved the §9 open decisions for **most-effective × lowest token cost**:

- **Use-signal = free FTS overlap only.** The LLM piggyback (token cost, fires multiple
  times/session) is **dropped**; the `$0` in-process term-overlap in `review.py` is the
  injected-engram use-signal. MCP retrieval is the use-signal for the bulk. Both fire the
  identical daily-idempotent impulse.
- **Cache-lane auto-promotion: deferred** (measure MCP query-rate first, §6). v1 = kind-pinned
  push lane + MCP bulk.
- **Flat daily impulse** (no log-scaling).

Correctness upgrade over the §5 sketch: decay is recomputed each run from a stored
`confidence_base` (value at last use) — `confidence = decay(base, idle_days)` — so it is a true
pure function of timestamps and never compounds across maintenance runs.

| File | Shipped change |
|---|---|
| `lib/confidence.py` (new) | Pure `reinforce(c,α,ceil)` + `decay(base,idle,floor,hl,grace)`. No I/O. |
| `tests/test_confidence_sim.py` (new) | §8 harness. All 4 assertions pass; daily/weekly/monthly settle 0.997/0.637/0.352; abandoned engram rotates out ~day 112. |
| `index.py` | `reinforce_entries` → daily-idempotent impulse from decayed base, no 0.95 wall; `build_index_entry` + merge gain `last_used`, `confidence_base` (index-only). |
| `commands.py` | `cmd_maintain` decay = exponential from `confidence_base` over idle days; PUSH_KINDS never auto-archived. |
| `sync.py` | Deleted the circular `reinforce_entries` call; `_select_prompt_entries` routes by kind (pinned + corrections + preferences), correction `≥0.8` gate dropped. |
| `mcp_server.py` | Unchanged — `_reinforce_batch` inherits the daily guard automatically (multi-session inflation fixed for free). |
| `review.py` | `_credit_relevant_injected` — free term-overlap use-signal for injected engrams; no `reviewer.md`/LLM change. |
| `config.py` | `reinforce_alpha`, `confidence_ceiling`, `decay_half_life_weeks`, `decay_grace_days`, `decay_floor`, `overlap_min_terms`; `PUSH_KINDS = {correction, preference}`. |
| `capture.py` | Sync docstring no longer claims reinforcement parity (sync is read-only on confidence). |

`preference` is a first-class extractor kind (extractor emits
`preference|correction|solution|domain_fact|error_recipe|procedure`), so routing on
`kind == "preference"` is sound — no residual-catch-all risk.

**Not yet done (deferred by design):** cache-lane promotion/demotion machinery (§5 promote-on-≥N/M,
demote-on-silence + min-tenure), and the §6 MCP query-rate instrumentation that gates whether to
widen/narrow the channel split.
