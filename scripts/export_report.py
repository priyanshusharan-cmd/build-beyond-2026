"""Export results/results.json (from run_benchmark.py) as a Markdown report.

Usage: python scripts/export_report.py [--in results/results.json] [--out docs/RESULTS.md]
Every number is read from the benchmark output; nothing is typed in by hand.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABELS = {"ours": "Ours (Layer 1 + Layer 2 + credit)", "blind": "Blind grab", "proportional": "Proportional",
          "priority": "Static priority", "ours_no_l2": "Ablation: ours without Layer 2",
          "ours_no_credit": "Ablation: ours without credit"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=str(ROOT / "results" / "results.json"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "RESULTS.md"))
    a = ap.parse_args()
    data = json.loads(Path(a.src).read_text(encoding="utf-8"))
    agg, per = data["aggregate"], data["per_seed"]
    lines = [f"# Benchmark results: {data['scenario']}", "",
             f"{data['seeds']} seeds, identical seeded disaster for every strategy. "
             "Damage is a **modeled proxy**, not a real-world measurement.", "",
             "| Strategy | Damage (mean ± std) | Violations | Jain | Cascades |", "|---|---|---|---|---|"]
    for s, r in agg.items():
        lines.append(f"| {LABELS.get(s, s)} | {r['total_damage']['mean']:.1f} ± {r['total_damage']['std']:.1f} | "
                     f"{r['violations']['mean']:.1f} | {r['jain']['mean']:.3f} | {r['cascades']['mean']:.2f} |")
    if "ours" in agg and "priority" in agg:
        d = [m["ours"]["total_damage"] - m["priority"]["total_damage"] for m in per]
        wins = sum(1 for x in d if x < 0)
        lines += ["", f"Paired against static priority, ours had lower damage on {wins} of {len(d)} seeds "
                      f"(mean difference {sum(d) / len(d):+.1f})."]
    lines += ["", "Read these honestly: where a baseline matches or beats ours on a metric, that is a real "
                  "result of this model, not something to hide."]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
