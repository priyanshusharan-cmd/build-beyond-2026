# Blackout Arena

Autonomous multi-agent negotiation for crisis power allocation (Build Beyond '26, PS 1.1).
Four utility agents (Hospital, Water, Telecom, Emergency) negotiate scarce, fluctuating power over a simulated
8-hour disaster. A live dashboard shows the negotiation, lets you inject chaos, and compares our strategy
against three baselines on the same seeded disaster.

Team ScaredToCompile: Priyanshu Sharan (lead), Abdul Khadar D Jamadar.

## Branches

- `main` is the default branch. It carries the Material 3 dashboard and the Layer 2 negotiation
  (bilateral concessions, credit, ablations).
- `main-old` is the previous stable version (the earlier dashboard, before Layer 2). Kept for reference:
  `git checkout main-old`.

## How the negotiation works

1. **Layer 1, price discovery.** A market clock publishes a scarcity price. Each agent bids the power it still
   wants at that price; the clock never allocates power.
2. **Layer 2, bilateral bargaining.** Agents with low marginal damage (for example Water with a full reservoir)
   offer to yield MW for 5 minutes to agents with high marginal damage. The counterparty accepts, counters or
   rejects. Yielders bank credit, which raises their bid weight later; debts are tracked but never starve an agent.
3. **Ledger.** Every allocation is proposed, validated against the safety invariants and committed atomically.
   If negotiation does not settle or the ledger rejects it, a deterministic fallback split is applied.

Each tick also emits plain-English `EXPLANATION` events built from fixed templates (no LLM).

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer (for the dashboard)

## Setup

```bash
git clone https://github.com/priyanshusharan-cmd/build-beyond-2026.git
cd build-beyond-2026
```

Python dependencies (a virtual environment is recommended):

```bash
python -m venv .venv
```

```bash
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

```bash
pip install pydantic numpy pyyaml fastapi "uvicorn[standard]" httpx pytest hypothesis
```

Dashboard dependencies:

```bash
npm --prefix web install
```

## Run the dashboard

Use two terminals from the repo root.

1. Start the API (port 8010):

```bash
python -m uvicorn api.app:app --port 8010
```

2. Start the web app (port 5173, proxies `/api` to the API):

```bash
npm --prefix web run dev
```

Open http://localhost:5173. A run of our negotiation strategy on seed 0 starts automatically.

If port 8010 is taken, run the API on another port and tell Vite: `API_PORT=8011 npm --prefix web run dev`
(PowerShell: `$env:API_PORT=8011; npm --prefix web run dev`).

### Using the dashboard

- **Top bar:** Live / Compare views, strategy and seed (click to start a new run), clock, pause,
  speed (1×, 4×, 16×, 60×), light/dark toggle, and **Chaos**.
- **Left pane:** agent status tiles and four synced charts: power split, need met (heatmap),
  damage per minute, buffers and price. Hover for a detailed tooltip; click to pin a minute.
- **Right pane:** the negotiation chat. Agents speak only when something changes; quiet minutes collapse.
  Layer 2 deals show as messages from the yielding agent; the tiles show each agent's credit.
  Hover or click a message to move the chart cursor to that minute.
- **Bottom:** timeline scrubber. Red bands are scripted shocks, orange ticks are chaos you injected.
- **Chaos:** knock out a substation, trigger an ICU surge, or burst a water main during a live run.
- **Compare:** all four strategies on the same seed: damage over time, safety breaches, fairness, cascades.
  If a baseline wins a metric, it is marked best.

## Run the tests

```bash
python -m pytest -q
```

This covers determinism (same seed gives an identical event log), ledger validation, the safety invariants,
baselines, metrics, property-based fuzzing with hypothesis, and the API (stream, chaos, replay, compare).

## Command-line tools

Run one strategy on one seed and print a readable timeline (writes the JSONL event log to `results/`):

```bash
python scripts/run_one.py --strategy ours --seed 0
```

Strategies: `ours`, `blind`, `proportional`, `priority`, plus the ablations `ours_no_l2` (no Layer 2) and
`ours_no_credit` (no credit).

Multi-seed benchmark (mean ± std for every strategy; writes `results.json` and CSV to `results/`):

```bash
python scripts/run_benchmark.py --seeds 20
```

Add `--ablations` to include the two ablations, then export a Markdown report to `docs/RESULTS.md`:

```bash
python scripts/run_benchmark.py --seeds 20 --ablations
python scripts/export_report.py
```

Every number in the report comes from the benchmark output. Where a baseline matches or beats our system,
the report shows it as is.

Fuzz our strategy with random supply walks and shocks (expects 0 invariant violations):

```bash
python scripts/fuzz.py --runs 1000
```

## Repo layout

```
config/damage.yaml          damage model parameters (modeled proxy, editable)
scenarios/default_8h.yaml   default 8-hour disaster scenario
engine/blackout_arena/      agents, market clock, ledger, invariants, simulation, baselines, metrics
api/                        FastAPI app: runs, WebSocket stream, chaos, compare
web/                        React + Vite dashboard
tests/                      pytest + hypothesis
scripts/                    run_one, run_benchmark, export_report, fuzz
docs/STATUS.md              what is done / in progress / next
docs/RESULTS.md             latest benchmark report (generated)
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Health check |
| GET | `/scenarios` | Available scenarios |
| POST | `/runs` | Start a run `{scenario, seed, strategy, speed}` → `{run_id, ...}` |
| GET | `/runs/{id}` | Run info, snapshot, metrics when done |
| GET | `/runs/{id}/events?from=seq` | Replay events |
| WS | `/runs/{id}/stream` | Live events `{events, snapshot, done, metrics?}` |
| POST | `/runs/{id}/chaos` | `{kind: kill_substation \| icu_surge \| burst_main, params}` |
| POST | `/runs/{id}/control` | `{speed?, paused?}` |
| GET | `/compare?seed=` | Metrics for all strategies on the same seed |

Damage figures are a modeled proxy, not real-world casualties. No LLM is used anywhere in the decision path.
