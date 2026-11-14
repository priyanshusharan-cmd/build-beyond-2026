# Benchmark results: default_8h

20 seeds, identical seeded disaster for every strategy. Damage is a **modeled proxy**, not a real-world measurement.

| Strategy | Damage (mean ± std) | Violations | Jain | Cascades |
|---|---|---|---|---|
| Ours (Layer 1 + Layer 2 + credit) | 179.7 ± 46.4 | 0.0 | 0.991 | 4.10 |
| Blind grab | 3368.1 ± 281.4 | 413.9 | 1.000 | 415.85 |
| Proportional | 787.2 ± 153.0 | 0.0 | 1.000 | 2.80 |
| Static priority | 194.0 ± 58.6 | 0.0 | 0.984 | 3.45 |
| Ablation: ours without Layer 2 | 190.9 ± 70.6 | 0.0 | 0.990 | 2.65 |
| Ablation: ours without credit | 178.8 ± 47.7 | 0.0 | 0.991 | 4.20 |

Paired against static priority, ours had lower damage on 11 of 20 seeds (mean difference -14.4).

Read these honestly: where a baseline matches or beats ours on a metric, that is a real result of this model, not something to hide.
