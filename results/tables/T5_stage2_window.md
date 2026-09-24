**T5. Stage 2 window comparison: all conditions evaluated on exactly the items AMP handled at Stage 2 (runs that reached Stage 2).**

| Condition | Stage 2 items (total) | Autonomous (total) | Autonomous rate (mean ± SD over seeds) | Autonomous error rate (mean ± SD) | Autonomous FA (total) | Autonomous FA / autonomous (mean ± SD) | Accuracy (mean ± SD) |
|---|---|---|---|---|---|---|---|
| AMP progressive | 170 | 149 | 0.876 (n=1/5) | 0.168 (n=1/5) | 20 | 0.134 (n=1/5) | 0.853 (n=1/5) |
| Static HITL δ=1σ | 170 | 133 | 0.782 (n=1/5) | 0.083 (n=1/5) | 10 | 0.075 (n=1/5) | 0.935 (n=1/5) |
| Static HITL matched coverage | 170 | 149 | 0.876 (n=1/5) | 0.107 (n=1/5) | 14 | 0.094 (n=1/5) | 0.906 (n=1/5) |
| Model only | 170 | 170 | 1.000 (n=1/5) | 0.171 (n=1/5) | 23 | 0.135 (n=1/5) | 0.829 (n=1/5) |

Static HITL at matched coverage auto-executes the same NUMBER of items AMP executed autonomously (chosen by largest margin, ties by image_id): no free parameter. Seeds are pooled over categories; per-run detail: results/aggregate/T5_per_run.csv.
