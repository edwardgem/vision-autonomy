# RESULTS-2.md — Experiment 2: Stage 1 qualification semantics (follow-up to Experiment 1)

Experiment `vision-loco-exp2-v1`, preregistered in `EXPERIMENT_PLAN_2.md` (tag `prereg-exp2-v1`, commit `c2c005b`). Runs executed 2026-09-24.
**Experiment 1 (`RESULTS.md`) remains the primary experiment.** This is a hypothesis-driven, paired follow-up on the same data.
Sections are ordered as follows:
- **§1–3:** preregistered observations (§2 is the primary endpoint).
- **§4:** exploratory analyses, not preregistered and labelled as such.
- **§5:** interpretation.
- **§6:** discussion hypotheses.

**Purpose.** Experiment 1 found that AMP's two Stage 1 promotion gates used different recommendation semantics:
- the cumulative gate compared human decisions with a recommendation at the Stage 2 execution threshold (P ≥ 0.90);
- the recent-20 gate compared them with the Stage 1 recommendation (P ≥ 0.65).

Experiment 2 made the cumulative gate use the Stage 1 recommendation too (`promotion.stage1_agreement_basis = recommendation`). **Every individual autonomous
decision still required P ≥ 0.90.** Everything else was identical to Experiment 1.

> **Erratum (2026-09-25):** In §4.2, the number of autonomous "defective" proposals outside juice_bottle s4 was previously reported as
> 430. Recalculation from the raw decision records gives **336** (3 wrong). The earlier value was a transcription error in the hand-written
> §4.2 table: the per-cell file committed with this document (`results/exp2/aggregate/autonomous_by_proposal_exploratory.csv`) was already
> correct, so no analysis code is affected. This correction affects the exploratory action-class count only. It does not change the
> preregistered primary endpoint, promotion results, or the Experiment 2 interpretation: 336 of the 337 autonomous executions in those 8 runs
> were "defective" confirmations, so "almost entirely" still holds.
> *(Evidence: the 25 raw `results/exp2/runs/*/amp_decisions.csv` files (7,840 rows) give, excluding juice_bottle s4, 337 autonomous
> decisions = 336 `defective` proposals (3 with ground truth good) + 1 `good` proposal (ground truth defective). juice_bottle s4 gives 99 (6) and
> 55 (22); all 9 runs give 435 (9) and 56 (23), with Σk = 491 as in §2. The static matched-coverage row, 421 (4) and 70 (21), is unchanged.
> The original §4.2 table is left as written, with a pointer to this erratum.)*

---

## 1. What was executed

| Item | As executed |
|---|---|
| Runs | **25/25 cells** (5 categories × stream seeds 0–4), each on a fresh agent `vis-loco2-{category}-s{seed}`. All exit code 0; no aborts, re-runs or fallbacks; 2.4 h total |
| System | amp-backend `ad5e7e8`, rlhf `2d3356e`, hitl-agent `746a268` (preregistered implementation). Basis `recommendation` in every run's AMP params; training seed `vision-loco-v1`; testing mode off |
| Frozen inputs | Every manifest carries the preregistered hashes (policy `6b573506…`, experiment config `d755b694…`, decision records `eb24ae6b…`, calibration `a33653b2…`). No code or config change after `prereg-exp2-v1` |
| Integrity | Items sent = requests in AMP = requests in AMP's tick statistics (all 25). 0 auto-rejects. 0 failed RLHF jobs. 0 autonomous decisions with P < 0.90 (min 0.9003), and 0 non-probe human items with P ≥ 0.90 (the Stage 2 threshold held). 15 informational "P exactly 0/1" flags (sigmoid saturation at extreme margins, as in Experiment 1) |
| Worker cleanup | Declared in the plan: each agent's worker was stopped after its run (25/25 verified: config disabled, state unchanged, only `rlhf_enabled` changed). Stored policies of these agents therefore read `rlhf_enabled: false` |
| Pairing | **Determinism vs Experiment 1: 25/25 cells**, streams identical, **4,638 Stage ≥1 probabilities compared before the first stage divergence, max \|ΔP\| = 0**, no score-presence mismatch. Experiment 1 and 2 are therefore exactly paired up to the point where the Experiment 2 gate promotes. After promotion, trajectories also differ through unseeded probe selection (plan §10.6) |

## 2. Primary endpoint (preregistered, EXPERIMENT_PLAN_2.md §7)

**Definitions.**
- **Window:** a run's Stage 2 items, from its first Stage 2 decision until its first re-entry to Stage 1.
- **k:** the number of AMP autonomous decisions in the window.
- **Comparison:** static HITL at matched coverage executes the k window items with the largest margin.
- **Pooling and interval:** errors pooled over runs; 95 % percentile bootstrap resampling runs (10,000 resamples, seed 2026).

| Runs reaching Stage 2 | Σk | AMP autonomous errors | Static (matched) errors | r_AMP | r_static | **Δ = r_AMP − r_static** | **95 % CI** |
|---|---|---|---|---|---|---|---|
| 9 | 491 | 32 | 25 | 0.065 | 0.051 | **+0.014** | **[−0.019, +0.038]** |

**Pre-declared reading: _inconclusive_.**
- *Consistent* requires Δ ≤ 0 and an upper bound below +0.05; Δ is positive.
- *Contradicts* requires a lower bound above 0; the CI includes 0.

This is a descriptive reading rule with a run-level interval, not a powered non-inferiority test. Escaped defects among autonomous decisions:
AMP 23/491 (0.047) vs static 21/491 (0.043).

Per run (`results/exp2/aggregate/primary_endpoint_per_run.csv`):

| Run | Window items | Re-entry at | k | Coverage | AMP errors | Static errors | Proposal error in window (model only) |
|---|---|---|---|---|---|---|---|
| breakfast_box s0 | 110 | 271 | 24 | 0.22 | 0 | 0 | 0.209 |
| breakfast_box s2 | 110 | 271 | 26 | 0.24 | 0 | 1 | 0.173 |
| breakfast_box s3 | 100 | 261 | 20 | 0.20 | 0 | 0 | 0.190 |
| juice_bottle s0 | 140 | 301 | 53 | 0.38 | 1 | 0 | 0.121 |
| juice_bottle s1 | 140 | 301 | 59 | 0.42 | 0 | 0 | 0.150 |
| juice_bottle s2 | 130 | 291 | 45 | 0.35 | 0 | 0 | 0.131 |
| juice_bottle s3 | 170 | — | 84 | 0.49 | 2 | 2 | 0.147 |
| **juice_bottle s4** | 170 | — | **154** | **0.91** | **28** | **19** | 0.171 |
| splicing_connectors s0 | 152 | — | 26 | 0.17 | 1 | 3 | 0.336 |

**The pooled estimate is dominated by one run.** juice_bottle s4 contributes 154 of 491 autonomous decisions (31 %) and 28 of AMP's 32 errors.
It is also the only cell that reached Stage 2 in **both** experiments, so its promotion is not attributable to the Experiment 2 change (§4.1).

## 3. Secondary observations (preregistered, descriptive)

### 3.1 Promotion (T3)

| Category | Exp 1 reached Stage 2 | **Exp 2 reached Stage 2** | Exp 2 re-entries to Stage 1 | Exp 2 candidates trained |
|---|---|---|---|---|
| breakfast_box | 0/5 | **3/5** | 3 | 8 |
| juice_bottle | 1/5 | **5/5** | 3 | 9 |
| pushpins | 0/5 | 0/5 | 0 | 5 |
| screw_bag | 0/5 | 0/5 | 0 | 5 |
| splicing_connectors | 0/5 | **1/5** | 0 | 6 |
| **Total** | **1/25** | **9/25** | **6** | 33 |

- Every cell that promoted in Experiment 1 also promoted in Experiment 2. No cell promoted only in Experiment 1.
- **All 9 promotions happened at stream position 161**, the first tick at which the 80-row sample gate can be met, and all four gates passed at that first eligible tick.
- **In all 16 non-promoting runs, the cumulative gate (≥ 0.70) failed at every tick** (26–42 eligible ticks per run), while the stability gate passed at 7–29 of them.
- **Cumulative agreement (recommendation basis), recomputed from the records**, equals AMP's stored value in all 25 runs (`results/exp2/aggregate/stage1_cumulative_agreement.csv`):
  - promoted runs, at the first eligible tick: **0.709–0.911**;
  - non-promoted runs, the highest value reached at any point: **0.551–0.683**.
  - For contrast, on the same Stage 1 rows (items 81–160, identical in both experiments), the Experiment 1 execution-threshold basis gave 0.418–0.861. It was ≥ 0.70 only for juice_bottle s4.
- As disclosed in the plan (§6), which cells would clear 0.70 was largely inferable from Experiment 1 data. Promotion frequency is therefore descriptive, not confirmatory.
- **No run was rolled back or auto-disabled.**

### 3.2 Stage 2 windows, re-entry, probes

- **Size:** 9 windows, 1,222 Stage 2 items.
- **Routing:** 491 autonomous (0.402). Of the 731 sent to a human, 654 were below 0.90 and 77 were probes.
- **Re-entry: 6 of 9 runs re-entered Stage 1** (breakfast_box s0, s2, s3 and juice_bottle s0, s1, s2), at positions 261–301, after 100–140 Stage 2 items.
  - **Sequence (all 6):** Stage 2 human rows reached 80 → retrain → the candidate passed the model-acceptance check → approved (D3) → activated → Stage 1.
  - **After re-entry, no run returned to Stage 2** in the remaining 5–40 items. That is consistent with F4 (the retained `stage1_promotion_approved` flag), but non-re-promotion was not directly testable: 80 Stage 1 rows were never available after re-entry.
  - **So the autonomy AMP granted was temporary in 6 of 9 runs.**
- **Probes:** the oracle rejected 1 of 77 (1 of 16 in juice_bottle s4, where the autonomous error rate was 0.18; 0 in the other windows).

### 3.3 Full stream (T2)

| Condition | Accuracy | FA rate | FR rate | Autonomous rate | HITL rate | Autonomous error rate |
|---|---|---|---|---|---|---|
| A Human oracle | 1.000 | 0.000 | 0.000 | 0.000 | 1.000 | — |
| B Model only | 0.680 | 0.477 | 0.049 | 1.000 | 0.000 | 0.320 |
| C Static HITL (δ = 1σ) | 0.788 | 0.329 | 0.010 | 0.761 | 0.239 | 0.279 |
| D1 AMP, Experiment 1 (5 seeds) | 0.997 ± 0.007 | 0.004 ± 0.009 | 0.002 ± 0.004 | 0.019 ± 0.042 | 0.981 ± 0.042 | 0.168 (1 seed) |
| **D2 AMP, Experiment 2 (5 seeds)** | **0.996 ± 0.008** | 0.005 ± 0.010 | 0.003 ± 0.004 | **0.063 ± 0.024** | **0.937 ± 0.024** | 0.044 ± 0.078 |

**D2's ≈ 99.6 % final accuracy reflects ≈ 94 % human review.**
- Across 7,840 decisions, 491 (6.3 %) were autonomous, and all 32 errors (23 FA, 9 FR) occurred among them.
- By seed: seeds 0–3 had 2, 0, 0 and 2 errors; seed 4 had 28, all from juice_bottle s4.
- Autonomy rose from 1.9 % (Experiment 1) to 6.3 %. Static HITL (δ = 1σ) remains a very different operating point: 76 % autonomy, 27.9 % autonomous error rate.

### 3.4 By anomaly type (T4)

D2 autonomous decisions by ground-truth type (pooled counts):

| Type | Autonomous | Errors |
|---|---|---|
| logical | 261 | 16 (FA) |
| structural | 188 | 7 (FA) |
| good | 42 | 9 (FR: good images proposed defective) |

- Autonomous rate (seed mean): logical 0.093, structural 0.087, good 0.015.
- The per-seed autonomous error rate for good images (0.718 ± 0.489) rests on 3 seeds with any such decisions and very small counts. It is not interpretable as a rate.

### 3.5 Stage 2 windows, all conditions on the same items (T5, pooled)

| Condition | Autonomous | Coverage | Autonomous errors | Autonomous error rate [Wilson 95 %] | Autonomous FA | Window accuracy |
|---|---|---|---|---|---|---|
| **AMP (D2)** | 491 | 0.402 | 32 | 0.065 [0.047, 0.091] | 23 | 0.974 |
| Static HITL, matched coverage | 491 | 0.402 | 25 | 0.051 [0.035, 0.074] | 21 | 0.980 |
| Static HITL, δ = 1σ | 955 | 0.782 | 131 | 0.137 [0.117, 0.160] | 124 | 0.893 |
| Model only | 1,222 | 1.000 | 221 | 0.181 [0.160, 0.203] | 193 | 0.819 |

Wilson intervals treat items as independent and are descriptive; the run-level interval is the one in §2.

### 3.6 Figures

- **`results/exp2/figures/F1_risk_coverage_exp2.*`:** risk–coverage per category and pooled, with the static sweep, D1 points and D2 points. Each panel states how many seeds made any autonomous decision.
- **`F1b_stage2_window_exp2.*`:** Stage 2 windows per seed.
  - **Seeds 0–3:** D2 lies on or slightly below the static sweep, at 20–50 % coverage.
  - **Seed 4 (juice_bottle s4 only):** D2 lies above the sweep at 91 % coverage, next to Experiment 1's point for the same window.

## 4. Exploratory analyses (NOT preregistered; they do not change the §2 reading)

### 4.1 Heterogeneity: the one non-attributable window versus the rest

- **Excluding juice_bottle s4:** 8 runs, Σk = 337, AMP 4 errors against 6 for static (matched), Δ = −0.006, run-bootstrap CI [−0.026, +0.006].
- **These 8 runs are exactly the promotions attributable to the Experiment 2 change;** they did not promote in Experiment 1.
- This split was chosen after seeing the results. It is reported to show where the pooled estimate comes from, not as a result.

### 4.2 Which proposals AMP executed autonomously

| | Autonomous "defective" proposals (errors) | Autonomous "good" proposals, i.e. released parts (errors = escaped defects) |
|---|---|---|
| AMP, 8 runs excl. juice_bottle s4 | 430 (3) [**erratum: 336 (3)**, see top] | **1 (1)** |
| AMP, juice_bottle s4 | 99 (6) | **55 (22)** |
| Static matched, all 9 runs | 421 (4) | 70 (21) |

- **Outside juice_bottle s4, AMP's autonomy consisted almost entirely of confirming "defective" proposals.** Every "release as good" decision except one went to a human.
- **In juice_bottle s4, AMP autonomously released 55 parts, 22 of them defective (40 %).**

### 4.3 What distinguishes juice_bottle s4 (descriptive; `results/exp2/aggregate/first_model_exploratory.csv`)

- **Training data:** its first AMP model was trained on the first 80 items of its stream, where **96 % of proposals were correct**. The other runs ranged 41–90 %; the other juice_bottle seeds ranged 81–90 %.
- **Model weights:** the fitted weights on `margin_abs` (0.27) and `score_z` (0.29) were the smallest of the 9 promoted runs (the other 8: 0.34–1.13 and 0.58–1.02).
- **Resulting probabilities:** all at or above 0.917 in both Stage 1 and Stage 2. The 0.90 execution threshold therefore selected every item, and AMP's autonomous error (0.182) ≈ the window's model-only error (0.171).
- **In the other 8 windows, 22–55 % of items had P ≥ 0.90,** and AMP's autonomous error was 0–4 %.
- **No retrain was accepted in this run,** so the first model governed the whole window.

## 5. Interpretation (limited to the endpoints)

1. **The primary question is not settled by this experiment.** At equal coverage on the same items, AMP's Stage 2 autonomous error rate was not shown to be lower, higher, or equivalent to a static confidence threshold's (Δ = +0.014, CI [−0.019, +0.038], *inconclusive* by the pre-declared rule).
2. **Changing only the Stage 1 qualification semantics changed promotion as expected, without lowering the per-decision standard.** Promotion rose from 1/25 to 9/25 runs, and all autonomous decisions still met P ≥ 0.90. The Stage 0/1 paths were identical to Experiment 1's, so promotion differences are attributable to the gate change.
3. **Final accuracy remains a measure of human review, not of AMP's decision quality.** Human review was 93.7 % (Experiment 2) vs 98.1 % (Experiment 1).
4. **Stage 2 behaviour was heterogeneous, and the heterogeneity is visible in the data.**
   - In 8 of 9 windows, AMP granted autonomy selectively (20–49 % coverage) at low error.
   - In one window, its probabilities never fell below the threshold, so it granted almost blanket autonomy at near model-only error, including releasing defective parts.
   - Whether AMP's selective behaviour is *better* than static HITL cannot be concluded from 9 windows (§4.1 is exploratory).
5. **Controlled autonomy was usually short-lived** under AMP's own lifecycle: 6 of 9 windows ended with a Stage 2 retrain and re-entry to Stage 1, and none resumed Stage 2.

## 6. Discussion: possible explanations (not established here)

- **E1 (small-sample first model).** A model trained on 80 rows, 20 % of them held out for calibration, can become nearly uninformative when the early sample is unrepresentative (juice_bottle s4: 96 % correct proposals). The execution threshold alone cannot detect that. **Candidate test:** a minimum-discrimination requirement for promotion, such as AUROC or probability spread on Stage 1 rows, preregistered.
- **E2 (asymmetric learned trust).** PatchCore's proposals miss many defects (FA 47.7 %), so "good" proposals are less often correct than "defective" ones. AMP's model assigned high P mainly to defective proposals, so autonomy became "auto-reject parts" rather than "auto-release parts". This is plausibly a sensible property for inspection, but it is inferred, not tested.
- **E3 (probe power).** At a 10 % probe rate, 16 probes could not reveal an 18 % autonomous error rate: 1/16 were rejected, which is within sampling variation. AMP also has no mechanism acting on probe disagreement.
- **E4 (lifecycle).** Re-entry after retrain, combined with AMP ISSUE-1 (retained promotion flag), makes Stage 2 temporary. Whether re-promotion would occur after a fix is untested.
- **E5 (path dependence).** Promotion happened at the first eligible tick or never. The first 80 Stage 1 rows effectively decided each run.

## 7. Threats to validity (in addition to Experiment 1 §7 and plan §10)

1. **Nine windows, one of them dominant.** Run-level uncertainty is large.
2. **Paired but not independent.** The same images and stream orders as Experiment 1 were used, and promotion was predictable from Experiment 1 data (disclosed in advance).
3. **Post-promotion trajectories include chance.** Unseeded probes feed retrain data, and that affects retrain acceptance and re-entry.
4. **The window definition** ends at re-entry (pre-declared), so windows range from 100 to 170 items.
5. **The system under test was modified by the one preregistered parameter** (amp-backend `ad5e7e8`, rlhf `2d3356e`).

## 8. Artifacts

- **Runs:** `results/exp2/runs/<run_id>/…` (25 runs), `results/exp2/runs/study_log.jsonl`, and the worker-stop records in `results/exp2/ops/`.
- **Primary endpoint:** `results/exp2/primary_endpoint.json`, `results/exp2/aggregate/primary_endpoint_per_run.csv`.
- **Aggregates:** `results/exp2/aggregate/{paired_cells, determinism_per_cell, gate_history, stage1_cumulative_agreement, T2_per_seed_D1, T2_per_seed_D2, all_decisions_D2}.csv`.
  - Exploratory: `autonomous_by_proposal_exploratory.csv`, `first_model_exploratory.csv`.
- **Tables:** `results/exp2/tables/` (T2–T5, `.csv/.md/.tex`). T1 is unchanged from Experiment 1.
- **Figures:** `results/exp2/figures/`.
- **Plan and record:** `EXPERIMENT_PLAN_2.md` (incl. the E2E acceptance record), `AMP_ISSUES.md`.
