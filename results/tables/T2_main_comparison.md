**T2. Main comparison over the full 1,568-image stream. FA = defect executed as good (rate over GT-defective); FR = good executed as defective (rate over GT-good).**

| Condition | Accuracy | FA rate | FR rate | Autonomous rate | HITL rate | Autonomous error rate |
|---|---|---|---|---|---|---|
| A Human oracle | 1.000 | 0.000 | 0.000 | 0.000 | 1.000 | — |
| B Model only | 0.680 | 0.477 | 0.049 | 1.000 | 0.000 | 0.320 |
| C Static HITL (δ=1σ) | 0.788 | 0.329 | 0.010 | 0.761 | 0.239 | 0.279 |
| D GOV progressive (n=5 seeds, mean ± SD) | 0.997 ± 0.007 | 0.004 ± 0.009 | 0.002 ± 0.004 | 0.019 ± 0.042 | 0.981 ± 0.042 | 0.168 (n=1/5) |

A–C do not depend on stream order (single value). D is pooled over the 5 categories within each seed, then mean ± SD across seeds. Stages 0 and 1 are 100% HITL, so D's full-stream autonomy is bounded by how early each run reaches Stage 2 (at least the first 160 items are always human).
