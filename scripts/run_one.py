"""Run one strategy on one seed, write the JSONL event log, print a readable timeline.

Usage: python scripts/run_one.py [--strategy ours|blind|proportional|priority] [--seed 0] [--every 30]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from blackout_arena.config import load_damage_params, load_scenario  # noqa: E402
from blackout_arena.metrics import compute_metrics  # noqa: E402
from blackout_arena.sim import run_simulation  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="ours")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--every", type=int, default=30, help="print every N ticks")
    ap.add_argument("--out", default=str(ROOT / "results"))
    a = ap.parse_args()
    run = run_simulation(load_scenario(), load_damage_params(), a.seed, a.strategy)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"events_{a.strategy}_seed{a.seed}.jsonl"
    run.log.write(path)
    print(f"{'tick':>4} {'time':>5} {'supply':>7} {'hosp':>6} {'water':>6} {'tele':>6} {'emerg':>6} "
          f"{'damage':>8}  notes")
    for r in run.records:
        notes = " ".join(f"CASCADE-{c}" for c in r.cascades) + (" FALLBACK" if r.used_fallback else "")
        if r.tick % a.every == 0 or notes:
            g = r.grants
            print(f"{r.tick:>4} {r.tick // 60:02d}:{r.tick % 60:02d} {r.supply:>7.1f} {g['hospital']:>6.1f} "
                  f"{g['water']:>6.1f} {g['telecom']:>6.1f} {g['emergency']:>6.1f} {r.damage_cum:>8.1f}  {notes}")
    m = compute_metrics(run)
    print(f"\nstrategy={a.strategy} seed={a.seed} damage={m['total_damage']:.1f} (modeled proxy) "
          f"violations={m['violations']} jain={m['jain']:.3f} cascades={m['cascades']}")
    print(f"event log: {path}  ({len(run.log.events)} events)")


if __name__ == "__main__":
    main()
