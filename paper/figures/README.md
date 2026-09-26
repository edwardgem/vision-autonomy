# Paper figures (CVC 2027 draft)

These scripts regenerate the figures in Sections 3–4 of the paper from committed results. Run them from the
repository root with the project venv. The PNGs are written to `paper/figures/out/`.

| Script | Figures | Inputs |
|---|---|---|
| `sec3_figures.py` | Fig. 1: perception error by category and type. Fig. 2: Experiment 3 stream design. Fig. 3: Clopper–Pearson certification and probe power | `results/inputs/decision_records.csv`; exact binomial computations, matching EXPERIMENT_PLAN_3 T2/T3 |
| `sec4_exp12_figures.py` | Fig. 4: Stage 1 agreement, Exp 1 vs Exp 2 basis. Fig. 5: Stage 2 window risk–coverage. Fig. 6: autonomous executions by action class | `results/exp2/aggregate/*` |
| `sec4_exp3_figures.py` | Fig. 7: Experiment 3 authority timeline and cumulative post-change escapes | `results/exp3/runs/*`, `results/exp3/aggregate/*`. Recomputes governance/T1/T0 escapes per item and asserts they equal the preregistered totals |

```bash
.venv/bin/python paper/figures/sec3_figures.py
.venv/bin/python paper/figures/sec4_exp12_figures.py
.venv/bin/python paper/figures/sec4_exp3_figures.py
```
