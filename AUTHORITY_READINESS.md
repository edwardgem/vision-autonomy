# GOV authority lifecycle (P0–P7): implementation and readiness report

2026-09-25. Implements `GOV_AUTHORITY_DESIGN.md`. **Experiment 3 has not been designed or run.**

## 1. Verdict

- **Complete.** P0–P7 are implemented on `feat/authority` in rlhf, hitl-agent and gov-backend. The optional per-class scope UI is not done (§6).
- **The authority lifecycle is the default GOV model.**
  - An absent block resolves to `enabled: true`, with defaults.
  - `{enabled: false}` gives legacy mode.
  - An invalid block resolves to enabled, fail-closed: no class is eligible.
  - The resolver's rules are identical in TypeScript and Python (shared test vectors).
- **Migration.**
  - Every existing policy file and config row without the block was explicitly marked `{enabled: false}`: 196 files and 63 rows, local database only.
  - New policies get a materialised `enabled: true` block when approved.
- **Gates.** Every phase was gated on all three suites plus the Experiment 1/2 legacy replay. All pass at the final commits:

| Gate | Result |
|---|---|
| rlhf | 129/129 |
| gov-backend | 876 passed |
| hitl-agent | 61/61 |
| Legacy replay A: routing | 15,680 decisions, 0 mismatches |
| Legacy replay B: tick gates | 2,297 ticks, 0 mismatches |
| Legacy replay C: SQL window stats | 3,479 windows, 0 mismatches |

- **Live validation.** Two full local E2E runs passed (§4). They were run on the real stack: amp, hitl-agent and the scoped RLHF worker, with a MySQL oracle and an admin session.
- **Nothing has been pushed, merged or deployed.**

## 2. What was built

| Phase | Where | What |
|---|---|---|
| P0 | rlhf | Legacy gate evaluation and Stage 2 routing extracted into pure functions (behaviour-neutral). The legacy replay harness (`regression/legacy_replay.js`) is mutation-tested. |
| P1 | all three | **Authority block:** resolution, validation (backend 400 on save/approve), version hash, explicit block written on approve.<br>**Migration:** `scripts/migrate_authority_default.py`; dry-run by default, idempotent, with backups.<br>**Pass-through:** hitl-agent `normalizePolicy` passes the block raw.<br>**Decision records:** gain the governance fields. |
| P2 Authorize | rlhf, hitl-agent | **Per decision:** class resolution → scope lookup → the class's certified threshold → `execute` / `probe` / `hitl` / `fallback`. There is no auto-reject in authority mode.<br>**Probes:** a deterministic per-class counter schedule.<br>**Public mapping:** execute → allow, fallback → deny, probe/hitl → require_human. |
| P3 Qualify | rlhf, backend | **Certification:** a Clopper–Pearson upper bound ≤ the budget on the prospective, model-scoped slice; fixed-sequence testing down the grid. Sparse thresholds are skipped, not failed; the sequence stops at the first bound failure.<br>**Authorization:** a privileged workitem that only a human admin session can resolve. API keys are always refused.<br>**Recorder:** race-safe; stale proposals are rejected. |
| P4 Monitor | rlhf | **Revoke** on a probe-error lower bound above the budget, or on N confirmed downstream failures. **Warn** on the point estimate. A revoked class requalifies from fresh evidence. |
| P5 Requalify | rlhf | **Reset:** a model or authority-policy change resets every class to qualifying; evidence starts at activation.<br>**Model acceptance (authority mode):** a held-out sanity check (label diversity, test AUROC ≥ 0.55, a drop of at most 0.05 from the active model), replacing the legacy auto-rate gain. The trainer now reports `test_auroc` and `label_counts`. |
| P6 Metrics | backend, rlhf, simulator | **`/api/rlhf/status` → `authority`**, per class and in total:<br>• decisions by outcome;<br>• HITL burden;<br>• override rate per routing path;<br>• probe error estimate with an exact CI;<br>• confirmed failures;<br>• qualification evidence;<br>• time to authorization;<br>• lifecycle counts.<br>It is computed from the raw decision records, and tests check that the numbers reconcile.<br>**Fair-baseline hook:** `AUTHORITY_QUALIFICATION_EVALUATED` records every evaluation with its exact evidence ids.<br>**Simulator:** logs the governance fields and flags authority invariant violations. |
| P7 Fallback | rlhf, hitl-agent, backend, simulator | **`safe_action`:** the decision is final at once. The agent resumes immediately with `reject` + `method=fallback` + `fallback_action`, and get-decision reports it as complete.<br>**Deferred review:** a non-blocking workitem bound to the same decision point. Completing it (approve/reject only) records the normal human outcome through a retryable outbox. It never resumes the agent: no callback outbox row and no dispatch. |

Commits on `feat/authority`:

| Repo | Commits |
|---|---|
| rlhf | `50ff2dd` `c60793a` `df9e62f` `1149507` `50c69bc` |
| hitl-agent | `89aedc1` `77eabbc` `ae3d409` |
| gov-backend | `40123ed` `407a249` `2edd314` |

## 3. Legacy guarantee

- **Legacy mode is behaviour-identical.** It is used only for backward compatibility and Experiment 1/2 reproducibility.
  - The replay regression re-derives every recorded Experiment 1/2 routing decision, tick gate and SQL window statistic, with zero mismatches.
  - No legacy-only behaviour fixes were made.
- **Pre-migration templates stay legacy.** The simulator injects `{enabled: false}` when a template lacks the block, and records `legacy_authority_injected` in the manifest.
- **Experiment 1/2 agents** keep `rlhf_enabled: false`, untouched.

## 4. Live E2E validation (juice_bottle, stream seed 999, 330 items each)

**`vis-auth-e2e-2`:** both classes `hitl` fallback; budget 0.10; min rows 30; admin approval required.
- **Lifecycle:**
  - Requalify (initialized) → `defective` certified at 0.85: n=33, a 32-row slice with 0 errors, UCB 0.089.
  - Authorization workitem → admin approval → authorized → derived Stage 2 at item 131.
- **Autonomy:** 70 executions, all `defective`, all at P ≥ the certified threshold. Realised error 3/70 = 4.3%, within the 0.10 budget.
  - **Probes:** 19, exactly what the schedule prescribes, with 0 errors.
  - **Auto-rejects:** 0.
- **`good` class:** stayed qualifying. That is correct: its evidence never met the budget.
- **Retrain:** the second model was accepted by the authority rule (test AUROC 0.683 against 0.733, within the 0.05 drop limit). It was activated, then `AUTHORITY_REQUALIFY` (cause `model_activation`) put the agent back to Stage 1 for the rest of the run.

**`vis-auth-e2e-3`:** as above, but `good` uses `safe_action: quarantine` with deferred review.
- 330/330 reconciled, 0 violations, 0 auto-rejects, no failed jobs.
- **Autonomy:** 96 executions (`defective`), 3 errors (3.1%). 22 probes.
- **Fallback:** 121 `good` safe actions, returned to the agent immediately, with 121 deferred reviews answered.
  - Every review was recorded as a human outcome by GOV itself, through the `deferred_review` outbox (33/33 verified in the DB mid-run).
  - No callback deliveries were created for any review.
  - Those outcomes fed qualification and training.
- **`good` was never authorized.** Only 86/121 of its proposals were correct, far over the budget.
- **Qualification hook:** 72 `AUTHORITY_QUALIFICATION_EVALUATED` events, each with an evidence-id count equal to n.
- **Status section:** `/api/rlhf/status` → `authority` read live and reconciled with the decision records.

All workers for `vis-auth-e2e-1/2/3` were stopped with the documented toggle; only the flag changed. No agents were deleted.

**Observed with P3–P5 but not in a live E2E:** probe-driven revocation, confirmed-failure revocation, requalification after an authority-policy change, and a rejected authorization. There were no bad probes in these streams. All four are covered by unit tests with fakes.

## 5. Findings to carry into Experiment 3 design (not acted on)

1. **Retraining costs autonomy.**
   - Activating a new model voids every scope by design. In e2e-2 the agent lost authority at the retrain near item 290 and could not requalify in the remaining items.
   - Shadow requalification is the deferred remedy (design §6.5). Retrain cadence versus stream length will dominate autonomy in any lifecycle experiment.
2. **Probe estimates at small n are weak.** e2e-2 had 0/19 probe errors but 3/70 wrong executions.
   - The UCB is the honest statement. The point estimate is not.
   - Monitoring power is a design parameter: the probe rate against the budget.
3. **A safe action has a cost the metrics don't price.** In e2e-3, 86 of 121 quarantined parts were truly good. The simulator records `correct = None` for fallbacks, so an Experiment 3 analysis has to define what a safe action costs.
4. **Certification is conservative by construction.** `good` is never authorized with this model and budget. Whether that is the right outcome is a question for Experiment 3, not an implementation defect.

## 6. Deviations, open items and decisions for the PI

- **Optional P7 per-class scope UI: not implemented.** The status API already exposes every field such a UI would show. Frontend deploys are teammate-only (Vercel).
- **One security regression test was relaxed, deliberately** (`test_hitl_get_decision_action_id.py`).
  - Before: the progress log is never consulted for an `action_id`-scoped poll.
  - Now: it is consulted only for a fallback line tagged with the exact same `action_id`.
  - Why: a safe_action fallback without deferred review creates no workitem, so the poll has nothing else to match.
  - The invariant is unchanged: a poll is never satisfied by an unrelated decision. New tests cover untagged and mismatched lines.
- **API keys cannot resolve authority authorizations.** `hitl:resolve` covers ordinary and deferred-review workitems, but authorization workitems are privileged, like model/stage approvals. An explicit `rlhf:authorize` capability is possible if wanted. **Not implemented; your call.**
- **Cosmetic, left as-is:**
  - ACTIVATE events still carry legacy-named fields (`promotion_auto_rate_gain`, `confidence_score`) alongside `authority_acceptance`.
  - `AUTHORITY_REQUALIFY` is stamped with the tick's window end, so it can sort a few ms before `MODEL_ACTIVATED`.
- **The rlhf TypeScript `ObservabilityService` was not extended.** The status endpoint is the metrics surface; the backend has its own Python observability port.
- **Deployment has not been done.** It would take:
  - merging `feat/authority` in the three repos;
  - running the migration with `--execute` on AWS **before** the new code serves (otherwise unmigrated policies silently become authority mode);
  - then `git pull` + `~/bin/run_deploy.sh`.
- **Uncommitted engineering artefacts in vision-autonomy** are committed with this report: the engineering configs, the smoke logs and outputs, and the simulator changes.
