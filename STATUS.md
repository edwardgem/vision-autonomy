# STATUS

| Component | Status | Findings | Issues/Decisions | Next Step |
|---|---|---|---|---|
| 0. Alignment | Done (2026-09-23) | AMP RLHF mechanics + payment simulator studied; see HANDOFF.md | D1–D5 agreed: local AMP, Option B semantics, auto-approve admin WIs, repo here, LOCO + PatchCore | Start Component 1 |
| 1. Dataset & model | **Done — awaiting Edward's review** | LOCO downloaded (SHA-256 verified), 1,568 test imgs (63% anomalous); PatchCore defaults scored, raw scores in results/patchcore_scores.csv; AUROC 0.70–0.93/category, logical weaker (screw_bag 0.61) | Open: threshold calibration source (val-good has mild shift vs test-good); stream length vs Stage 2 gates; seed count; 3,651 vs 3,644 image count | Edward approves → switch to stronger model → Component 2 (EXPERIMENT_PLAN.md) |
| 2. Experiment design | Not started | — | Guardrails in HANDOFF.md | EXPERIMENT_PLAN.md, checkpoint |
| 3. Simulator + E2E test | Not started | — | — | — |
| 4. Run & results | Not started | — | — | — |
