# EXPERIMENT_PLAN.md — Vision progressive autonomy on MVTec LOCO AD

Status: **APPROVED by Edward 2026-09-23 (pre-registered). Nothing in this plan has been tuned on test labels.** Once approved, this
file plus `config/calibration_v1.json`, `config/amp_policy_v1.json` and `config/experiment_v1.json` are committed.
That commit hash is the pre-registration point, and every run manifest records it. Any later change is a new
version (`*_v2`) with a stated reason, and v1 results are still reported.

## 1. Research question and scope

> Can validated human decisions and model performance be used to progressively grant decision authority to a
> vision-based agent while maintaining policy-governed human oversight?

- **Perception (fixed):** PatchCore, seed 0, frozen raw scores in `results/patchcore_scores.csv`. It is never
  retrained or re-seeded, and it never sees human feedback.
- **Proposal:** a deterministic threshold on the PatchCore score gives `good` or `defective` (§3).
- **Governance (AMP):** AMP decides whether that proposal **may execute autonomously** or **must go to human review**.
  AMP's learned model predicts P(human approves the proposal), which here is P(the proposal is correct). It never
  predicts `good`/`defective` itself and cannot flip a proposal (auto-reject is disabled, §5). **AMP is not a second
  anomaly classifier.**
- **Ground truth** is used only as the simulated human oracle and for evaluation. It is never an AMP input.

## 2. Evaluation data and stream construction

- **Data:** the complete LOCO test split, **1,568 images**: 575 good, 561 logical, 432 structural. **993 / 1,568
  (63.3 %) are anomalous.** This is a benchmark evaluation distribution, **not** an assumed production anomaly rate.
  Autonomy rates and error rates depend on this prevalence, and the paper must say so.
- **One AMP agent per category.** An AMP autonomy stage belongs to an (org, agent) pair, and one PatchCore model is
  fitted per category, so each category is an independent inspection station with its own promotion path. This is
  what lets one category fail to promote while another reaches Stage 2.
- **Streams:** for each category, sort test `image_id`s ascending, then order them by
  `numpy.random.default_rng(seed).permutation`. **Stream seeds: 0, 1, 2, 3, 4.** Each seed is a full, independent AMP
  run on fresh agents `vis-loco-{category}-s{seed}` (25 agents). No data is deleted between runs, so the audit trail
  is kept.
- **Seed fallback (decided on wall time, never on results):** if the Component 3 E2E test projects more than 3 h
  per seed, run seeds 0, 1 and 2 only.
- Categories are independent agents, so they run sequentially within a seed.

## 3. Input record passed into the governance experiment

Built once, offline, from frozen scores and frozen calibration: `results/inputs/decision_records.csv` (1,568 rows).

| Field | Definition | Sent to AMP? |
|---|---|---|
| `image_id` | `{category}/test/{type_dir}/{file}` | only as the opaque `resource_id` in context, **not a feature** |
| `category` | LOCO category | no (constant within an agent) |
| `anomaly_type` | good / logical / structural (from the folder name) | **never** (analysis only) |
| `ground_truth` | good / defective | **never** (oracle and evaluation only) |
| `raw_score` | PatchCore image score | no |
| `tau` | category threshold (below) | no |
| `predicted_class` = `proposal` | `defective` if `raw_score >= tau` else `good` | **yes** (categorical) |
| `score_z` | `(raw_score - mu_val) / sigma_val` | **yes** (numeric) |
| `margin_abs` = `model_confidence` | `abs(raw_score - tau) / sigma_val`, distance from the decision threshold in validation-normal SDs | **yes** (numeric) |

**Threshold (decision 1).** `tau_c` is the **0.95 quantile** of the category's validation-normal raw scores (numpy
linear interpolation, n = 54–69 per category). Rationale: validation holds only normal images, so a quantile of
normal is the only label-free choice. 0.95 is the conventional one-class operating point (a nominal 5 % false-alarm
rate on normal parts). 0.99 would essentially be the sample maximum at these n and would be unstable. Values were
computed before any test evaluation (`config/calibration_v1.json`, sha256 `a33653b2…6d95`):

| Category | n val | tau | mu_val | sigma_val |
|---|---|---|---|---|
| breakfast_box | 62 | 43.425 | 41.521 | 1.360 |
| juice_bottle | 54 | 33.780 | 30.488 | 2.242 |
| pushpins | 69 | 43.027 | 38.692 | 2.486 |
| screw_bag | 60 | 51.945 | 48.768 | 2.153 |
| splicing_connectors | 60 | 41.658 | 36.648 | 2.720 |

Known limitation (from Component 1, measured on normal images only): validation-normal and test-normal scores differ
modestly (KS p < 0.05 in 3 of 5 categories), so the realised test false-alarm rate will not be exactly 5 %.

**Why `margin_abs`:** proposals are most often wrong near `tau`, so P(correct) is not monotone in the raw score.
AMP trains a logistic regression, which cannot learn that shape from the raw score alone. With
`{proposal one-hot, score_z, margin_abs}`, a linear model can fit a separate slope for each proposal. This is
agent-side feature engineering, the same pattern as payment-agent's derived signals. AMP is not modified.

## 4. Experimental conditions

All four conditions use the identical 1,568 input records. Conditions A–C are deterministic functions of those
records and are computed offline. Only D needs live AMP.

| | Condition | Who decides | Final decision |
|---|---|---|---|
| A | **Human oracle** | human reviews 100 % | `ground_truth` |
| B | **Model only** | 0 % human | `proposal` |
| C | **Static HITL (selective prediction / deferral)** | human iff `margin_abs < δ` | `ground_truth` if deferred, else `proposal` |
| D | **AMP progressive autonomy** | AMP routing (§5) | `ground_truth` if routed to human, else `proposal` |

**Static HITL is the selective-prediction baseline**, with abstention by a fixed confidence band around the threshold.
- **Pre-registered operating point:** **δ = 1.0** validation-normal SD, chosen without test labels.
- **Full risk–coverage curve:** δ from 0 to 5.0 in steps of 0.05, so AMP's realised operating points can be placed
  on the curve.
- **Coverage-matched comparison:** on exactly the items AMP handled at Stage 2 in each run, static HITL
  auto-executes the same **number** of items, choosing those with the largest `margin_abs`. This is the selective-
  prediction comparison at equal coverage. It is computed after the AMP runs because the coverage comes from AMP, but
  it involves no free parameter, so it cannot be tuned in AMP's favour.

## 5. AMP condition specification (frozen in `config/amp_policy_v1.json`)

### 5.1 Parameter rule

To limit researcher degrees of freedom:
- **Every row-count parameter** is AMP's catalog default × **0.4**, so defaults of 200 become 80 and 50 becomes 20.
  The factor fits Stage 0 (80), Stage 1 (80) and a Stage 2 window into the smallest category stream (275).
- **Every rate or threshold parameter** keeps AMP's shipped default.
- **The only deviations** are the four in §5.3, each required by the semantics of this experiment.

| Parameter (policy location) | Value | AMP default | Why |
|---|---|---|---|
| `automation.min_samples_for_autonomy_change` → `initial_train_min_human_rows` | 80 | 200 | ×0.4 |
| `promotion.stage1_eval_min_human_rows` | 80 | 200 | ×0.4 |
| `promotion.stage1_recent_window_rows` | 20 | 50 | ×0.4 |
| `retrain.retrain_min_human_rows` | 80 | 200 | ×0.4 |
| `upgrade.upgrade_min_eval_human_rows` | 80 | 200 | ×0.4 |
| `promotion.stage1_eval_min_agreement_rate` | 0.70 | 0.70 | default |
| `promotion.stage1_recent_min_agreement_rate` | 0.65 | 0.65 | default |
| `promotion.stage2_promotion_blocking_safety_alerts_7d_max` | 0 | 0 | default |
| `promotion.stage1_eval_max_days` | 5 | 5 | default (informational only; not a promotion gate) |
| `upgrade.upgrade_min_auto_rate_gain` | 0.03 | 0.03 | default |
| `retrain.max_failed_retrain_cycles` | 4 | 4 | default |
| `automation.recommend_threshold` (Stage 1 recommendation) | 0.65 | 0.65 | default |
| `automation.auto_execute_threshold` (Stage 2 autonomy) | **0.90** | 0.90 (backend default) | default |
| `probing.stage2_probe_rate` / `stage2_probe_min_per_day` | 0.1 / 2 | 0.1 / 2 | default |
| `rollback.post_switch_zero_auto_rollback_days` / `cooldown_days` | 2 / 7 | 2 / 7 | default |

### 5.2 How AMP moves between stages (verified in the rlhf/amp-backend source, commits `59fffbd` / `d2a42ca`)

- **Stage 0 (full HITL):** every item goes to a human, and each labelled outcome is stored.
- **Stage 0 → 1:** at the first tick with ≥ 80 Stage 0 human rows, AMP extracts the settled human outcomes and trains
  a binary logistic regression: Adam, L2 = 0.001, 12 epochs, 80/20 split, Platt scaling on the 20 %. EVAL then
  proposes the model if its auto-eligible rate on the human rows rises by ≥ 0.03. Otherwise the candidate is
  `metric_rejected` and AMP retrains after 80 more rows, up to 4 failed cycles. An accepted candidate creates a
  model-approval workitem, which the simulator approves (D3), and ACTIVATE moves the agent to Stage 1.
  *Note for the paper: this EVAL gate measures auto-eligibility, not accuracy; the accuracy gate is the Stage 1 → 2
  agreement check below.*
- **Stage 1 (recommendation only, full HITL):** AMP shows `approve` if p ≥ 0.65, else `reject`, and the human still
  decides every item.
- **Stage 1 → 2:** all four hard gates must pass at a tick:
  1. ≥ 80 Stage 1 human rows;
  2. overall recommendation–oracle agreement ≥ 0.70;
  3. agreement over the last 20 rows ≥ 0.65;
  4. no more than 0 repeated-failure safety alerts in the last 7 days.

  A Stage 2 promotion workitem is then created, the simulator approves it, and the agent enters Stage 2. Stage 1
  agreement here means how often AMP's recommendation matches the oracle's approve/reject of the proposal.
- **Stage 2 (narrow autonomy):** an item is **executed autonomously** iff all of the following hold:
  - no hard criterion is unmet;
  - p(approve proposal) ≥ **0.90**;
  - it is not selected for a probe (10 % hash-based sample plus at least 2 per UTC day).

  Everything else goes to a human. Stage 2 human rows keep training data flowing: at 80 rows AMP retrains, and an
  accepted new model **re-enters Stage 1** (AMP invariant). If 2 consecutive ticks in Stage 2 produce no autonomous
  decisions, AMP triggers a rollback check. All of these are AMP's own mechanisms, and every occurrence is logged
  and reported.

### 5.3 Deliberate deviations from AMP defaults (all required by the experiment's semantics)

1. **Base-policy rules disabled** (`reject_on_hard_fail: false`, `approve_on_all_pass: false`). Both default to on.
   This policy has no business criteria, and `approve_on_all_pass` fires when every criterion passes, so it would
   auto-approve **every** Stage 2 item at confidence 1.0 and bypass the learned model completely. That would make
   condition D equal to model-only.
2. **Auto-reject disabled** (`auto_reject_threshold: 1.01`, so `p <= -0.01` can never happen). A binary AMP model
   otherwise auto-rejects when p ≤ 1 − threshold. Under Option B, auto-rejecting a proposal would mean AMP
   overruling the vision model, which would make AMP a second classifier. **Any auto-reject observed in a run
   invalidates that run**, and the simulator checks for it. Open risk: the TS policy schema does not list this
   field. If AMP rejects or ignores it, Component 3 stops and escalates. The field will not be dropped silently.
3. **One hard criterion only:** `c_perception_output_valid` (`margin_abs >= 0`, fallback `not_met`). This is a real
   governance precondition: without a valid perception output, the item can never be autonomous. It is always met on
   this data, so it contributes a constant feature (which AMP's normalisation handles safely).
4. **Only `approve`/`reject` human decisions**, which keeps AMP in binary label mode (Platt-calibrated). The
   three-class mode is not needed.

### 5.4 Simulated human and lifecycle (reuses the payment-agent `run_e2e.py` API sequence)

Per item: agent init → `POST /api/hitl/request` (action fields as in §3, HITL always requested with no LLM-evaluated
condition) → either an AMP auto route (`rlhf_auto_no_workitem`) or a human workitem → the oracle completes the
workitem → `POST /api/rlhf/outcome` → `POST /api/rlhf/outcome/feedback` → lifecycle state and log.

- **Oracle:** `approve` iff `proposal == ground_truth`, else `reject`. It is deterministic and never wrong. A reject
  means the final decision is `ground_truth`.
- **Outcome feedback:** `succeeded` for every human decision, because the oracle is correct by construction (reward
  +1). Without feedback, outcomes stay pending for AMP's 48 h window and never enter training. Autonomous decisions
  get no feedback: AMP excludes `decision_mode = auto` rows from training anyway, and in this primary experiment
  autonomous errors are not discovered after the fact. That is recorded as a limitation, and the rollback stretch
  goal would test it.
- **Admin workitems** (model approval, Stage 2 promotion) are auto-approved by the simulator (D3).
  `auto_approve_upgrade_proposals` stays false, so each approval appears as an explicit, logged workitem.
- **Ticks and settling:** after every **10 items per agent** the simulator triggers `stage_tick` with
  `tick_minutes = 1440`. AMP starts each tick window at `max(requested start, last_processed_at)`, so a window
  shorter than the real time elapsed would silently drop rows; 1440 prevents that. The simulator then **settles**: it
  waits for the agent's RLHF jobs to finish, approves any admin workitems, and ticks again (up to 6 extra ticks with
  no new items) until nothing new is scheduled.
  - Effect: stage transitions are a deterministic function of stream position, not of worker speed. The paper must
    state this idealisation (zero pipeline latency relative to arrivals).
  - AMP's "days" parameters (`stage1_eval_max_days`, `post_switch_zero_auto_rollback_days`) therefore advance **per
    tick** (1 tick = 10 items).
  - The probe minimum per day uses the real UTC day.

### 5.5 Reproducibility controls and known non-determinism

- The RLHF worker must run with **`RLHF_TRAINING_SEED=vision-loco-v1`**. Otherwise AMP picks a random UUID seed per
  training job. This is an environment setting on the local AMP, not a code change, and needs Edward's go-ahead.
- **Remaining non-determinism:** Stage 2 probe selection hashes the random `decision_point_id`, so which 10 % get
  probed differs between runs. It is recorded per item (`probe_forced_human`), and the stream seeds capture the
  resulting variation.
- **Recorded in every run manifest:**
  - git SHAs of amp-backend, hitl-agent and rlhf, and of this repo (the pre-registration commit);
  - policy file sha256 and calibration sha256;
  - every parameter value, the stream seed and the `RLHF_TRAINING_SEED`;
  - AMP testing-mode flag, Python/package versions and wall-clock timestamps.

## 6. What each run records (per decision, `amp_decisions.csv` and `.jsonl`)

`experiment_id, run_id, condition, stream_seed, stream_position, agent_name, image_id, category, anomaly_type,
ground_truth, raw_score, tau, score_z, margin_abs (model_confidence), proposal, amp_stage (0/1/2), amp_model_version,
amp_approval_probability, amp_recommended_decision (Stage 1), routing (autonomous|hitl), escalation_reason,
probe_forced_human, hard_blocked, oracle_response (approve|reject|n/a), final_decision, correct, false_acceptance,
false_rejection, decision_point_id, workitem_id, instance_id, timestamp`

- **`escalation_reason`:** `stage0_full_hitl` | `stage1_full_hitl` | `stage2_below_auto_threshold` | `stage2_probe` |
  `stage2_hard_blocked` | `rlhf_bypass_or_error`.
- **Run events log (`amp_events.jsonl`):** every tick and its window, job outcomes, candidate trained, EVAL result,
  model-approval and promotion workitems (IDs, time, stream position), stage transitions, retrains, Stage 1
  re-entries, rollback checks, and protocol violations (such as any auto-reject).
- Conditions A–C produce the same per-decision columns, with AMP fields set to `n/a`.

## 7. Metrics

Correctness is `final_decision == ground_truth`. "Defective" is the positive class.

| Metric | Definition |
|---|---|
| Decision accuracy | correct / N |
| False acceptance (FA) | final = good ∧ GT = defective (an escaped defect). Rate = FA / #GT-defective; count also reported |
| False rejection (FR) | final = defective ∧ GT = good. Rate = FR / #GT-good; count also reported |
| Autonomous decision count / rate | autonomous / N |
| HITL count / rate | human-reviewed / N (human workload) |
| Autonomous error rate | errors among autonomous decisions / autonomous count (the risk in selective prediction) |
| Promotion point | stream position of the first Stage 1 decision and the first Stage 2 decision (or "not reached") |
| Stage 2 window metrics | the above, restricted to items AMP handled at Stage 2 |

**Reporting windows:**
- the full stream;
- AMP's Stage 2 window, with every baseline evaluated on the **same items**.

**Breakdowns** (sample size permitting):
- by category;
- by `anomaly_type` (good / structural / logical);
- by AMP stage.

**Uncertainty:** Wilson 95 % CIs within a run; mean ± SD across stream seeds. Rates with n < 10 are shown as counts
only. There are no hypothesis tests beyond descriptive CIs. Each comparison is reported as observed, including
results that go against AMP.

**Guidance on reading the results (fixed in advance, not a claimed result):**
- Final errors in C and D come only from autonomous decisions.
- A category that never reaches Stage 2 is a valid outcome, reported as such, and never re-run with different
  settings.
- AMP's Stage 2 behaviour amounts to a learned confidence band. The comparison against static HITL at equal coverage
  (§4) is the central baseline and is reported whichever way it falls.

## 8. Output tables (`results/tables/`, CSV + Markdown + LaTeX)

- **T1 Dataset and perception:** per category: test counts by type; image-level AUROC (threshold-free) overall,
  logical and structural; `tau`; realised proposal FA/FR at `tau`.
- **T2 Main comparison (full stream):** rows are conditions A–D. Columns: accuracy, FA rate, FR rate, autonomous
  rate, HITL rate, autonomous error rate (mean ± SD across seeds).
- **T3 AMP promotion per category:** Stage 1 and Stage 2 entry positions per seed; number of seeds reaching Stage 2;
  retrains or Stage 1 re-entries; rollbacks; Stage 2 autonomy rate and autonomous error rate.
- **T4 By anomaly type:** A–D × {good, structural, logical}, with FA/FR and autonomy by type. This shows whether AMP
  withholds autonomy where PatchCore is weak (logical).
- **T5 Stage 2 window comparison:** on AMP's Stage 2 items, compare AMP, static δ = 1.0 and static at matched
  coverage, reporting autonomous count, autonomous error rate and FA among autonomous decisions.
- **F1 Risk–coverage figure** (per category and pooled): the static-HITL δ sweep, with the AMP Stage 2 operating
  point for each seed.
- **Machine-readable outputs:**
  - `results/runs/<run_id>/{manifest.json, amp_decisions.csv, amp_decisions.jsonl, amp_events.jsonl}`
  - `results/baselines/{oracle,model_only,static_hitl}.csv`
  - `results/aggregate/*.csv`

## 9. Component 3 acceptance (E2E test before the full run)

On one category with a short synthetic-order stream (not a stream seed used in the study), confirm:
1. every request routes, and oracle decisions and feedback persist;
2. Stage 0 → 1 → 2 transitions happen through AMP's own jobs and workitems;
3. no auto-reject occurs, and `auto_reject_threshold` is honoured;
4. base-policy rules do not fire;
5. `tick_minutes = 1440` drops no rows (tick stats reconcile with items sent);
6. the training seed is honoured;
7. per-item latency is measured, and the §2 seed-fallback rule is applied from it.

**Stop and escalate (switch to a stronger model) if** any of these fail in a way that needs a plan change: Stage 2
unreachable in principle, the `auto_reject_threshold` field rejected, row loss, or settling not converging.

## 10. Threats to validity (for the paper)

1. **Anomaly-heavy benchmark distribution (63 %).**
2. **Perfect, instantaneous oracle.**
3. **Idealised zero pipeline latency.**
4. **Small AMP training sets:** 64 training rows and 16 Platt rows per initial model.
5. **Validation-to-test normal-score shift.**
6. **Single PatchCore seed** (decision 3; deliberate).
7. **Non-square resize** distorts some categories.
8. **AMP's model-acceptance gate measures auto-eligibility, not accuracy** (§5.2).
9. **Probe randomness.**
10. **The row-count scaling (×0.4) is a choice:** it is disclosed, applied uniformly, and fixed in advance.

## 11. Prerequisites (resolved 2026-09-23)

1. AMP target: local AMP, org `O-XXXX-ORG`, reviewer/`who` = `reviewer@example.org` (superadmin). API key is
   kept in the gitignored `vision-autonomy/.env`, never committed.
2. `RLHF_TRAINING_SEED=vision-loco-v1` approved. Env chain: `amp-backend/.env` is sourced by `amp-backend/dev.sh`
   (pm2 `amp`) → Flask backend → the backend spawns scoped `rlhf_worker.js` processes (inheriting env) for each
   enabled pipeline. Set it by adding the line to `amp-backend/.env` and `pm2 restart amp`; verify with
   `ps eww <worker pid>`.
3. Registering 25–30 `vis-loco-*` agents approved.
4. AMP testing mode verified **off**: `AMP_TESTING_MODE` is commented out in `amp-backend/.env` and absent from
   the running worker's environment. `MODEL_MODE=file` in hitl-agent (real learned model, not the stub).
5. Note: scoped RLHF workers exist only for enabled pipelines (at pre-registration time only the payment agent
   had one). Bootstrapping each `vis-loco-*` agent must spawn its worker; the E2E test verifies this.
