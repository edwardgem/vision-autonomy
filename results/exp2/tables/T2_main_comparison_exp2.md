**T2 (Experiment 2). Full-stream comparison of conditions A-C and AMP under the Experiment 1 (D1) and Experiment 2 (D2) Stage 1 gate.**

| Condition | Accuracy | FA rate | FR rate | Autonomous rate | HITL rate | Autonomous error rate |
|---|---|---|---|---|---|---|
| A Human oracle | 1.000 | 0.000 | 0.000 | 0.000 | 1.000 | — |
| B Model only | 0.680 | 0.477 | 0.049 | 1.000 | 0.000 | 0.320 |
| C Static HITL (δ=1σ) | 0.788 | 0.329 | 0.010 | 0.761 | 0.239 | 0.279 |
| D1 AMP, Experiment 1 (execution-threshold gate), 5 seeds mean ± SD | 0.997 ± 0.007 | 0.004 ± 0.009 | 0.002 ± 0.004 | 0.019 ± 0.042 | 0.981 ± 0.042 | 0.168 (n=1/5) |
| D2 AMP, Experiment 2 (recommendation gate), 5 seeds mean ± SD | 0.996 ± 0.008 | 0.005 ± 0.010 | 0.003 ± 0.004 | 0.063 ± 0.024 | 0.937 ± 0.024 | 0.044 ± 0.078 |

Final accuracy must be read together with the HITL rate. A–C do not depend on stream order. D1/D2: pooled over 5 categories per seed, then mean ± SD across seeds.
