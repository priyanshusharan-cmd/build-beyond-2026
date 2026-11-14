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

## Phase 4 (Material 3 UI pass) — DONE, verified in browser
The 3D stage was REMOVED on request (too busy / too cinematic for the judging context).
Deleted: web/src/stage/**, web/src/store/runStore.js, web/public/hdri/.
Dropped deps: three, @react-three/fiber, @react-three/drei, @react-three/postprocessing,
postprocessing, gsap, zustand, framer-motion, @phosphor-icons/react. useRun.js no longer
mirrors into a store; App has two views (Live | Compare). Engine and API untouched.

- web/src/styles.css is now a Material Design 3 token system:
  * colour — a full M3 tonal scheme (--md-primary/secondary/tertiary/error + containers,
    surface + surface-container-lowest…highest, outline/outline-variant, inverse-*), light and
    dark. The dark block is written twice on purpose (media query + [data-theme="dark"]) since
    custom properties cannot be shared across a media boundary.
  * type — Roboto Flex (variable) + Roboto Mono for every number; M3 type scale sizes/tracking.
  * shape 4/8/12/16/28/full, elevation levels 0–5, M3 motion tokens (standard / emphasized /
    emphasized-decelerate easings, 100–500ms), state layers at 8%/10% on every pressable.
  * one creamy wash on body::before (primary/tertiary/secondary at 7–9% alpha); no per-panel gradients.
- Components mapped to M3 patterns: small top app bar, segmented buttons (views, speed, mobile tabs),
  filled/tonal/text/icon buttons, assist chip (run chip), filled cards, linear progress (meters),
  tonal badges (status), list items (chat), basic dialogs (run / chaos / method), M3 slider (timeline).
- Agent colours are now scheme-aligned and theme-aware: AGENT_META[a].hex (light) / .dark,
  resolved by agentHex(a, theme) for canvas/SVG; CSS uses --agent-* vars. CompareView is
  theme-aware too (PALETTE + CHART_THEME).
- Charts are live, not static: LiveLegend reads the value at the hovered/pinned minute for every
  series; EventPins overlays scripted shocks, live chaos and cascades along the top of each plot;
  the heatmap has a 0→100% ramp legend; areas use soft vertical gradient fills.
- Chaos countdown is a restrained M3 dialog (determinate circular progress), not a cinematic slam.
  NOTE: the digit's entrance animation must never start from opacity 0 — it is re-keyed every second
  and the first element can sit in the from-state for ~1s, which hid it. It now fades 0.4→1.
- Tiles: name row, big MW number, progress meter, note row with the status badge; the badge collapses
  to a status dot under a 470px container. KPI strip (damage / fairness / cascades / breaches) spans
  the full width with an ƒx button.
- NEW: web/src/components/Method.jsx — one dialog, "How these numbers are computed", opened from the
  KPI strip and from the Compare footer. States the per-agent damage functions and weights exactly as
  config/damage.yaml and agents/*.py implement them, the cascade multipliers, and Jain's index
  (sᵢ = mean over ticks of clip(served/need,0,1); J = (Σsᵢ)²/(n·Σsᵢ²), n = 4) with why it moves during a
  run and the honest caveat that Jain is priority-blind. Keep this file in sync if damage.yaml changes.
- Verified in the browser: light + dark, 1440x900 and 375x812, Live + Compare, method dialog, chaos
  countdown and impact. `npm run build` passes (bundle down to 118 kB app + 560 kB recharts).

## Phase 3 + Nice tier (Layer 2, credit, ablations, explanations, report) — DONE (engine), UI not yet wired
- Layer 2 (`sim._layer2`): after Layer 1 settles, agents bargain bilaterally up to `layer2.rounds` (3). Best
  (yielder, beneficiary, x MW) by net weighted-damage gain is OFFERed for T=5 min; beneficiary accepts, COUNTERs
  (halved x, only if `debt_penalizes`) or rejects. Transfers conserve power and respect caps; the result still goes
  through ledger propose -> validate -> commit; on fallback the tick's concessions are void and no credit is booked.
  Accepted concessions persist T ticks (replayed while still net-beneficial). Params in config/damage.yaml `layer2:`.
- Credit: yielder banks x*T/credit_scale, beneficiary owes it (CREDIT_UPDATE events), clamped to [debt_floor, credit_cap],
  decays 2%/tick. Positive credit raises bid weight (w_eff = w*(1+lambda*credit)). Debts are tracked/reported but do NOT
  lower bid weight (`debt_penalizes: false`): first version let debt starve the hospital and cost +60% damage (308 vs 191).
- Ablation strategies `ours_no_l2`, `ours_no_credit` (baselines.ABLATIONS; not in default /compare).
  `python scripts/run_benchmark.py --ablations`.
- EXPLANATION events: deterministic templates (chaos, concession, fallback, cascade, status change). No LLM, never
  read by agents.
- `python scripts/export_report.py` -> docs/RESULTS.md from results.json.
- Tests: 132 passing (9 new in tests/test_layer2.py). Fuzz 1000 runs, 0 violations, 0 fallbacks.

## Benchmark with Layer 2 (20 seeds, default_8h, damage = modeled proxy)
- ours 179.7±46.4, 0 viol, jain 0.991, 4.10 cascades
- ours_no_l2 190.9±70.6, jain 0.990, 2.65 cascades; ours_no_credit 178.8±47.7, jain 0.991, 4.20 cascades
- priority 194.0±58.6, jain 0.984, 3.45 cascades; proportional 787±153; blind 3368 with 414 violations
- HONEST: Layer 2 lowers damage ~6% vs no Layer 2 and ours beats static priority on 11/20 seeds (mean -14.4), still
  within one std: not a clean win. Layer 2 RAISES cascades (4.10 vs 2.65 without it; priority 3.45). Credit has
  no measurable effect on damage or Jain here (179.7 vs 178.8, 0.991 vs 0.991): present as a fairness mechanism
  that is cost-free, not as a proven improvement.

## UI wiring for Layer 2 — DONE, verified in browser
- useRun.js folds CONCESSION (non-replay) and COUNTER into `thread.deals`; story.js turns each into a chat line from the
  yielder (chips "Yields x MW", "+credit"; counter/reject lines). App.jsx tiles show `credit ±x` once |credit| >= 0.01.
- Fixed a pre-existing build break: Sheets.jsx still imported the removed `gsap`; now uses the Web Animations API.
- Gotcha: vite proxies /api -> 8010 (env API_PORT overrides). If a stale API holds 8010 the UI shows no deals.

## Next
- Add ablations to the Compare view (API /compare currently returns only the 4 default strategies).
- Investigate why Layer 2 raises cascades (likely it drains the water reservoir / telecom battery for a short-term gain).
