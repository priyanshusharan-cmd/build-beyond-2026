"""Fuzz our strategy: random supply walks and shocks; expect 0 invariant violations.

Usage: python scripts/fuzz.py [--runs 1000]
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from blackout_arena.config import Scenario, load_damage_params, load_scenario  # noqa: E402
from blackout_arena.sim import run_simulation  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1000)
    ap.add_argument("--ticks", type=int, default=40)
    args = ap.parse_args()
    params, base = load_damage_params(), load_scenario().model_dump()
    rng = random.Random(12345)
    violations = fallbacks = 0
    for _ in range(args.runs):
        d = dict(base, ticks=args.ticks)
        d["supply_walk"] = {"sigma": rng.uniform(0, 15), "min": 0, "max": 130, "mean_revert": 0.05}
        d["shocks"] = [
            {"tick": rng.randint(0, 30), "duration": rng.randint(1, 40),
             "delta_mw": rng.uniform(-100, 20), "label": "fuzz"}
            for _ in range(rng.randint(0, 3))
        ]
        r = run_simulation(Scenario(**d), params, rng.randint(0, 10**6), "ours")
        violations += len(r.violations)
        fallbacks += r.fallback_ticks
    print(f"fuzz runs={args.runs} violations={violations} fallback_ticks={fallbacks}")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
