# RESULTS.md — Vision progressive autonomy on MVTec LOCO AD

Experiment `vision-loco-v1`, preregistered in `EXPERIMENT_PLAN.md` (tags `prereg-v1`, `prereg-v1.1`; amendments v1.2 and v1.3 are
infrastructure/operations only). Runs executed 2026-09-24. Everything below comes from the committed outputs in `results/`.
No condition was added, rerun for results, or tuned. Sections 1–4 are **observations**, §5 is **interpretation**, and §6 is **discussion**
(possible explanations that the measurements do not establish).

**Research question.** Can validated human decisions and model performance be used to progressively grant decision authority to a
vision-based agent while maintaining policy-governed human oversight?

> **Erratum (2026-09-24):** Subsequent code inspection while preparing Experiment 2 established that Experiment 1's cumulative Stage 1
> agreement gate classified recommendations using the Stage 2 auto-execution threshold (P ≥ 0.90), whereas the recent-20 stability gate used
> the stored Stage 1 recommendation based on recommend_threshold (P ≥ 0.65). Earlier wording implying that both gates used 0.90 was incorrect.
> This correction changes no Experiment 1 measurements, gate outcomes, stage transitions, or conclusions.
> *(Evidence: `rlhf/src/db/repos/ApprovalRepo.ts` — `aggregateWindowStats` uses `model_score ≥ threshold_used`; `getStage1RecentAgreement` uses
> `signals_json.recommended_decision`. AMP's stored final-tick recent-20 rate matches a 0.65 recomputation in 24/24 non-promoting runs, a 0.90
> recomputation in 4/24. In this document, "gate agreement" in §3.3 and H1 in §6 refer to the cumulative gate.)*

---

## 1. What was executed

| Item | As executed |
|---|---|
| Evaluation data | MVTec LOCO AD test split, 1,568 images (575 good, 432 structural, 561 logical). **993/1,568 (63.3 %) anomalous: a benchmark distribution, not an assumed production anomaly rate.** |
| Perception | PatchCore (anomalib 2.6.2 defaults, seed 0), frozen raw scores. Proposal = `defective` iff score ≥ τ_c (0.95 quantile of validation-normal scores, fixed before test evaluation) |
| Governance | AMP (local; amp-backend `d2a42ca`, hitl-agent `746a268`, rlhf `59fffbd`). One agent per category × stream seed. Policy `config/amp_policy_v1.json` (row-count parameters = AMP defaults × 0.4; all rate/threshold parameters = AMP defaults, incl. Stage 2 auto-execute threshold 0.90). Features seen by AMP: `proposal`, `score_z`, `margin_abs` |
| Oracle | Approves a proposal iff it equals ground truth. Never wrong. Ground truth never sent to AMP |
| Conditions | A human oracle; B model only; C static HITL (defer iff margin < δ = 1.0 σ, plus δ sweep); D AMP progressive autonomy |
| Runs | D: **25/25 cells complete** (5 preregistered stream seeds × 5 categories). A–C are deterministic functions of the same 1,568 records |
| Integrity | Every D run: items sent = requests in AMP = requests in AMP's tick statistics. 0 autonomous non-approve decisions (auto-reject disabled as preregistered). 0 failed RLHF jobs. Training seed `vision-loco-v1` in every worker. AMP testing mode off. Config files byte-identical to the preregistered versions (sha256 recorded in all 27 manifests) |

**Deviations and incidents (all in the record):**
- **Pre-study E2E.** It first failed because AMP's HITL server dropped policy fields. That was fixed in hitl-agent `746a268`, then the E2E passed (`E2E_REPORT.md`; amendment v1.1).
- **Two study attempts aborted** for infrastructure reasons and were re-run once on fresh agents under a rule declared before the re-runs (amendments v1.2 and v1.3):
  - `juice_bottle` seed 3: a false positive in the simulator's tick guard. The partial run is kept; it was in Stage 1 for items 81–320 and never reached Stage 2. The complete re-run is used and agrees: it also never reached Stage 2.
  - `juice_bottle` seed 4: MySQL connection exhaustion before any item was sent.
- **Worker cleanup after the runs.** Workers of finished agents were stopped via AMP's RLHF toggle, so their stored policy files now read `rlhf_enabled: false`; it was `true` during every run.

## 2. Perception layer (T1)

| Category | AUROC all | AUROC logical | AUROC structural | Proposal FA rate | Proposal FR rate |
|---|---|---|---|---|---|
| breakfast_box | 0.857 | 0.864 | 0.851 | 0.277 | 0.078 |
| juice_bottle | 0.925 | 0.908 | 0.950 | 0.148 | 0.085 |
| pushpins | 0.741 | 0.696 | 0.792 | 0.657 | 0.051 |
| screw_bag | 0.704 | 0.611 | 0.861 | 0.808 | 0.016 |
| splicing_connectors | 0.833 | 0.782 | 0.898 | 0.523 | 0.025 |
| All | 0.812 (macro) | 0.772 | 0.870 | 0.477 | 0.049 |

At the preregistered threshold, the proposal misses 47.7 % of defects (FA) and flags 4.9 % of good parts (FR). Overall proposal accuracy is 68.0 %.
The operating point is conservative toward "good", and misses concentrate in pushpins and screw_bag and in logical anomalies (T4: 54.2 % of logical
anomalies are proposed as good, versus 39.4 % of structural anomalies).

## 3. AMP promotion behaviour (observations)

### 3.1 Stage transitions (T3)

- **Stage 0 → 1: 25/25 runs, all at stream position 81**, the first tick after 80 human rows.
  - Each run trained one candidate model, which AMP's model-acceptance check (auto-eligible-rate gain ≥ 0.03) accepted, then the model-approval workitem was approved.
  - Candidate auto-eligible-rate estimates ranged from 0.04 (screw_bag) to 1.00 (juice_bottle seed 4).
- **Stage 1 → 2: 1/25 runs** (juice_bottle, stream seed 4, from position 161).
  - The other 24 runs stayed in Stage 1 until their streams ended, after 194–260 Stage 1 decisions each.
  - There were no Stage 2 promotions in breakfast_box, pushpins, screw_bag or splicing_connectors (0/5 each), and 1/5 in juice_bottle.
- **None of these occurred in any run:** RLHF auto-disable, rollback, stage regression, or a second trained model.

### 3.2 Which Stage 1 → 2 gate failed

AMP evaluated four hard gates at every tick. In every run the stored gate results start to matter once the sample gate is met (≥ 80 Stage 1 human rows).
Source: `results/aggregate/stage1_gate_history.csv`, from AMP's own `STAGE_TICK_SUMMARY.decision_debug`.

| Gate (threshold) | 24 non-promoting runs | juice_bottle s4 |
|---|---|---|
| Sample (≥ 80 Stage 1 human rows) | met from ≈ position 160 onward | met |
| **Primary: cumulative agreement ≥ 0.70** | **failed at every tick after the sample gate was met** (27–43 ticks per run) | met at the first tick after the sample gate was met |
| Stability: last 20 rows ≥ 0.65 | met at some ticks in all 24 (6–39 of 27–43 ticks per run) | met |
| Safety (repeated failures ≤ 0) | met at every tick | met |

The primary gate is the only one that separated the promoting run from the others. (AMP scores the primary gate as passed while agreement is still undefined at the
first Stage 1 tick, but that tick is before the sample gate can be met, so it has no effect.)

### 3.3 Stage 1 agreement: how it is computed and what it was

AMP's gate statistic compares the human decision with an approve/reject recommendation **at the Stage 2 threshold**: approve iff AMP's P(approve proposal) ≥ 0.90.
The recommendation *displayed* to reviewers at Stage 1 uses 0.65 instead. My recomputation of the gate statistic from the per-decision records matches AMP's stored
value exactly in all 25 runs (`results/aggregate/stage1_agreement_analysis.csv`).

Per category, over the Stage 1 decisions of the runs listed (ranges across seeds):

| Category (runs) | Proposal correct (= oracle approves) | Share with P ≥ 0.90 | Gate agreement (final) | Agreement of displayed 0.65 recommendation |
|---|---|---|---|---|
| breakfast_box (5) | 0.789–0.814 | 0.299–0.381 | 0.490–0.557 | 0.613–0.799 |
| juice_bottle s0–s3 (4) | 0.859–0.888 | 0.466–0.542 | 0.570–0.667 | 0.703–0.880 |
| juice_bottle s4 (1, promoted) | 0.861 | **1.000** | **0.861** | 0.861 |
| pushpins (5) | 0.585–0.638 | 0.074–0.122 | 0.437–0.515 | 0.546–0.655 |
| screw_bag (5) | 0.462–0.492 | 0.038–0.092 | 0.554–0.615 | 0.612–0.654 |
| splicing_connectors (5) | 0.658–0.688 | 0.212–0.247 | 0.545–0.571 | 0.602–0.671 |

Measured facts:
- **Highest gate agreement in a non-promoting run:** 0.670 (juice_bottle s3), counted over the cumulative Stage 1 rows from the 80th row onward.
- **The promoting run is a boundary case.** Every Stage 1 probability was ≥ 0.90 (minimum 0.916), so the gate recommendation was *approve* for every item. Gate agreement therefore
  equalled that run's proposal-correct rate (0.861), which exceeds 0.70.
- **What an "approve everything" recommendation would score (an identity).** Its agreement equals the proposal-correct rate. That rate is above 0.70 in breakfast_box and
  juice_bottle and below 0.70 in pushpins, screw_bag and splicing_connectors.
- **AMP's probability separated correct from incorrect proposals.** The model was trained on the first 80 items, and all rows evaluated below come after them in the stream.
  Its AUROC over each run's Stage ≥ 1 decisions was 0.70–0.84 (category means 0.72–0.81). On the same items, the raw margin feature alone scored 0.58–0.82 (category means 0.59–0.80).
  Source: `results/aggregate/stage1plus_discrimination.csv`.
- **AMP's probabilities were concentrated.** Interquartile ranges were, for example, 0.35–0.65 in screw_bag and 0.61–0.99 in juice_bottle.

## 4. Condition comparison (observations)

### 4.1 Full stream (T2)

| Condition | Accuracy | FA rate | FR rate | Autonomous rate | HITL rate | Autonomous error rate |
|---|---|---|---|---|---|---|
| A Human oracle | 1.000 | 0.000 | 0.000 | 0.000 | 1.000 | — |
| B Model only | 0.680 | 0.477 | 0.049 | 1.000 | 0.000 | 0.320 |
| C Static HITL (δ = 1σ) | 0.788 | 0.329 | 0.010 | 0.761 | 0.239 | 0.279 |
| D AMP progressive (5 seeds, mean ± SD) | 0.997 ± 0.007 | 0.004 ± 0.009 | 0.002 ± 0.004 | 0.019 ± 0.042 | 0.981 ± 0.042 | 0.168 (1 seed with any autonomous decision) |

**AMP's ≈ 99.7 % final accuracy reflects ≈ 98 % human review.** Across all 25 runs (7,840 decisions), 7,691 (98.1 %) were made by the oracle and
149 (1.9 %) executed autonomously. All 149 came from the one promoted run. All 25 AMP errors (20 FA, 5 FR) are among those 149 autonomous decisions.
By seed:
- **Seeds 0–3:** 100 % human, accuracy 1.000.
- **Seed 4:** 90.5 % human, accuracy 0.984.

Condition D's full-stream accuracy is therefore a measure of how much work was routed to the oracle, not of AMP's decision quality. Static HITL executed 76.1 % of
decisions autonomously, with an error rate of 0.279 among them.

### 4.2 By anomaly type (T4)

| Condition | Good (n=575) | Structural (n=432) | Logical (n=561) |
|---|---|---|---|
| B model only, error rate | 0.049 | 0.394 | 0.542 |
| C static HITL, error rate / autonomous rate | 0.010 / 0.797 | 0.231 / 0.690 | 0.405 / 0.779 |
| D AMP, error rate (mean ± SD) / autonomous rate | 0.002 ± 0.004 / 0.014 | 0.003 ± 0.007 / 0.019 | 0.005 ± 0.010 / 0.024 |

Static HITL does not withhold autonomy from logical anomalies: 77.9 % of them are executed autonomously, with an error rate of 0.519 among those decisions.
AMP withheld autonomy from all types in 24/25 runs. Anomaly type was never an AMP input.

### 4.3 The single Stage 2 window (T5): descriptive only

One run (juice_bottle, seed 4) had 170 Stage 2 items. All conditions below are evaluated on those same items.

| Condition | Autonomous | Coverage | Autonomous errors (FA / FR) | Autonomous error rate [95 % Wilson] | Accuracy |
|---|---|---|---|---|---|
| AMP progressive | 149 | 0.876 | 25 (20 / 5) | 0.168 [0.116, 0.236] | 0.853 |
| Static HITL δ = 1σ | 133 | 0.782 | 11 (10 / 1) | 0.083 [0.047, 0.142] | 0.935 |
| Static HITL at AMP's coverage | 149 | 0.876 | 16 (14 / 2) | 0.107 [0.067, 0.167] | 0.906 |
| Model only | 170 | 1.000 | 29 (23 / 6) | 0.171 [0.121, 0.234] | 0.829 |

- **Why AMP's autonomy was close to model-only here.** Every Stage 2 probability in this window was in [0.917, 0.985], so every item cleared the 0.90 threshold.
  The only items sent to a human were the 21 probes (12.4 %). AMP's autonomous error rate (0.168) is close to model-only (0.171).
- **Against static HITL.** At equal coverage, static HITL had fewer autonomous errors (16 vs 25). At δ = 1σ it had fewer autonomous errors at lower coverage.
  The confidence intervals of AMP and the matched-coverage baseline overlap.
- **What the 149 autonomous decisions were:** 67 logical (13 errors), 42 structural (7 errors), 40 good (5 errors).
- **Scope:** one category, one stream order, 170 items. **This comparison is descriptive and does not generalize** to AMP versus static HITL.

### 4.4 Figures

- **F1 (`results/figures/F1_risk_coverage.*`):** risk–coverage curves of the static-HITL δ sweep per category and pooled, with the static δ = 1σ point, the model-only point
  and AMP's full-stream points. In 24/25 runs AMP had zero coverage, so it has no plottable point; each panel states how many seeds made any autonomous decision.
  The one plotted AMP point (juice_bottle, and the pooled seed-4 panel) lies above the static sweep at the same coverage.
- **F1b (`F1b_stage2_window.*`):** the Stage 2 window only. It exists only for seed 4 and shows the same relation as T5.

## 5. Interpretation (limited to what the measurements support)

1. **Under the preregistered configuration, AMP granted autonomous authority rarely.** It did so in 1 of 25 category × order runs, and in 149 of 7,840 decisions.
   In the other 24 runs, AMP kept every decision with the human for the whole stream. Its Stage 1 → 2 gate never passed, and the gate that failed was always the
   cumulative-agreement gate.
2. **The oversight effect of the governance layer is measurable. Its autonomy effect, with this data and configuration, is small.** Final accuracy near the oracle comes
   from routing ≈ 98 % of decisions to the oracle. It is not evidence that AMP made correct autonomous decisions.
3. **The data do not show that AMP improves safety, accuracy or autonomy relative to static HITL.**
   - Over the full stream, static HITL has far higher autonomy (0.761 vs 0.019) and much lower accuracy (0.788 vs 0.997). That is a different trade-off, not a comparison at equal coverage.
   - The only equal-coverage comparison (§4.3, one run) has AMP with more autonomous errors than static HITL.
   - In that run AMP did **not** withhold autonomy from any items beyond the probes.
4. **The research question is not answered affirmatively by this experiment.** Validated human decisions and model performance *were* used by AMP to decide on promotion.
   The mechanism operated as specified: 25/25 runs moved from Stage 0 to Stage 1 through AMP's own jobs and approvals, and the Stage 1 → 2 gates were evaluated at every tick.
   But authority was granted in only one run, and there the granted autonomy was not more selective than a static confidence threshold.
5. **Non-promotion is reported as observed.** It is neither a demonstrated safety success nor a demonstrated failure: this experiment has no measure of whether
   withholding autonomy was *warranted* for a given category, beyond the proposal accuracies in T1/T4.

## 6. Discussion: possible explanations (not established by these measurements)

These are hypotheses consistent with §3, stated so they can be tested. None was tested here, because the preregistration forbids changing the configuration.

- **H1: the gate statistic.** Gate agreement counts a recommendation as *approve* only when P ≥ 0.90. When few items clear 0.90 (4–12 % in pushpins and screw_bag,
  21–38 % in breakfast_box and splicing_connectors), the recommendation is mostly *reject* while most proposals are correct, and agreement stays low. That can happen even
  though AMP's probability separates correct from incorrect proposals (AUROC 0.70–0.84). The measurements that fit this: agreement tracks the P ≥ 0.90 share and the proposal-correct rate,
  and the only promoting run had P ≥ 0.90 for every Stage 1 item. The displayed recommendation at 0.65 agreed at least as often in all 25 runs, and strictly more often in 24 (§3.3). Whether a gate at that threshold would
  have promoted, and with what Stage 2 risk, was not run and cannot be inferred from these data.
- **H2: small training sets and compressed probabilities.** Each promotion decision rested on one model trained on 80 human rows, with 64 for training and 16 for Platt
  calibration under AMP's 80/20 split. The observed probability ranges are compressed. The promoting run's probabilities sat in a narrow band just above 0.90, so all
  items were auto-eligible. That pattern is consistent with a model and calibration fitted on little data. Under the ×0.4 row scaling, no run trained a second model.
- **H3: base rates.** The cumulative-agreement gate interacts with how often the proposal is correct (0.46–0.89 across categories). Categories where proposals are right
  less than 70 % of the time cannot pass by approving everything. Whether that makes the gate conservative in exactly the categories where autonomy would be riskiest
  is plausible from T1/T4 but was not measured as a causal relation.
- **H4: order effects.** The one promotion occurred at one of five stream orders for juice_bottle. The other four juice_bottle orders reached gate agreement of 0.570–0.667.
  Promotion may therefore depend on the order of the first 160 items. Five orders are too few to estimate that probability.
- **Scope of the Stage 2 result.** In the one Stage 2 window, AMP's threshold selected all items, so AMP's autonomy there reflects the proposal accuracy of that window
  (0.829) rather than selective routing. With one window, whether this is typical of AMP's Stage 2 under this policy is unknown.

## 7. Threats to validity

1. **Anomaly-heavy benchmark stream (63.3 %).** Rates depend on prevalence.
2. **Perfect, instantaneous oracle.**
3. **Idealized pipeline latency.** AMP jobs settle between items; one tick = 10 items.
4. **Small AMP training sets** (§6 H2), a direct consequence of the preregistered ×0.4 row scaling on 275–341-item streams.
5. **Single PatchCore seed; validation-to-test normal-score shift** (DATASET_AND_MODEL.md).
6. **AMP's model-acceptance check measures auto-eligibility, not accuracy** (plan §5.2).
7. **Stage 2 probe selection uses a random decision-point id** and is not seeded.
8. **Stream orders:** only 5, and each category is an independent agent, so there are 5 runs per category.
9. **The AMP system under test includes a fix made during this project** (hitl-agent `746a268`). Results apply to that version.
10. **Test-label exposure during E2E:** one E2E console summary exposed proposal accuracy by margin band (amendment v1.1 #5). No frozen value changed.

## 8. Artifacts

- **Plan and record:** `EXPERIMENT_PLAN.md` (with amendments), `DATASET_AND_MODEL.md`, `E2E_REPORT.md` (v1 failure and rerun)
- **Per-decision data:**
  - `results/runs/<run_id>/{manifest.json, amp_decisions.csv/.jsonl, amp_events.jsonl, amp_rlhf_events.jsonl}` (27 dirs, including the 2 aborted attempts)
  - `results/baselines/{oracle,model_only,static_hitl}.csv`
  - `results/aggregate/all_decisions_D.csv`
- **Aggregates:** `results/aggregate/{per_run_metrics, T2_per_seed, T3_per_run, T5_per_run, stage1_agreement_analysis, stage1_gate_history, stage1plus_discrimination}.csv`
- **Tables:** `results/tables/T1–T5` (`.csv`, `.md`, `.tex`)
- **Figures:** `results/figures/F1_risk_coverage.{png,pdf}`, `F1b_stage2_window.{png,pdf}`
- **Operations record:** `results/ops/` (worker-stop snapshots and policy backups)
