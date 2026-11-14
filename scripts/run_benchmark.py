"""Multi-seed benchmark: all strategies on identical seeded disasters.

Usage: python scripts/run_benchmark.py [--seeds 20] [--out results]
Writes results/results.json and results/results.csv. All numbers are measured (modeled proxy).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from blackout_arena.baselines import ABLATIONS, STRATEGIES  # noqa: E402
from blackout_arena.config import load_damage_params, load_scenario  # noqa: E402
from blackout_arena.metrics import aggregate, compare, compare_with_ablations  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--out", default=str(ROOT / "results"))
    ap.add_argument("--scenario", default=None)
    ap.add_argument("--ablations", action="store_true", help="also run ours without Layer 2 / without credit")
    args = ap.parse_args()

    params = load_damage_params()
    sc = load_scenario(args.scenario)
    fn = compare_with_ablations if args.ablations else compare
    per_seed = [fn(sc, params, seed) for seed in range(args.seeds)]
    agg = aggregate(per_seed)
    names = list(STRATEGIES) + (list(ABLATIONS) if args.ablations else [])

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(
        json.dumps({"scenario": sc.name, "seeds": args.seeds, "aggregate": agg, "per_seed": per_seed}, indent=2),
        encoding="utf-8",
    )
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["seed", "strategy", "total_damage", "violations", "jain", "cascades", "fallback_ticks"])
        for seed, m in enumerate(per_seed):
            for s in names:
                r = m[s]
                w.writerow([seed, s, f"{r['total_damage']:.4f}", r["violations"], f"{r['jain']:.4f}",
                            r["cascades"], r["fallback_ticks"]])

    print(f"scenario={sc.name}  seeds={args.seeds}  (damage = modeled proxy)")
    print(f"{'strategy':<14}{'damage (mean±std)':>24}{'violations':>14}{'jain':>10}{'cascades':>11}")
    for s in names:
        a = agg[s]
        print(f"{s:<14}{a['total_damage']['mean']:>14.1f} ± {a['total_damage']['std']:<7.1f}"
              f"{a['violations']['mean']:>14.1f}{a['jain']['mean']:>10.3f}{a['cascades']['mean']:>11.2f}")


if __name__ == "__main__":
    main()
