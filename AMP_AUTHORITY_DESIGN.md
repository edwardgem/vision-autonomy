# AMP_AUTHORITY_DESIGN.md — Minimum AMP changes before Experiment 3 (engineering design, not implemented)

Status: design for review (2026-09-24). Nothing here is implemented. Experiment 3 is not designed or preregistered (§10 only sketches environments).
Target lifecycle (agreed): **Learn → Qualify → Authorize → Monitor → Requalify**, with per-action authority and risk-constrained autonomy.
Grounding: `TARGET_MODEL_REVIEW.md`, Experiments 1–2, and the AMP code at amp-backend `ad5e7e8`, rlhf `2d3356e`, hitl-agent `746a268`, amp-core (public `DecisionProvider`).

---

## 0. Design principles

1. **Opt-in, default unchanged.** Everything lives under one new policy block, `autonomy_ops.authority` with `enabled: true`. When it is absent or false, today's code paths run unchanged: Stage 0/1/2 gates, the single threshold, auto-reject, probes and rollback. Regression is checked by replaying Experiment 1/2 records (legacy mode must reproduce them exactly).
2. **Authority only tightens automatically; loosening needs evidence plus human approval.**
   - Automatic: revocation, requalification, threshold tightening.
   - Human-approved: authorization and re-authorization. This extends D3 and AMP's existing admin-approval pattern.
3. **AMP never reverses the agent's decision.** Declining autonomy means human review, or a policy-defined safe action. It never means AMP substituting its own classification.
4. **Evidence is prospective and model-scoped.** Qualification and monitoring use only human-labelled decisions made *after* the current model was activated. The model never trained on them, so they are held out by construction.
5. **Public contract preserved.** The `amp-core` `DecisionProvider` outcomes stay `allow | require_human | deny`, and the "may only tighten" invariant holds (§3.4).

## 1. Policy schema (the one opt-in block)

```jsonc
"autonomy_ops": {
  "authority": {
    "enabled": true,                         // master switch; absent/false = legacy behaviour
    "class_key": "proposal",                 // action field that defines the action class (from action_context)
    "confidence": 0.95,                      // one-sided confidence for all bounds below
    "classes": {
      "defective": {                         // e.g. "confirm defect / reject part"
        "autonomy": "eligible",              // eligible | never
        "threshold_mode": "risk_controlled", // fixed | risk_controlled
        "auto_execute_threshold": 0.90,      // used when threshold_mode = fixed
        "threshold_grid": [0.99, 0.98, 0.97, 0.95, 0.93, 0.90, 0.85, 0.80],   // risk_controlled: tested high → low
        "max_autonomous_risk": 0.05,         // risk budget: max error rate among autonomous decisions of this class
        "min_authorized_rows": 30,           // min evidence rows inside the would-be-authorized slice
        "fallback": { "mode": "hitl" }
      },
      "good": {                              // e.g. "release part"
        "autonomy": "eligible",
        "threshold_mode": "risk_controlled",
        "threshold_grid": [0.995, 0.99, 0.98, 0.97, 0.95],
        "max_autonomous_risk": 0.01,
        "min_authorized_rows": 60,
        "fallback": { "mode": "safe_action", "action": "quarantine", "deferred_review": true }
      }
    },
    "default_class": { "autonomy": "never", "fallback": { "mode": "hitl" } },   // unknown / missing class value
    "qualification": {
      "min_discrimination_auroc": null,      // optional gate; always reported as a diagnostic
      "require_admin_approval": true
    },
    "monitoring": {
      "probe_rate_initial": 0.3, "probe_initial_decisions": 50, // heavier sampling right after authorization
      "probe_rate": 0.1, "min_probes_per_decisions": [2, 50],   // count-based, not per UTC day
      "warn_when": "point_estimate_exceeds_budget",
      "revoke_when": "lower_bound_exceeds_budget",               // LCB(errors/probes) > max_autonomous_risk
      "revoke_on_confirmed_failures": 3,                         // verified failures of autonomous decisions (outcome feedback)
      "min_probe_rows_for_rules": 10
    },
    "requalify_on": ["model_activation", "authority_policy_change", "revocation"]
  }
}
```

- **Validation:** a dedicated validator in amp-backend (the flat autonomy-ops catalog can't express nested classes). Budgets must be in (0, 1), thresholds in (0, 1], grids strictly descending, `class_key` must be in `action_fields_allowlist`, and fallback modes must be known.
- **Two configuration channels today, one source.** Per-decision logic (hitl-agent → `RLHFDecisionService`) reads the policy file. Tick logic (rlhf worker) reads `rlhf_agent_config.params_json`. The same block reaches both:
  - amp-backend passes it into `params_json.authority`, validated and canonicalised, with an `authority_version` hash;
  - hitl-agent's `normalizePolicy` passes `autonomy_ops.authority` through, the same pattern as the ISSUE-3 fix.

## 2. State model

- **Per-class authority scopes,** stored in `rlhf_agent_state.metadata_json.authority`. That is the row `decide()` already reads as `agentState`, so no schema migration is needed:

```jsonc
"authority": {
  "authority_version": "sha256:…",           // hash of the policy block in force
  "model_version": "v_…",                    // scopes are only valid for this model
  "evidence_since": "2026-…",                // activation / revocation time; evidence rows must be later
  "classes": {
    "defective": { "status": "authorized", "threshold": 0.93, "authorized_at": "…", "approved_by": "…",
                   "qualification": { "n": 64, "errors": 1, "ucb": 0.071, "auroc": 0.81, "tested": [[0.99, "pass"], …] },
                   "monitor": { "decisions": 120, "probes": 18, "probe_errors": 0, "confirmed_failures": 0, "state": "ok" } },
    "good": { "status": "qualifying", … }    // qualifying | pending_approval | authorized | revoked
  }
}
```

- **Agent-level stage becomes derived (backward compatible):**
  - Stage 0: no active model.
  - Stage 1: active model, no class authorized.
  - Stage 2: at least one class authorized.
  - The existing `stage` column, UI and SDK keep working. Under `authority.enabled` the legacy Stage 1 → 2 gates and the zero-autonomy rollback check are bypassed; they are replaced by §4 and §5.
- **Per-decision record additions.** Written to `rlhf_approval_request.signals_json`, which every query already reads:
  - `action_class`;
  - `authority_state` (the class status at decision time);
  - `class_threshold`;
  - `governance_outcome` ∈ {`execute`, `probe`, `hitl`, `fallback`};
  - `fallback_action`;
  - `authority_version`;
  - `model_version` (already present).

## 3. Authorize: the per-decision flow (`RLHFDecisionService.decide`, authority mode)

1. **Resolve the class.** c = `action_context[class_key]`; an unknown value → `default_class`.
2. **Score.** The active model gives P(human approves proposal), as today. No model, or a scoring failure → fallback.
3. **Check eligibility.** The item is eligible iff all of these hold:
   - class c has `autonomy: eligible`;
   - the scope status is `authorized` for the *current* `model_version` and `authority_version`;
   - P ≥ the class's qualified `threshold`;
   - no hard criterion is unmet.
4. **Eligible → execute, or probe.** The probe is chosen by the §5 schedule. `governance_outcome = execute`, routing `auto`, decision `approve`: the agent's own proposal executes. Probed items go to a human (`probe`).
5. **Not eligible → the class fallback.**
   - `hitl` (the default): today's human workitem path.
   - `safe_action`: return immediately with `governance_outcome = fallback` and `fallback_action` (e.g. `quarantine`). If `deferred_review` is set, also create a **non-blocking** review workitem, so human evidence keeps accruing (§3.3).
6. **Never reversed.** Under authority mode the auto-reject path is disabled entirely, whatever `auto_reject_threshold` says.

### 3.1 Why per-class thresholds must come from qualification, not configuration alone

- **Experiment 2 is the reason.** In juice_bottle s4 a fixed 0.90 threshold selected every item, because the model's probabilities were uninformative.
- **Two modes:**
  - under `risk_controlled`, the threshold is the one *certified* by qualification (§4);
  - under `fixed`, qualification still has to certify that the configured threshold meets the risk budget, or the class stays unauthorized.

### 3.2 Probe selection

- **Probes are selected by a per-class counter schedule** (§5), not a hash of the random decision-point id.
- **A sim/test flag makes selection seedable** for reproducible experiments. Today's hash-based probe selection is the known source of post-promotion non-determinism in Experiment 2.

### 3.3 Safe-action fallback

- **Scope.** The safe action is agent-defined and policy-named; AMP only names it. The agent must implement it (e.g. put the part in a quarantine bin).
- **What AMP records.** The decision is recorded with `decision_mode = fallback`, and no autonomous authority is exercised.
- **Evidence.** With `deferred_review`, the later human decision is recorded as a normal human outcome for the same decision point. That feeds evidence and training exactly like a synchronous review, without blocking the agent.
- **Minimum for Experiment 3:** `hitl` fallback is required; `safe_action` is optional (see §9).

### 3.4 Public contract mapping (hitl-agent `decision_provider_endpoint.js`)

| governance_outcome | amp-core outcome | reason_code |
|---|---|---|
| `execute` | `allow` | `rlhf_authorized_execute` |
| `probe`, `hitl` | `require_human` | `rlhf_probe` / `rlhf_not_authorized` |
| `fallback` (safe_action) | `deny` | `rlhf_fallback_safe_action` |

- **The invariant holds.** `deny` and `require_human` are never looser than a policy floor, so `decide_with_safety`'s tighten-only invariant is preserved.
- **Private detail stays private.** `fallback_action` and scope details travel only in the Enterprise-private payload and callback, not in the public `diagnostics`.

## 4. Qualify: selective-risk qualification (StageTickHandler, per class)

**Evidence.**
- E_c = human-decided rows (`decision_mode = human`) with `action_class = c`, a non-null `model_score` from the **current** `model_version`, created after `authority.evidence_since`.
- While a class is unauthorized, every item of that class goes to a human, so E_c is an unselected prospective sample.
- Rows labelled during `deferred_review` count too.

**Statistic.** For threshold t:
- slice S_t = { rows in E_c with P ≥ t };
- n_t = |S_t|, and k_t = the number of human *rejections* of the proposal in S_t (the proposal was wrong);
- UCB_t = one-sided Clopper–Pearson upper bound on k_t/n_t at `confidence`.

**Pass rule.**
- `fixed` mode: the single t passes iff n_t ≥ `min_authorized_rows` and UCB_t ≤ `max_autonomous_risk`.
- `risk_controlled` mode, **fixed-sequence testing:**
  - test the grid from the highest threshold downwards, and stop at the first failure;
  - the certified threshold is the lowest t that passed before any failure;
  - the family-wise error of certifying a threshold whose true risk exceeds the budget is ≤ 1 − `confidence`, with no data splitting;
  - if the highest grid value already fails, the class stays `qualifying`.

**Diagnostics** (stored, displayed, optionally gated):
- AUROC of P against the human decision within E_c;
- the share of E_c with P ≥ t;
- probability quantiles.

**On pass → `pending_approval`.** A per-class authorization workitem is created (the pattern of `upsertStage2PromotionWorkitem`). Its payload: class, certified threshold, n, k, UCB, the grid results, diagnostics, model_version and authority_version.

**On admin approval.**
- amp-backend's workitem-resolution handler writes `status = authorized`, the threshold and an evidence snapshot.
- It sets the derived stage.
- On rejection the class stays `qualifying`, and evidence keeps accumulating.

**Worked check (by construction, not an experimental claim).** In the Experiment 2 run where every probability was ≥ 0.917, the whole Stage 1 set was the authorized slice, with ≈ 14 % proposal errors. Any budget ≤ 5 % fails. A selective-risk gate cannot be passed by an uninformative model unless the proposals themselves are within budget.

**Replaced under authority mode:** the cumulative/recent agreement gates and the Stage 1 → 2 promotion workitem. Stage 0 → 1 (first model training and activation) is unchanged, except for the acceptance rule in §6.

## 5. Monitor: evidence with consequences (StageTickHandler, per authorized class)

**Probe schedule.** Per class, counted in eligible decisions since authorization:
- rate `probe_rate_initial` for the first `probe_initial_decisions`, then `probe_rate`;
- at least `min_probes_per_decisions` (e.g. 2 in every 50);
- replaces the per-UTC-day minimum.
- Probes are human-reviewed, so they give an **unbiased estimate of the autonomous slice's error rate.**

**Monitoring evidence.**
- (a) Probe rows of class c since authorization: n_p probes, k_p proposal rejections.
- (b) Confirmed failures: outcome feedback `failed` or `reversed` on *autonomous* decisions of class c. It is accepted today but unused by any gate.

**Graduated consequences, all audited as `rlhf_events` plus agent-log entries and visible in status:**

| Condition (evaluated each tick) | Consequence | Reversible how |
|---|---|---|
| n_p ≥ `min_probe_rows_for_rules` and k_p/n_p > budget | **warn**: event + admin notification | automatically when back in budget |
| LCB(k_p, n_p) > budget (one-sided Clopper–Pearson at `confidence`), or confirmed failures ≥ `revoke_on_confirmed_failures` | **revoke** the class: status `revoked`, new `evidence_since`; class decisions use the fallback | only by fresh qualification (§4) + admin approval |
| all classes revoked or unauthorized | derived stage falls to 1 | as above |

**Design notes.**
- Using the lower bound for revocation keeps false alarms rare while acting as soon as the evidence is conclusive.
- Repeated testing inflates false alarms. That is accepted, because it fails in the safe direction; an alpha-spending variant is left for later.
- Automatic threshold *tightening* (moving one grid step up on warn) is deliberately **excluded** from the minimum set. It would need its own evidence rule, and revocation already covers safety.

## 6. Requalify: model-scoped evidence and model change

1. **On ACTIVATE of any model** (`EvalActivateHandlers`):
   - set `authority.model_version` and `evidence_since = now`;
   - move every class to `qualifying`, so there is no carry-over;
   - under authority mode, also clear the legacy `stage1_promotion_*` and `stage1_agreement_*` keys.
   - The ISSUE-1 fix is proposed here as part of authority mode. Fixing it in legacy mode too is a separate product decision: it changes default behaviour, so it would need its own opt-in flag.
2. **Model acceptance** (EVAL, authority mode). The current acceptance rule (`upgrade_min_auto_rate_gain`) rewards models that authorize more. Under authority mode acceptance becomes a **sanity check** on the training test split:
   - label diversity;
   - AUROC ≥ a floor;
   - not worse than the active model by more than a margin.
   - The real evidence gate is prospective requalification (§4). This keeps the evidence budget small and avoids evaluating on the rows used for Platt calibration.
3. **Authority-policy change.** A new `authority_version` hash on policy approval makes the tick treat every scope with an older hash as `qualifying`, with a new `evidence_since`.
4. **Revocation** → the class requalifies from fresh evidence (§5).
5. **Deferred, not in the minimum set: shadow requalification.** Score a candidate on live human-labelled rows *before* activation, to shorten the autonomy gap after retraining. It is useful for the Stage 2 whiplash the Playbook warns about, but not needed for Experiment 3.

## 7. Metrics (operational in AMP; experimental in the simulator)

**Operational.** Per agent × model_version × class × period, exposed in `/api/rlhf/status` under an `authority` section and in `ObservabilityService`:
- decisions; `execute` count; `probe`, `hitl` and `fallback` counts;
- **HITL burden** = human-reviewed ÷ decisions (probes + hitl + deferred reviews);
- probe error estimate with its confidence interval; confirmed failures;
- qualification state and evidence (n, k, UCB, certified threshold, AUROC);
- time-to-authorization (decisions and wall-clock); revocations and requalifications with causes;
- human override rate (proposal rejections) in each routing path.
- **In deployment the correctness of unprobed autonomous decisions is unknown.** AMP reports it as an *estimate* from probes and feedback, never as a fact.

**Experimental** (vision-autonomy simulator, ground truth known). Logged per decision from the new `signals_json` fields:
- **useful autonomy** = correct autonomous executions (count, and rate over all decisions);
- **autonomous risk** = errors ÷ autonomous executions, split by class and by FA/FR;
- **HITL burden**; fallback volume, and the correctness of safe actions;
- final accuracy (always shown next to HITL burden);
- per-class **budget compliance** (realised autonomous error ≤ budget);
- time and decisions to authorization; number of revocations and whether each was warranted.
- **Hook for the fair baseline** (for Experiment 3, not designed here): record every qualification evaluation — timestamp, evidence row ids, certified threshold. A static-HITL "twin" can then apply the same certification rule to the raw margin, using the same evidence at the same time. This gives "matched information", as agreed in the review.

## 8. Prerequisite branches (merge first)

| Repo | Branch | Commit | Status | Action |
|---|---|---|---|---|
| hitl-agent | `fix/normalize-policy-rlhf-fields` | `746a268` | 1 ahead of **stale** local `main`; `origin/main` has 2 newer commits (OpenClaw/codex support) | fetch → rebase onto `origin/main` → `npm test` → merge |
| amp-backend | `feat/stage1-agreement-basis` | `ad5e7e8` | 1 ahead of stale local `main`; `origin/main` has **7 newer commits**, incl. `e9b1c78` (action-id correlation for `get-decision`, safe modified approvals) and `ca018b5` ("Policy not hitting HITL even when stated") | fetch → rebase → full pytest → **re-run the Experiment 2 E2E smoke** (the simulator uses `get-decision`) → merge |
| rlhf | `feat/stage1-agreement-basis` | `2d3356e` | 1 ahead of `main` = `origin/main`; includes the `dist/` rebuild (activates `d92f45e`) | merge; separately triage the 3 pre-existing failing tests (gate_orchestrator `rules_strict` expectation; 2 override-validation fixtures) |

**Notes.**
- **Both experiments ran on the stale local `main`** plus these branches. That is recorded in the run manifests (git SHAs) and is correct for reproducibility. The new work should start from the rebased, merged upstream, and the Experiment 1/2 legacy-mode replay regression (§9) guards against behaviour drift from the upstream commits.
- **AWS deployment** of the merged prerequisites follows your normal procedure: `git pull` on the server repos, then `~/bin/run_deploy.sh`. It is a separate decision from Experiment 3, which runs locally.

## 9. Smallest coherent implementation sequence

Each step is behind `authority.enabled`, lands with unit tests, and must pass these regressions before the next step starts:
- the **legacy-replay regression:** Experiment 1 and 2 records re-evaluated in legacy mode give identical gate and routing results;
- the existing suites.

| Step | Content | Repos | Size | Exit criterion |
|---|---|---|---|---|
| **P0** | Rebase + merge the prerequisites (§8); triage the 3 rlhf test failures | all three | S | suites green on upstream; Experiment 2 E2E smoke passes |
| **P1** | Schema + plumbing: `authority` validator; pass-through to `params_json` (with `authority_version`) and through hitl-agent `normalizePolicy`; new `signals_json` fields written in legacy mode too (additive) | amp-backend, hitl-agent, rlhf | M | a policy with `authority` round-trips; legacy decisions unchanged |
| **P2** | Authorize: class resolution, scope lookup, per-class threshold, `hitl` fallback, auto-reject disabled, public-contract mapping, counter-based and seedable probes | rlhf (`RLHFDecisionService`), hitl-agent mapping | M | unit tests over a decision matrix (class × status × P × hard-block) |
| **P3** | Qualify: evidence query (model- and time-scoped), Clopper–Pearson, fixed-sequence certification, per-class authorization workitem; backend approval handler writing scopes; derived stage | rlhf (`ApprovalRepo`, `StageTickHandler`), amp-backend (workitem resolution) | M–L | synthetic-evidence tests: known k/n → expected certify/reject; admin approve → scope authorized |
| **P4** | Monitor: probe schedule, warn/revoke rules, confirmed-failure counting, events and notifications | rlhf, amp-backend (notify) | M | simulated deterioration revokes within the expected number of probes; no revoke on in-budget streams (tests) |
| **P5** | Requalify: activation resets scopes (model-scoped), EVAL sanity acceptance, `authority_version` change handling | rlhf (`EvalActivateHandlers`, `ExtractTrainHandlers`) | M | retrain → activation → classes `qualifying` → re-certify possible (fixes ISSUE-1 in authority mode) |
| **P6** | Metrics: status/observability `authority` section; simulator logging of the new fields and the qualification-evaluation hook | rlhf, amp-backend, vision-autonomy | M | metrics reconcile with raw decision records |
| *P7 (optional)* | `safe_action` fallback + deferred review; UI for per-class scopes | rlhf, hitl-agent, amp-backend, frontend | M | only if Experiment 3 uses a safe action |

- **Minimum for Experiment 3: P0–P6.**
- **Ordering rationale.** P2 is useless without P3 (no scope can become `authorized`) but is testable alone. P4 depends on P2's probe schedule. P5 depends on P3's scopes. Each step leaves legacy agents untouched.

## 10. Controlled-shift environments for Experiment 3 (sketches only; not designed)

**E-A: Defect-mix shift on LOCO (cheapest; reuses frozen PatchCore scores).**
- **Change:** in each category's stream, the first segment is normal plus *structural* anomalies, where PatchCore is stronger. After a change point the mix shifts toward *logical* anomalies, where it is weak (AUROC 0.61–0.86), and/or toward higher prevalence.
- **Exercises:** Authorize and **Monitor/revoke**. "Good" proposals become wrong more often after the shift, so a correctly working system should revoke the "good" class and keep "defective" authorized.
- **Caveats:** a constructed stream order, not a natural shift; limited items per category (a change point needs enough pre- and post-shift items; seeds can be pooled).

**E-B: Acquisition shift with MVTec AD 2 (most realistic imaging shift).**
- **Change:** AD 2 was built to probe robustness, with test images under changed conditions such as lighting. Streams start with regular-condition images and switch to shifted-condition images; PatchCore is trained once on the regular train set, and its scores and proposals degrade after the switch.
- **Exercises:** Monitor/revoke, then Requalify once enough post-shift human evidence exists (a retrained AMP model).
- **To verify first:** licence, download, and **whether ground truth is public** for the shifted test subsets. At least one AD 2 test split has hidden labels, and we need labels for the oracle. We also need a new PatchCore run, with the same "no tuning" rule.

**E-C: Product changeover or perception-model update.**
- **Change:** one agent governs a line whose product changes mid-stream (e.g. LOCO category A → B, or VisA categories), *or* whose perception model is replaced (e.g. a PatchCore variant with a different backbone), without AMP being told.
- **Exercises:** **Requalify on material change.** A variant with an explicit `agent_version` or `product` field, carried in `class_key` or as an authority-version trigger, tests declared change. A variant without it tests whether monitoring alone detects the change.
- **Caveats:** needs a decision on whether a declared change must trigger requalification. That is a small addition to §6: an agent-declared `perception_version` field in `requalify_on`.

All three can compare against a static-HITL twin with matched information (§7 hook). E-A is the natural first step, being cheap and reusing Experiments 1–2 assets. E-B has the most external validity.
