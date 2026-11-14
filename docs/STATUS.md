# STATUS

## Phase 1 (engine) — DONE and verified
- Contracts/config: models.py, events.py, config.py, config/damage.yaml, scenarios/default_8h.yaml
- Agents + damage fns (agents/), Market Clock (market.py), fairness.py
- Ledger + invariants + fallback (ledger.py, invariants.py)
- Sim loop (sim.py), baselines.py, metrics.py
- scripts: run_benchmark.py, run_one.py, fuzz.py
- pytest: 118 passing. Fuzz: 1000 random runs, 0 violations (scripts/fuzz.py).
- Determinism: same seed => byte-identical event log (tested).

## Design notes (deviations/additions, none touch frozen Section 7 contracts)
- Bidding uses `valuation()` (look-ahead `foresight_ticks`, default 15, for water reservoir / telecom
  battery). Scoring damage is unchanged and identical for every strategy.
- Layer 1 settles via price clearing: after the 8 coarse rounds, bisection finds the lowest price where
  total bids fit supply (counted in rounds_used, logged as PRICE_BROADCAST phase=clearing). Agents
  indifferent at the clearing price take the residual in public priority order, bounded by their own bids.
- Fallback never fired in 1000 fuzz runs, only in unit tests (fallback_split property-tested).
- Layer 2 / credits NOT built yet (credits stay 0).

## Benchmark, 20 seeds, default_8h (damage = modeled proxy)
- ours 190.9±70.6, 0 violations, jain 0.990, 2.65 cascades
- priority 194.0±58.6, 0 violations, jain 0.984, 3.45 cascades
- proportional 787±153, 0 viol, jain 1.000, 2.8 cascades
- blind 3368±281, 414 violations, 416 cascades
- HONEST: ours vs static priority on damage is a statistical tie (not a win). Ours wins on Jain/cascades
  vs priority; proportional has higher Jain (1.000). Claim: matches best baseline on damage with fairer
  split and zero violations, far better than blind/proportional.

## Phase 2 (API + UI) — DONE, verified in browser
- api/app.py: /health, /scenarios, POST /runs, GET /runs/{id}, GET /runs/{id}/events?from=, WS /runs/{id}/stream,
  POST /runs/{id}/chaos, POST /runs/{id}/control {speed,paused} (additive), GET /compare (cached per seed).
  WS message envelope: {events:[...], snapshot, done, metrics?}. Pace lives only in the API driver task.
- tests/test_api.py (4): stream to completion w/ live chaos, 0 violations, events replay, compare.
- web/ UI v3 (flat light workspace, 8px grid, type 12/14/16/20/28, size-specific tracking). Full-screen,
  page never scrolls: app bar (views Live|Compare, run chip, clock, pause, speed 1x default, Chaos) +
  two panes (data 58% / chat 42%) + timeline scrubber with shock bands and chaos markers.
  Data pane: agent tiles + KPIs, 4 synced charts (power split stacked + supply, need-met heatmap, damage
  per minute, buffers + price) with one detailed tooltip, shared cursor, shock/chaos bands.
  Chat (src/story.js, pure): continuous log, speaks only on change (chaos, cascade, status, grant > 2 MW with
  10-min cooldown, buffer crossing 50/25/10%, price jump, fallback); quiet minutes collapse; summary-only
  at >= 16x; SVG avatars (components/Avatars.jsx); chips urgent/wait/yield/shock/degraded; follows only at
  bottom, else "N new messages" pill. Chart/heatmap/timeline click pins a minute and scrolls chat; chat
  hover/click moves the chart cursor. Phone: Data/Chat tabs. Patterns view merged into the live data pane.
  Themes: light + dark (tokens in styles.css; follows OS, app-bar toggle persists in localStorage; useTheme.js
  also feeds chart colours). Soft look: gradient washes, translucent app bar/timeline, 20px radii, more spacing.
  Illustrations (components/Illustrations.jsx): skyline hero whose lit windows track need met; empty-chat art.
- /compare now also returns `series` (every 5th minute damage_cum, served_avg, supply) per strategy.
- Run: `python -m uvicorn api.app:app --port 8010` and `npm --prefix web run dev` (Vite proxies /api -> 8010).
  Needs `pip install websockets` (uvicorn[standard]) for WS.

## Next
1. Phase 3: Layer 2 concessions + credit, chaos panel, scrubber
3. Nice: ablations, explanations
