# AMP product issues found during the vision-autonomy experiments (not fixed during the experiments)

## ISSUE-1 — Stage 1 re-entry after a Stage 2 retrain cannot be re-promoted (found 2026-09-24, code inspection)
- **Where:** `rlhf/src/services/rlhf/EvalActivateHandlers.ts` (ACTIVATE) and `StageTickHandler.ts::scheduleFollowUps`; flags written by
  `amp-backend/app.py` (Stage 2 promotion workitem resolution).
- **Behaviour:** activating a retrained model moves a Stage 2 agent back to Stage 1 and resets `stage1_eval_rows`, but keeps
  `metadata.stage1_promotion_approved = true` and the cumulative `stage1_agreement_count/agree` of the previous model. The tick handler only
  proposes Stage 2 promotion while `stage1_promotion_approved` is false, so the new model is never re-proposed; its cumulative agreement also
  mixes in the previous model's rows. Only the manual "clear training data" admin action clears these keys.
- **Impact:** an agent that retrains in Stage 2 silently stays in Stage 1 (full HITL) indefinitely; contradicts the playbook's intent that each
  new model re-earns Stage 2 (Playbook §11.3).
- **Status:** intentionally unchanged during Experiment 2 (would be a second experimental change). To be confirmed empirically in the
  Experiment 2 E2E (EXPERIMENT_PLAN_2.md §8.5) and fixed afterwards (reset the Stage 1 promotion keys on activation into Stage 1).

## ISSUE-2 — Stage 1 gates use inconsistent recommendation semantics (found 2026-09-24)
- Cumulative gate: `model_score ≥ threshold_used` (Stage 2 execution threshold); recent-20 gate: stored `recommended_decision`
  (`recommend_threshold`). Addressed for experimentation by the opt-in `promotion.stage1_agreement_basis` parameter (default unchanged);
  whether to change the default is a product decision after Experiment 2.

## ISSUE-3 — HITL server dropped RLHF policy fields (fixed, hitl-agent `746a268`, branch `fix/normalize-policy-rlhf-fields`, not yet merged/deployed)
