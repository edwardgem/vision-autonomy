# TARGET_MODEL_REVIEW.md — "Learn → Qualify → Authorize → Monitor → Requalify" vs current AMP and Experiments 1–2

Status: review only (2026-09-24). No AMP change is proposed for implementation here, and Experiment 3 is not designed.
Code references are to the AMP versions used in Experiment 2 (amp-backend `ad5e7e8`, rlhf `2d3356e`, hitl-agent `746a268`).

---

## 1. Verdict in brief

- **The four lessons are supported by Experiments 1–2.** I agree with them, and I would sharpen two of them (§2.2, §2.3).
- **The lifecycle is the right shape.** AMP already has a recognisable version of every phase, but three phases are incomplete in ways the experiments exposed:
  - **Qualify** measures the wrong quantity.
  - **Monitor** has no consequences.
  - **Requalify** is broken by carried-over state.
- **Two parts of the proposal need changing before they drive Experiment 3:**
  - **(a)** the success criterion against static HITL must be defined as *matched information and matched risk budget*, not matched coverage chosen in hindsight;
  - **(b)** on a stationary benchmark with only score-derived features, progressive autonomy can at best *match* a well-chosen static threshold at the per-decision level. Its distinctive value is governance over time: qualification, withdrawal and requalification. That value only becomes visible under change (§3).
- **Most of the required engineering is in rlhf and the policy schema.** Roughly 10 changes are needed (§5). The largest are:
  1. a selective-risk qualification gate;
  2. action-class authorization;
  3. monitoring with consequences;
  4. model-scoped evidence on requalification.

## 2. The four lessons: agreement, with refinements

### 2.1 Authority qualification ≠ action authorization: agree (AMP already embodies it)

- **What the experiments showed.** Experiment 2 was a direct test of this lesson. Qualification (the Stage 1 → 2 gates) changed from 1/25 to 9/25 runs, while per-decision authorization stayed at P ≥ 0.90. In 8 of 9 windows only 20–49 % of items were executed autonomously.
- **Where AMP stands.**
  - The split already exists: the stage is agent-level authority, and `RLHFDecisionService.decide` applies the per-decision threshold, hard criteria and probes.
  - What is missing is the *content* of per-decision authorization: it is one probability threshold for every action (§2.3).
- **One disagreement: "rejection" as an autonomous outcome.**
  - In our design, AMP's "reject" means "the proposal is wrong". An autonomous reject therefore makes AMP overrule the perception model, i.e. act as a second classifier. That is why auto-reject was disabled.
  - For the target model, **autonomous rejection must be defined as declining to execute and taking a policy-defined safe fallback**, for example *quarantine the part* or *route to deferred review*. It should never mean substituting AMP's own judgement.
  - AMP currently returns `auto_decision: reject` with no fallback semantics (`RLHFDecisionService.ts`, binary branch).

### 2.2 High confidence ≠ useful discrimination: agree, but discrimination is also not the right target

- **What the experiments showed.** In juice_bottle s4 the first model scored every item ≥ 0.917, so the threshold filtered nothing. Autonomous error was 0.18 ≈ model-only (RESULTS-2 §4.3).
- **Refinement.** What authorization needs is not discrimination in general (AUROC) but **low error in the slice that would actually be authorized**:
  - the *selective risk* at the action's threshold, with a confidence bound, on data the model was not trained on, and with a minimum slice size;
  - a model can have a good AUROC and still a bad top slice, or the reverse.
- **Proposal.** Qualification should use an **upper confidence bound on the authorized-slice error rate**, with AUROC or probability spread as a diagnostic. That criterion is also the one that can be compared directly with a static-threshold baseline.
- **How AMP measures today (none of these is selective risk):**
  - *Model acceptance (EVAL):* the change in auto-eligible rate, which rewards models that authorize *more*, not models that are more correct (`EvalActivateHandlers.ts`, `upgrade_min_auto_rate_gain`).
  - *Stage 1 gates:* agreement between recommendation and human, which mixes the approve and reject slices (Experiment 1).
  - *Sample gate:* a row count, not a statistical bound.

### 2.3 Risk is action-dependent: agree, with a caution on cost assumptions

- **What the experiments showed.** Experiment 2 displayed the asymmetry without our designing it.
  - Outside one run, AMP's autonomy was 430 "defective" confirmations and 1 "release as good". [Erratum 2026-09-25: 336, not 430; see the RESULTS-2.md erratum. The conclusion is unchanged.]
  - In the anomalous run, 22 of 55 auto-released parts were defective.
  - In inspection, releasing a defective part (FA) and scrapping a good one (FR) have very different consequences.
- **Where AMP stands.** It has one `auto_execute_threshold` per agent. Action-specific control exists only indirectly: a hard criterion can block autonomy for some actions, and the model can learn an action feature.
- **Caution.** LOCO provides no costs. Any cost ratio (e.g. FA = 10 × FR) is an assumption. To keep results from depending on an arbitrary choice:
  - pre-specify it;
  - report the full risk frontier;
  - run a sensitivity analysis over the ratio.
- **Prefer per-action risk budgets** (a maximum autonomous error rate per action class) over a single scalar cost. They are easier to justify and to govern.

### 2.4 Closed evidence loop: agree; this is where AMP is weakest

| Loop element | AMP today | Gap exposed |
|---|---|---|
| Human decisions → learning | Yes (outcomes, feedback, reward weights, retraining) | Human labels assumed correct; the oracle was perfect in both experiments, so the effect of reviewer error is untested |
| Operational outcomes of **autonomous** decisions | Feedback accepted and reward-weighted, but auto rows are **excluded** from the training dataset and not used by any gate | Deterioration discovered after autonomous execution changes nothing |
| Probes | 10 % sampling plus a per-UTC-day minimum | **No consequence** (ISSUE-5). The 1/16 probe signal in juice_bottle s4 was too weak anyway |
| Deterioration → reduce authority | Kill switch (manual); rollback check on *zero* autonomous decisions (a utility signal, not a safety one); drift flag only for Stage 0 rows at Stage ≥ 1 | No demotion or threshold-raising on rising error |
| Model change → requalify | New model re-enters Stage 1 (invariant) | Old promotion flag and cumulative counters carried over, so the new model can never be re-promoted (ISSUE-1). Re-entry happened in 6/9 Experiment 2 windows |

## 3. Where I disagree or would reframe

1. **Stationarity limits what progressive autonomy can win.**
   - AMP's reliability model sees the proposal and two score transforms. That is the same information a static margin threshold uses, fitted per deployment.
   - On an i.i.d. stream, a well-chosen static threshold is close to optimal, so per-decision risk–coverage can at best tie. Experiment 2 was consistent with that: 8 of 9 windows sat on the static curve.
   - The target model's distinctive claims (Monitor, Requalify, withdrawal) only produce measurable value when **reliability changes**: distribution shift, a new product variant, a model update, drift.
   - **Recommendation:** Experiment 3 should include a controlled change. MVTec AD 2 or an induced shift, which was already the stretch goal, is where the lifecycle can show what static HITL cannot.
2. **The comparison needs matched information, not matched hindsight.**
   - Experiments 1–2 compared against static HITL at AMP's *realized* coverage. That is fair as a diagnostic, but static HITL got to know the coverage after the fact.
   - "Matched operating conditions" should mean the static threshold is chosen from the **same evidence AMP had at the same time**: the same early human-labelled rows, the same risk budget. Both are then evaluated on the same subsequent items.
   - Otherwise static HITL is either unfairly strong (hindsight) or unfairly weak (an arbitrary δ).
3. **"Increase correct autonomous work and reduce human burden" needs a declared trade-off rule.**
   - The three dimensions (useful autonomy, autonomous risk, human burden) are right, but a single winner requires a rule.
   - I recommend **maximizing correct autonomous decisions subject to an autonomous-risk budget per action class**, reporting human burden alongside. That is the constrained form used in selective prediction.
4. **Authority scope should be per action class, not per agent.**
   - The lesson "the agent may operate at a stage, each action separately authorized" suggests AMP's authority is really a *vector*. For example: authorized to auto-confirm "defective", not authorized to auto-release "good".
   - A single agent-level stage cannot express that. Experiment 2's emergent behaviour approximated it only through the model's probabilities.
5. **Human reviewers are not an oracle in deployment.** The target model says "human decisions establish initial evidence". With imperfect reviewers, qualification and monitoring must tolerate label noise. At minimum the paper should state that the oracle is an idealisation, or a future experiment should add reviewer noise.

## 4. Mapping the lifecycle to AMP

| Phase | AMP support today | Missing (conceptual) |
|---|---|---|
| **Learn** | Stage 0 human collection; outcome feedback with reward weights; logistic model + Platt; retrain on buffers; audit | Held-out evaluation separate from training rows (EVAL uses the same window); use of verified autonomous outcomes for *monitoring* (not training, to avoid selection bias); reviewer-noise handling |
| **Qualify** | Sample, agreement, stability and safety gates; admin approval workitem; model-acceptance check | Selective-risk bound on the would-be-authorized slice; minimum slice size; discrimination diagnostic; per-action qualification; statistical rather than count thresholds |
| **Authorize** | Per-decision threshold; hard criteria block; probes; deterministic base rules; (binary/3-class) auto-reject | Action classes with their own thresholds and risk budgets; fallback semantics for declined execution; per-action authority scope |
| **Monitor** | Probes; zero-autonomy rollback check; routing-drift flag; outcome feedback; RLHF status/observability | Probe/outcome error estimates per action class with sequential bounds; consequences (alert → raise threshold → revoke action scope → demote); probe cadence independent of wall-clock days |
| **Requalify** | New model → Stage 1 (invariant); kill switch; manual "clear training data" | Evidence scoped to the model version (reset promotion state on activation); acceptance of a new model on held-out selective risk, not auto-rate gain; explicit partial withdrawal |

## 5. Engineering changes required to implement the model faithfully

Ordered by dependency. Sizes are rough. "Params" means new `autonomy_ops` fields: catalog entry, pass-through to RLHF params, defaults that preserve today's behaviour (the pattern used for `stage1_agreement_basis`).

| # | Change | Where | Size |
|---|---|---|---|
| 0 | **Merge the prerequisites**: hitl-agent `normalizePolicy` fix (ISSUE-3) and the `stage1_agreement_basis` parameter | hitl-agent, amp-backend, rlhf | done on branches; merge + deploy |
| 1 | **Model-scoped Stage 1 evidence (ISSUE-1).** On activation into Stage 1, clear `stage1_promotion_*` and the cumulative agreement keys (and future qualification stats); tag stats with `model_version` | `EvalActivateHandlers.ts` (ACTIVATE), `StageTickHandler.ts` | S |
| 2 | **Selective-risk qualification gate.** On Stage 1 human rows scored by the *current* model: error rate among rows with P ≥ the action's execution threshold, its upper confidence bound (Wilson/Clopper–Pearson), and the slice size. Gate: UCB ≤ `max_autonomous_risk` and slice ≥ `min_authorized_rows`; AUROC/spread reported as a diagnostic (and optionally gated) | New `ApprovalRepo` query; `StageTickHandler.scheduleFollowUps`; params; UI gate display | M |
| 3 | **Model acceptance on held-out selective risk.** Replace or augment `upgrade_min_auto_rate_gain` with selective risk and discrimination on rows not used for training (carry the train/test split IDs from TRAIN to EVAL) | `ExtractTrainHandlers.ts`, `EvalActivateHandlers.ts`, `train_baseline.ts` | M |
| 4 | **Action classes in policy.** `authorization.action_classes: {key_field, classes: {<value>: {auto_execute_threshold, max_autonomous_risk, min_authorized_rows, fallback}}}`, e.g. keyed on `proposal`. Unknown class → HITL | policy schema (TS + backend validator + catalog/UI), `RLHFDecisionService.decide` | M |
| 5 | **Per-action authority scope in stage state.** Stage 2 holds a set of authorized action classes (qualified separately via #2); decide() authorizes only within scope | `stage_state_store` / `rlhf_agent_state.metadata`, `StageTickHandler`, promotion workitem payload (admin approves per class) | M–L |
| 6 | **Declined-execution semantics.** Replace binary "auto-reject" with `fallback` per class (`hitl` default; or an agent-defined safe action such as `quarantine`), returned to the agent explicitly; never "flip the proposal" | `RLHFDecisionService`, hitl-agent callback payload, SDK docs | S–M |
| 7 | **Monitoring with consequences.** Per class in Stage 2: probe outcomes plus verified autonomous-outcome feedback → error estimate with a sequential bound. Graduated responses: alert → raise class threshold → revoke class scope → demote to Stage 1, each audited and admin-visible. Probe cadence by decision count, not UTC day | `StageTickHandler`, `ApprovalRepo`, new event types, observability | L |
| 8 | **Requalification rules.** Material change (new model, policy change, detected drift) → affected classes return to qualification with fresh evidence (uses #1, #2, #5) | `EvalActivateHandlers`, policy approval path | M |
| 9 | **Metrics and observability for the three dimensions** (correct autonomous decisions, autonomous risk by class/FA-FR, human burden), per stage and model version | `ObservabilityService`, RLHF status API, frontend | M |
| 10 | **Experiment tooling (not product).** Seedable probe selection for reproducible studies (today it hashes a random decision-point id); a simulator hook to inject distribution shift | rlhf (behind a test/sim flag), vision-autonomy simulator | S |

**Not required, and I'd avoid:**
- a new classifier inside AMP;
- cost-weighted end-to-end optimisation;
- replacing logistic regression.

The research contribution is the governance lifecycle, not the reliability model.

## 6. Risks and open questions before Experiment 3

1. **Too many changes at once lose attribution.** Experiment 3 should either test the full lifecycle against static HITL (a system-level claim), or ablate one capability at a time. Decide which before implementing.
2. **Small evidence budgets.** With 275–341 items per category and ~80 rows per phase, selective-risk bounds will be wide. Qualification may rarely pass unless streams are longer (pool seeds, or larger datasets such as VisA).
3. **The cost/risk budgets are assumptions.** Pre-register them and show sensitivity.
4. **Engineering changes #1–#7 alter AMP for all tenants.** Ship them behind opt-in parameters with defaults preserving today's behaviour, as with `stage1_agreement_basis`, and treat the change as its own AMP release.
