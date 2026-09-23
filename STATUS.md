# STATUS

| Component | Status | Findings | Issues/Decisions | Next Step |
|---|---|---|---|---|
| 0. Alignment | Done (2026-09-23) | AMP RLHF mechanics + payment simulator studied; see HANDOFF.md | D1–D5 agreed: local AMP, Option B semantics, auto-approve admin WIs, repo here, LOCO + PatchCore | Start Component 1 |
| 1. Dataset & model | **Done — approved 2026-09-23** | LOCO downloaded (SHA-256 verified), 1,568 test imgs (63% anomalous); PatchCore defaults scored, raw scores in results/patchcore_scores.csv; AUROC 0.70–0.93/category, logical weaker (screw_bag 0.61) | Open: threshold calibration source (val-good has mild shift vs test-good); stream length vs Stage 2 gates; seed count; 3,651 vs 3,644 image count | Edward approves → switch to stronger model → Component 2 (EXPERIMENT_PLAN.md) |
| 2. Experiment design | **Done — approved & pre-registered (tag `prereg-v1`, 4da48ff)** | EXPERIMENT_PLAN.md + frozen config/*_v1.json; RQ wording per Edward | Testing mode verified off; MODEL_MODE=file; RLHF_TRAINING_SEED approved (set via amp-backend/.env + pm2 restart); API key in gitignored .env | Component 3 (Sonnet) — see HANDOFF.md 'Component 3 brief' |
| 3. Simulator + E2E test | Ready to start | — | Must verify auto_reject_threshold 1.01 honoured; hard-stop list in HANDOFF.md | Build inputs + sim, run E2E on vis-loco-e2e-1, report to Edward |
| 4. Run & results | Not started | — | — | — |
