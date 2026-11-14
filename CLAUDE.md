# Blackout Arena — Project Brief (read fully before coding)

Hackathon: Build Beyond '26 (BMSCE) · Team ScaredToCompile (Priyanshu Sharan – lead, Abdul Khadar D Jamadar)
Problem Statement: PS 1.1 — Autonomous Multi-Agent Negotiation for Crisis Resource Allocation
Time box: 24h hackathon, a large part is already gone. Favor a working end-to-end slice over polish.

## 1. What we are building
A decentralized multi-agent simulation where utilities (Hospital, Water, Telecom, Emergency) negotiate scarce, fluctuating disaster power over a simulated 8-hour disaster. A live web dashboard ("Blackout Arena") shows the negotiation and lets judges inject chaos. We beat three baselines on the SAME seeded disaster and report real, measured numbers.

PS checklist (design to tick every line):
1. One autonomous agent per utility, decentralized.
2. Real-time negotiation: bids, priorities, concessions.
3. Supply fluctuates.
4. Hard capacity limits never violated; no inconsistent states.
5. Balances priority vs fairness.
6. Minimizes total damage over the multi-hour scenario.

## 2. Core design (already approved — do not redesign)
**Agents decide; infrastructure only aggregates and validates.**
- Agent: owns private need, damage function, internal state (reservoir level, battery, etc.), credit balance. Methods: `bid(price, state) -> demand_mw`, `propose_concession(ctx) -> Offer|None`, `respond(offer) -> Accept|Counter|Reject`.
- **Market Clock**: sums demands, publishes a scarcity price. It NEVER allocates power.
- **Ledger**: propose -> validate -> commit (atomic). It makes no decisions. Only checks invariants and commits or rejects.
- **Fallback**: if negotiation does not settle within N rounds, or the ledger rejects, apply a deterministic always-feasible split (see 5). No deadlocks, no invalid states, ever.
- **LLM never touches decisions or math.** Optional later: after commit, generate a plain-English explanation event. Not in the Must tier.

### Two-layer negotiation (per tick)
- **Layer 1 – coarse price discovery**: price p starts at p0 (carry over from last tick). Each round every agent returns demand q_i(p) = largest q where its marginal damage reduction per MW >= p (credit-adjusted, see fairness). Update p <- p * (1 + eta * (D - S)/S) with damping; stop when |D - S| <= eps or after N rounds (N default 8).
- **Layer 2 – fine bilateral bargaining**: agents with low marginal damage (e.g. Water with a full reservoir) offer to yield x MW for T minutes to agents with high marginal damage; counterparty accepts / counters (credit rate) / rejects. Accepted concessions record credit to the yielder. Cap rounds (default 3).
- Then ledger propose -> validate -> commit. On failure -> fallback.

### Fairness (concession-debt)
- Yielding agent banks credit; credit raises its effective weight in later ticks: w_eff = w * (1 + lambda * credit), credit decays slowly. Debtor's credit goes negative (owes).
- Report Jain's index on normalized satisfaction s_i = served/need (time-averaged per agent): J = (sum s_i)^2 / (n * sum s_i^2).

### Damage model (modeled proxy — all params in `config/damage.yaml`, editable)
Per tick, per agent, deficit u = 1 - served/need in [0,1]:
- Hospital: sigmoid cliff; near-zero damage until ~25% deficit, then steep to max (ICU critical load). Highest weight.
- Water: reservoir buffer L (0..1). Deficit drains L; refills when served >= need. Damage ramps only when L < threshold. Low pressure (L < 0.2) triggers cascade A.
- Telecom: battery B drains while deficit > 0, near-zero damage until B empty, then sharp rise. Battery empty triggers cascade B.
- Emergency: ~linear in deficit; amplifier on total damage when its effectiveness drops.
- Cascade A: water pressure low -> hospital cooling load up (hospital need *= 1.2).
- Cascade B: telecom down -> emergency effectiveness down (emergency damage *= 1.5).
- Total damage = sum over ticks of weighted per-agent damage (+ cascade multipliers). Report as "modeled proxy".
Default scale: need MW — Hospital 38, Water 24, Telecom 14, Emergency 16 (sum 92). Nominal supply 100 MW, seeded fluctuation + chaos shocks (e.g. drops to 70).

## 3. Simulation
- Tick = 1 simulated minute, 480 ticks for 8 hours. Seeded RNG (`numpy.random.Generator(PCG64(seed))`); same seed + config => byte-identical event log.
- Supply model: baseline + seeded random walk + scheduled shocks from scenario YAML + live chaos (kill substation: -X MW for T min; ICU surge: hospital need +Y%; burst water main: reservoir drain rate up).
- Scenario files in `scenarios/*.yaml` (default: `scenarios/default_8h.yaml`).

## 4. Baselines (run on the same seed, same damage model, same independent checker)
1. **Blind grab**: each agent requests full need independently. If sum > supply, grid overload: proportional curtailment AND an "overload trip" event (supply -20% for 5 min => cascade). Count as invariant violation (capacity breach).
2. **Proportional**: served_i = need_i * min(1, S/D).
3. **Static priority**: fixed ranking Hospital > Emergency > Telecom > Water; satisfy in order.
Add ablations only if time allows: ours without Layer 2, ours without credit.

## 5. Safety invariants (checked by an independent `invariants.py`, also run on baselines)
- INV-1 sum(grants) <= available supply at every tick.
- INV-2 0 <= grant_i <= max_draw_i.
- INV-3 atomic commits: a commit applies to all agents or none; no partial state.
- INV-4 every commit passes ledger validation first.
- INV-5 fallback is always feasible. Fallback = deterministic water-filling by public weights with per-agent critical floors; if floors exceed supply, truncate in priority order. No randomness, no negotiation.
Target: 0 violations for our system over all fuzzed seeds. Do NOT claim a guarantee that the tests don't prove.

## 6. Metrics (computed per run, compared across strategies on the same seed)
total damage; invariant violations; Jain's index (normalized satisfaction); cascade count; per-agent served% over time. Multi-seed: mean ± std over >= 20 seeds. Never present invented numbers; the pitch deck currently has illustrative placeholders to replace with these.

## 7. Contracts (implement first; both halves build against them)
### Event (append-only JSONL, source of truth for UI + replay)
```
{ "seq": int, "tick": int, "t": "HH:MM", "type": str, "agent": str|null, "payload": {...} }
```
Types: SUPPLY_UPDATE, CHAOS_INJECTED, PRICE_BROADCAST, BID, OFFER, COUNTER, CONCESSION, CREDIT_UPDATE, PROPOSE, VALIDATED, REJECTED, COMMIT, FALLBACK, DAMAGE_TICK, CASCADE_TRIGGERED, TICK_SUMMARY, EXPLANATION(optional).
`TICK_SUMMARY.payload`: supply, grants{agent: mw}, served_pct{agent}, damage_tick, damage_cum, reservoir, battery, price, rounds_used, used_fallback.
### State snapshot for the UI (per tick)
`{tick, supply, grants, need, served_pct, damage_cum, jain, cascades, credits, status{agent: ok|degraded|down}}`
### HTTP / WS API (FastAPI)
- `GET /scenarios`
- `POST /runs` {scenario, seed, strategy: ours|blind|proportional|priority} -> {run_id}
- `GET /runs/{id}/events?from=seq` (replay / scrubber)
- `WS /runs/{id}/stream` (live events, pace configurable)
- `POST /runs/{id}/chaos` {kind: kill_substation|icu_surge|burst_main, params}
- `GET /compare?scenario=&seed=` -> metrics for all strategies on the same seed
- `GET /health`
- Additive (Phase 2): `GET /runs/{id}` (info + snapshot + metrics when done), `POST /runs/{id}/control` {speed?, paused?}. WS frames: `{events, snapshot, done, metrics?}`.

## 8. Repo layout
```
blackout-arena/
  CLAUDE.md                 # this file
  config/damage.yaml
  scenarios/default_8h.yaml
  engine/blackout_arena/    # models.py events.py agents/ market.py ledger.py invariants.py
                            # sim.py baselines.py metrics.py fairness.py config.py
  api/                      # FastAPI app, WS streaming, run registry
  web/                      # Vite + React + React Flow + Recharts
  tests/                    # pytest + hypothesis
  scripts/run_benchmark.py  # multi-seed comparison -> results.json + CSV
```
Stack: Python 3.11, pydantic v2, numpy, FastAPI, uvicorn, pytest, hypothesis; React + Vite + React Flow + Recharts.

## 9. Build order (cut from the bottom if time runs out)
1. **Must** — models/events/config, agents + damage fns, Market Clock, Layer 1, ledger + invariants + fallback, sim loop, event log, blind + proportional + priority baselines, metrics, benchmark script.
2. **Must** — FastAPI run/stream/compare endpoints; UI: city grid graph, negotiation ticker, supply gauge + damage meter, scoreboard.
3. **Should** — Layer 2 concessions + credit/fairness, chaos panel, time scrubber, multi-seed results.
4. **Nice** — ablations, plain-English explanations, extra agents, export report.
5. **Out of scope** — RL-trained agents, 3D city, user accounts.

## 10. Acceptance tests (gate before calling a feature done)
- Determinism: same seed + config => identical event log.
- Fuzz (hypothesis, >= 1000 random seeds/shocks): our strategy has 0 invariant violations; fallback always feasible.
- Ledger rejects an over-capacity proposal and a partial commit.
- Blind baseline produces at least one capacity breach on the default scenario.
- Benchmark prints damage / violations / Jain / cascades for all strategies, same seed. If a baseline beats us on any metric, REPORT IT HONESTLY (we claim damage + fairness trade-off, not a clean sweep).
- No LLM call anywhere in the decision path.

## 11. Working rules
- Contracts in section 7 are frozen unless the user approves a change. If you change one, update this file.
- Keep the engine pure and deterministic (no wall-clock, no global RNG). Streaming pace lives only in the API layer.
- Write the test with the feature. Run `pytest` before reporting done.
- Small commits. Git author is Arsh (Arsh1255, arshdjamadar7777@gmail.com) with a `Co-authored-by: priyanshusharan-cmd <priyanshu0sharan@gmail.com>` trailer. NO Claude co-author trailers, NO "Generated by Claude" text in commits or PRs. All git commits/pushes are run from the user's own terminal, never from Claude's tools.
- Keep a short `docs/STATUS.md` (done / in progress / next) updated as you go so a fresh session can resume cheaply.
