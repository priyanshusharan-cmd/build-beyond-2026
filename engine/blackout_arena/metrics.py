"""Per-run metrics and same-seed multi-strategy comparison. Damage is a modeled proxy."""
from __future__ import annotations

import statistics

from .baselines import ABLATIONS, STRATEGIES
from .config import Scenario
from .fairness import jain_from_runs
from .models import AGENTS
from .sim import RunResult, run_simulation


def compute_metrics(run: RunResult) -> dict:
    served = {a: [r.grants[a] for r in run.records] for a in AGENTS}
    need = {a: [r.need[a] for r in run.records] for a in AGENTS}
    served_pct_avg = {a: sum(r.served_pct[a] for r in run.records) / max(1, len(run.records)) for a in AGENTS}
    return {
        "strategy": run.strategy,
        "seed": run.seed,
        "total_damage": run.records[-1].damage_cum if run.records else 0.0,
        "violations": len(run.violations),
        "jain": jain_from_runs(served, need),
        "cascades": run.cascade_count,
        "fallback_ticks": run.fallback_ticks,
        "served_pct_avg": served_pct_avg,
    }


def compare(scenario: Scenario, params: dict, seed: int) -> dict[str, dict]:
    return {s: compute_metrics(run_simulation(scenario, params, seed, s)) for s in STRATEGIES}


def compare_with_ablations(scenario: Scenario, params: dict, seed: int) -> dict[str, dict]:
    """All strategies plus our two ablations (no Layer 2, no credit) on the same seed."""
    return {s: compute_metrics(run_simulation(scenario, params, seed, s)) for s in STRATEGIES + ABLATIONS}


def aggregate(per_seed: list[dict[str, dict]]) -> dict[str, dict]:
    """mean +- std over seeds for each strategy and scalar metric."""
    out: dict[str, dict] = {}
    for s in [k for k in per_seed[0] if k in STRATEGIES + ABLATIONS]:
        rows = [m[s] for m in per_seed]
        out[s] = {}
        for k in ("total_damage", "violations", "jain", "cascades", "fallback_ticks"):
            vals = [r[k] for r in rows]
            out[s][k] = {
                "mean": statistics.fmean(vals),
                "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
            }
    return out
