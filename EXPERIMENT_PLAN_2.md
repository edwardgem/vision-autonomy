# EXPERIMENT_PLAN_2.md — Separating Stage 1 qualification from Stage 2 execution

Status: **PREREGISTERED 2026-09-24 (tag `prereg-exp2-v1`), design approved by Edward; implementation and E2E acceptance complete (§11, §12).** On approval: the AMP parameter (§4) is implemented and tested,
its commits are recorded in §11, and this file plus `config/exp2/*` are committed and tagged `prereg-exp2-v1` **before any Experiment 2 run**,
including the E2E. Results go to `RESULTS-2.md`. Experiment 1 (`EXPERIMENT_PLAN.md`, `RESULTS.md`, `results/runs/`) remains the primary
experiment and is not altered.

## 1. Motivation (from Experiment 1)

In Experiment 1, Stage 1 → 2 promotion happened in 1/25 runs. In the 24 other runs the **cumulative-agreement gate** was the only gate that failed
(RESULTS.md §3.2). Inspecting the code for this plan established the following (verified 2026-09-24):

| Stage 1 → 2 gate | Recommendation compared with the human decision | Code |
|---|---|---|
| Primary: cumulative agreement ≥ 0.70 | approve iff `model_score ≥ threshold_used`, where `threshold_used` = Stage 2 auto-execute threshold **0.90** | `rlhf/src/db/repos/ApprovalRepo.ts::aggregateWindowStats` |
| Stability: last-20 agreement ≥ 0.65 | the stored `signals_json.recommended_decision`, i.e. approve iff P ≥ `recommend_threshold` **0.65** (the recommendation shown to reviewers) | `ApprovalRepo.ts::getStage1RecentAgreement` |

Empirical confirmation from Experiment 1's stored gate values: the final-tick recent-20 rate matches a 0.65 recomputation in **24/24** non-promoting runs
and a 0.90 recomputation in only 4/24 (where both happen to coincide).
**Correction to the premise of this experiment as first drafted:** Experiment 1 did **not** use 0.90 for both gates. AMP already evaluates its two Stage 1 gates
on two different recommendation thresholds. (Suggested erratum for RESULTS.md / amendment v1.2 #4: pending Edward's approval.)

## 2. Hypothesis and single change

**Purpose.** Experiment 1 showed that AMP's two Stage 1 promotion gates use inconsistent recommendation semantics: the cumulative gate uses
the Stage 2 execution threshold (P ≥ 0.90); the recent-20 gate already uses the Stage 1 recommendation (P ≥ 0.65). Experiment 2 tests whether
using the existing Stage 1 recommendation semantics consistently for Stage 1 qualification leads to effective controlled autonomy, while every
individual autonomous decision still requires P ≥ 0.90. The aim is not to lower a threshold or to obtain more promotions.

**Hypotheses.**
- (a) *Secondary / descriptive:* more category × order runs reach Stage 2 than in Experiment 1. This is partly predictable from Experiment 1 (§6)
  and is not confirmatory.
- (b) *Primary:* Stage 2 autonomous decision quality will be consistent with or better than a static confidence threshold granting the same
  number of autonomous decisions on the same items (endpoint and reading rule in §7). This is a pre-declared descriptive reading rule with a
  run-level bootstrap interval, **not** a formal, powered non-inferiority test, and must not be described as one.

**Single experimental change.** The cumulative-agreement gate counts a Stage 1 recommendation as *approve* iff P(human approves proposal) ≥ 0.65, taken from
the same stored `recommended_decision` the recent-20 gate already uses. So both agreement gates use one definition:
- cumulative agreement ≥ 0.70 (threshold unchanged);
- recent-20 agreement ≥ 0.65 (threshold and definition unchanged).

**Unchanged** (identical to Experiment 1; the policy files differ only in the one field in §4):
- dataset, frozen PatchCore scores, proposal thresholds τ_c, and `decision_records.csv` (sha256 `eb24ae6b…fa9`);
- the 5 categories, and stream seeds 0–4 with exactly the same stream construction;
- AMP features, training, calibration and seed (`RLHF_TRAINING_SEED=vision-loco-v1`), and the row-count scaling (×0.4);
- the Stage 0 → 1 rules, the model-acceptance mechanism, the oracle, and the safety gate;
- the probe mechanism (10 %, ≥ 2/day), and auto-reject disabled (`auto_reject_threshold` 1.01);
- the Stage 2 auto-execute threshold of **0.90**, so reaching Stage 2 does not lower the confidence required for an individual autonomous decision;
- the retrain and rollback settings, baselines A–C, metrics, and the tick/settle procedure;
- the AMP versions, apart from the new parameter's code (§4).

## 3. Why the change is expected to matter only through the gate

- **Stage 0/1 path (per cell).** Experiment 2 uses the same records, the same stream order, the same deterministic training and the same policy values for everything else.
  Each cell's Stage 0 model and Stage 1 probabilities should therefore be identical to Experiment 1's until the point where Experiment 2 first promotes.
  That is tested as an acceptance criterion (§8), not assumed.
- **Divergence.** The two experiments diverge only if and when the cumulative gate (at 0.65) passes together with the other three gates.
  After that, Stage 2 behaviour is governed by unchanged rules.

## 4. AMP implementation (smallest change, configuration-switched)

Add a policy parameter `autonomy_ops.promotion.stage1_agreement_basis` with values:
- **`execution_threshold`** (default): the current behaviour. Absent or unknown values mean this, so **Experiment 1, the payment agent and all other agents are unchanged.**
- **`recommendation`**: the cumulative gate uses `signals_json.recommended_decision ∈ {approve, reject}`, the same rows and definition as the recent-20 gate.

Required edits (exact diff and commit hashes recorded in §11 before preregistration):
1. `amp-backend/autonomy_ops_catalog.py`: new string field (enum above, default `execution_threshold`).
2. `amp-backend/app.py::_extract_rlhf_params_from_policy`: pass `stage1_agreement_basis` into `rlhf_agent_config.params_json`.
3. `rlhf`: `aggregateWindowStats` also returns recommendation-basis Stage 1 counts, and `StageTickHandler.computeNextState` picks the pair of counts by
   the parameter. `dist/` is rebuilt, and hitl-agent needs no change.
4. Tests:
   - **Default:** counts and gate decisions are byte-identical to the current code.
   - **`recommendation`:** counts equal the recent-gate definition applied to all Stage 1 rows.
   - The existing suites pass.
5. Restart `amp`; verify the payment agent's `params_json` shows the default and its behaviour is unchanged.

**Pre-flight facts that stay as they are (existing AMP behaviour, verified in code, not changed):**
- **(F1)** Stage 1 `recommended_decision` = approve iff P ≥ `recommend_threshold_stage1` (null) → policy `recommend_threshold` (0.65).
- **(F2)** The first request after a model activation can have no score (cache warm-up). Its `recommended_decision` is null and it is excluded from both gates, as in Experiment 1.
- **(F3)** Hard-blocked rows: the old cumulative definition counts them as *reject*; the recommendation basis follows the stored decision. No row is hard-blocked in this data (the criterion is always met).
- **(F4) Re-entry.** A Stage 2 retrain (after 80 Stage 2 human rows) whose candidate passes the model-acceptance check is approved (D3) and activated, and the agent **re-enters Stage 1**.
  On activation AMP resets `stage1_eval_rows` but **does not** clear the cumulative agreement counters or the `stage1_promotion_approved` flag. Those are cleared only
  by the manual "clear training data" admin action. The tick handler only proposes promotion while `stage1_promotion_approved` is false.
  **Consequence (from code; to be confirmed in E2E):** a re-entered agent is not re-promoted in this configuration and stays in Stage 1 for the rest of its stream.
  This is identical AMP behaviour in both experiments (Experiment 1 never exercised it) and is **not** changed here (fixing it would be a second change).
  **A run's Stage 2 window ends when the agent re-enters Stage 1**; later Stage 1 items are human-reviewed and counted in the full-stream metrics only.
  Re-entries are reported per run (§7). Recorded separately as an AMP product issue (`AMP_ISSUES.md`) for remediation after this experiment.

## 5. Conditions and runs

| Condition | Experiment 2 |
|---|---|
| A human oracle, B model only, C static HITL (δ = 1σ, plus sweep) | identical to Experiment 1 (deterministic; reused, not recomputed differently) |
| D2 AMP progressive, recommendation-basis gate | 25 runs: 5 categories × stream seeds 0–4, each on a **fresh** agent `vis-loco2-{category}-s{seed}` |
| D1 (Experiment 1) | the 25 completed Experiment 1 runs, used as the paired reference |

- **Execution:** sequential, via the Experiment 1 driver with the Experiment 2 config.
- **Worker cleanup:** each agent's RLHF worker is stopped with the Experiment 1 v1.3 toggle mechanism **immediately after its run completes**. That is declared here, not an incident.
  Stored policies then read `rlhf_enabled: false`.
- **Infrastructure aborts:** handled by the Experiment 1 v1.2 rule (one re-run on a fresh `-r2` agent; the first complete run is used; aborted attempts are kept).
- **Seed fallback:** the Experiment 1 time rule applies (> 3 h per seed → seeds 0–2); not expected, at ≈ 22 min per seed in Experiment 1.

## 6. Disclosure: what is already known before running

- **Stage 1 agreement at 0.65 is already on record.** RESULTS.md §3.3 reports, for each Experiment 1 run, the final cumulative agreement of the 0.65 recommendation over all its Stage 1 rows
  (0.546–0.880). It was computed descriptively for Experiment 1, before this plan. Because of §3, **which cells can pass the new cumulative gate is largely inferable from
  Experiment 1 data**, so promotion frequency is **not** a confirmatory outcome here.
- **No tick-by-tick counterfactual computed.** In accordance with Edward's instruction, no counterfactual Experiment 2 promotion timing, Stage 2 window, or outcome has been computed from Experiment 1 records.
  None will be before the Experiment 2 runs complete.
- **What is genuinely unknown** is Stage 2 behaviour after promotion: coverage at P ≥ 0.90, autonomous errors, retrains and re-entry. That is where the confirmatory question sits (§7).

## 7. Endpoints (fixed before running)

**Primary (confirmatory): Stage 2 autonomous decision quality versus static HITL at equal coverage.**
For each Experiment 2 run that reaches Stage 2, take the items AMP handled at Stage 2 (its *window*). Let k = the number of those AMP executed autonomously.
Static HITL at matched coverage executes the k window items with the largest `margin_abs` (ties by `image_id`), as in Experiment 1's T5. Pooled over runs:

- r_AMP = Σ autonomous errors_AMP / Σ k, and r_static = Σ autonomous errors_static / Σ k.
- Δ = r_AMP − r_static, with a 95 % percentile bootstrap CI resampling **runs** (10,000 resamples, seed 2026).
- **Pre-declared reading:**
  - *consistent with the hypothesis* if Δ ≤ 0 and the CI upper bound < +0.05;
  - *contradicts* if the CI lower bound > 0;
  - otherwise *inconclusive*.
- If fewer than 3 runs reach Stage 2: *insufficient data*, and results are descriptive only.
- **Also reported:** escaped defects among autonomous decisions (FA/k) for both, and per-category counts.

**Secondary (descriptive; Experiment 2 vs Experiment 1, paired by cell):**
1. Promotion: runs reaching Stage 2; Stage 1 and Stage 2 entry positions; gate history (which gates passed at each tick); retrains; Stage 1 re-entries; rollbacks; auto-disables.
2. Stage 2 window: coverage (autonomous/window), probe count, below-0.90 escalations.
3. Full stream (T2 form): accuracy, FA, FR, autonomous rate, HITL rate, autonomous error rate. **Final accuracy must be reported next to the HITL rate**, as in Experiment 1.
4. By anomaly type (T4 form).
5. Static HITL δ = 1σ on the same windows, and risk–coverage figures (F1/F1b form) with Experiment 1 and Experiment 2 AMP points.
6. Determinism check outcome (§8).

**Not claimed without a supporting comparison:** safety, accuracy or autonomy improvements over static HITL. Non-promotion is reported as observed, neither success nor failure.

## 8. Acceptance before the 25 study runs (E2E on fresh agents `vis-loco2-e2e-*`, stream seed 999, not a study seed)

1. Everything Experiment 1's E2E required: reconciliation, zero auto-rejects, base-policy rules not firing, the training seed in the worker, and admin approvals logged.
2. **Parameter effect:**
   - AMP's stored cumulative counts equal the recommendation-basis recomputation.
   - The recent-20 values are unchanged in definition.
   - The Stage 2 auto-execute threshold used per decision is 0.90.
3. **Default preserved:** `params_json` of an existing Experiment 1 agent and of `invoice-payment-agent-5c58` shows `execution_threshold` (or absent).
4. **Determinism:** Stage 1 approval probabilities of `vis-loco2-e2e-*` (juice_bottle, seed 999) equal those of Experiment 1's E2E agent `vis-loco-e2e-3b` at the same stream positions,
   up to the first position where the stage differs. If they differ, stop: the paired design must be re-assessed.
5. **Retrain / re-entry path (F4):** if it occurs in the E2E, record the behaviour. If it does not, run a second E2E category (`screw_bag`, seed 999, which is more likely to accumulate Stage 2 human rows).
   If the observed behaviour contradicts F4, stop and escalate.
6. **Stop and escalate** on any AMP behaviour that would require a second change.

## 9. Outputs

- `results/exp2/runs/<run_id>/…` (same files as Experiment 1), `results/exp2/aggregate/`, `results/exp2/tables/` (T1 reused; T2–T5 with D1 and D2 rows), and `results/exp2/figures/`.
- `results/exp2/primary_endpoint.json`, containing Δ, the CI, the per-run k, the errors, and the reading.
- **`RESULTS-2.md`**, in the same structure as RESULTS.md:
  - observations first;
  - interpretation limited to the endpoints;
  - discussion hypotheses separated;
  - Experiment 2 always reported as a follow-up to Experiment 1, not a replacement.

## 10. Threats to validity (in addition to Experiment 1 §7)

1. The design is partly unblinded (§6).
2. The single-change claim depends on the determinism check (§8.4).
3. AMP's re-entry behaviour (F4) can end Stage 2 windows early, and it is inherited, not designed.
4. Primary-endpoint power is limited by the number and length of Stage 2 windows (≤ 25 runs, at most ≈ 115–180 Stage 2 items each).
5. The same 1,568 images are reused. Experiment 2 is a paired follow-up, not an independent replication.
6. **Pairing is exact only until promotion (observed in E2E, §12).** After promotion, AMP's unseeded probe selection (hash of a random
   decision-point id) changes which Stage 2 items receive human labels. That changes the Stage 2 retrain data and therefore whether a retrained
   candidate passes the model-acceptance check (+0.037 vs +0.012 against the 0.03 bar in the E2E pair). So Stage 2 trajectories, retrains and
   re-entries differ between Experiment 1 and 2 partly by chance, not only because of the gate change. Post-promotion Experiment 1 vs 2
   differences are reported as descriptive, not attributed solely to the parameter.
7. The rlhf `dist/` running during Experiment 1 predated rlhf commit `d92f45e` (a Stage 0 count filter by `stage_entered_at`); the rebuild for
   Experiment 2 activates it. For fresh agents it is a no-op. That was confirmed empirically: identical first model and identical Stage 0/1 probabilities vs Experiment 1 (§12).

## 11. Implementation record (frozen before `prereg-exp2-v1`)

| Item | Value |
|---|---|
| amp-backend | branch `feat/stage1-agreement-basis`, commit **`ad5e7e8`** (on `d2a42ca`): catalog field `promotion.stage1_agreement_basis` (choices; absent/invalid → `execution_threshold`) + pass-through in `_extract_rlhf_params_from_policy` + `tests/test_stage1_agreement_basis.py` |
| rlhf | branch `feat/stage1-agreement-basis`, commit **`2d3356e`** (on `59fffbd`): `ApprovalRepo.aggregateWindowStats` adds recommendation-basis Stage 1 counts; `StageTickHandler` selects counts by basis and records it in metadata/debug; `tests/stage1_agreement_basis.test.ts`; `dist/` rebuilt (also activates earlier `d92f45e`, see §10.7) |
| hitl-agent | unchanged: `746a268` (Experiment 1 fix) |
| amp-backend tests | 759 passed (baseline 755 + 4 new); 0 failed |
| rlhf tests | 91 run: 88 passed; the same 3 pre-existing failures as the unmodified baseline (gate_orchestrator "creates approval_request…" expects `model` but base-policy rules now return `rules_strict`; 2 override-validation fixtures), unrelated to Stage 1 gates; 5/5 new tests pass |
| Real-data regression (rebuilt SQL, 24 completed Experiment 1 agents, full history) | default counts = AMP-stored Experiment 1 cumulative counts **24/24**; recommendation counts = stored-recommendation definition **24/24** |
| Default compatibility | `invoice-payment-agent-5c58` and Experiment 1 agents: `stage1_agreement_basis` absent from `params_json` → `execution_threshold`; payment worker respawned on the new `dist/`, no other change |
| Simulator | vision-autonomy `591ceda`: `--config` (Experiment 2 policy, agent pattern `vis-loco2-*`, `results/exp2`); Experiment 1 default path unchanged. Later: worker-stop filter includes `vis-loco2-*`; driver halts if a post-run worker stop fails |
| `config/exp2/amp_policy_exp2_v1.json` | `6b573506feda1f6e4189c5e8ee1e822a70ade71fe4fd95b92472099d8234b300` (experimental diff vs v1: `autonomy_ops.promotion.stage1_agreement_basis = recommendation`; plus `policy_id`, `comment`) |
| `config/exp2/experiment_exp2_v1.json` | `d755b694c5e42ab92317d28b430f9e3cd91de2674a9f7b46fa600c04f3010ffc` |
| Reused unchanged | `config/amp_policy_v1.json` `f83fc31f…edae` (reference); `config/calibration_v1.json` `a33653b2…6d95`; `results/inputs/decision_records.csv` `eb24ae6b…fa9`; `results/patchcore_scores.csv` `5e261c7b…8b28` |

## 12. E2E acceptance record (engineering validation only; never study evidence)

Agent `vis-loco2-e2e-1`, juice_bottle, stream seed 999; reference: Experiment 1 E2E agent `vis-loco-e2e-3b` (same stream).
Evidence: `results/exp2/e2e/vision-loco-exp2-v1-vis-loco2-e2e-1-20260924T164943Z/` (incl. `e2e_acceptance.json`).

| §8 criterion | Result |
|---|---|
| 1 Generic | PASS: 330 = 330 = 330 reconciled; 0 auto-rejects; 0 violations; 0 failed jobs; worker seed `vision-loco-v1`; testing mode off; admin approvals logged (model ×2, Stage 2 promotion ×1) |
| 2 Parameter effect | PASS: AMP stored cumulative 85/99 with basis `recommendation`; recommendation recomputation 85/99 (execution-threshold recomputation would be 74/99). Recent-20: AMP 0.85 = recomputation 0.85 (definition unchanged). Stage 2: `threshold_used` = 0.90 for every item; 0 autonomous decisions with P < 0.90 (min 0.9008); 0 non-probe human items with P ≥ 0.90 |
| 3 Default preserved | PASS (see §11) |
| 4 Determinism | **PASS**: first model identical (max parameter difference 0.0); 229 scored items before stage divergence, max |ΔP| = 0.0; no missing-score mismatch. Both runs promoted to Stage 2 at item 161 (this stream already passed under the Experiment 1 basis). Stage-divergence at item 311 (Experiment 2 re-entered Stage 1). The 16 routing differences before 311 are all Stage 2 probe selections (Experiment 2: 4 probes, Experiment 1: 16), the known unseeded source (§10.6) |
| 5 Retrain / re-entry (F4) | **Exercised.** 81 Stage 2 human rows → retrain → candidate accepted (+0.037 ≥ 0.03) → approved → activated → **Stage 1 at item 311**. After re-entry AMP kept `stage1_promotion_approved = true` and carried over the cumulative counts (99 = 79 first-model rows + 20 new) while resetting `stage1_eval_rows` (20): **consistent with F4**. Non-re-promotion itself was not observable (stream ended 20 rows after re-entry, below the 80-row sample gate); the blocking condition is unambiguous in code. No second change needed |
| 6 Design change required? | **No.** Two operational fixes were made to the simulator (not AMP, not experimental parameters): the worker-stop name filter, and the driver halting on a failed stop |
