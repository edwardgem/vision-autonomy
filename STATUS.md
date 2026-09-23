# STATUS

| Component | Status | Findings | Issues/Decisions | Next Step |
|---|---|---|---|---|
| 0. Alignment | Done (2026-09-23) | AMP RLHF mechanics + payment simulator studied; see HANDOFF.md | D1–D5 agreed: local AMP, Option B semantics, auto-approve admin WIs, repo here, LOCO + PatchCore | Start Component 1 |
| 1. Dataset & model | **Done — approved 2026-09-23** | LOCO downloaded (SHA-256 verified), 1,568 test imgs (63% anomalous); PatchCore defaults scored, raw scores in results/patchcore_scores.csv; AUROC 0.70–0.93/category, logical weaker (screw_bag 0.61) | Open: threshold calibration source (val-good has mild shift vs test-good); stream length vs Stage 2 gates; seed count; 3,651 vs 3,644 image count | Edward approves → switch to stronger model → Component 2 (EXPERIMENT_PLAN.md) |
| 2. Experiment design | **Draft — awaiting Edward's review** | EXPERIMENT_PLAN.md + frozen config/{calibration,amp_policy,experiment}_v1.json. tau = val-normal q0.95; one AMP agent per category; 5 stream seeds; row counts = AMP defaults x0.4, rates = AMP defaults | Found in AMP source: base-policy rules default ON would auto-approve all Stage 2 items (disabled); binary auto-reject must be disabled (auto_reject_threshold 1.01 — schema risk); tick windows drop rows unless tick_minutes covers elapsed time (1440); training seed random unless RLHF_TRAINING_SEED set; outcome feedback required for training | Edward approves plan + §11 prerequisites → pre-registration commit → Component 3 (Sonnet OK) |
| 3. Simulator + E2E test | Not started | — | — | — |
| 4. Run & results | Not started | — | — | — |
