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

## Next
1. Phase 2: FastAPI (runs/stream/compare/chaos) + React UI
2. Phase 3: Layer 2 concessions + credit, chaos panel, scrubber
3. Nice: ablations, explanations
