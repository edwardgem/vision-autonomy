# E2E_REPORT.md — Component 3 end-to-end validation

Date: 2026-09-23. Model: Sonnet 5. **Result: HARD STOP. The full experiment must not run under `prereg-v1`.**
Three assumptions in the pre-registered plan do not hold on this AMP deployment. Evidence is in `results/e2e/`.

## 1. What was run

- **Agents:** `vis-loco-e2e-1` (one probe item), `vis-loco-smoke` and `vis-loco-smoke-2` (12-item code smoke tests),
  and `vis-loco-e2e-2` (the real E2E: `juice_bottle`, stream seed 999, not a study seed).
- **Setup:** each agent was registered and given the frozen `config/amp_policy_v1.json` (filled with org and agent
  only) through AMP's own endpoints. RLHF was enabled and a scoped RLHF worker spawned for each.
- **E2E run:** 240 of 330 items were processed at Stage 0 before the run was stopped (see §3). All 240 were routed to
  the human and completed by the simulated oracle.

## 2. Acceptance checks (plan §9)

| # | Check | Result |
|---|---|---|
| 1 | Routing, oracle decision and outcome feedback persist | **PASS.** 240 requests, 240 outcomes, 240 feedbacks (reward +1.0, `confirmed`), 240 in tick summaries. Smoke runs reconcile exactly (12 = 12 = 12). |
| 2 | Stage 0 → 1 → 2 through AMP's own jobs and workitems | **FAIL.** Never left Stage 0 (§3). |
| 3 | `auto_reject_threshold: 1.01` honoured; no auto-reject | **FAIL: the field is ignored** (§4). No auto-reject occurred only because Stage 2 was never reached. |
| 4 | Base-policy rules never fire | **FAIL (by code):** the "disabled" setting is ignored, so the defaults (both on) apply (§4). Not observed in the run, because it needs Stage ≥ 1. |
| 5 | Tick statistics reconcile with items sent | **PASS after two fixes to my own loop** (§5). |
| 6 | Training seed honoured | **PASS.** `RLHF_TRAINING_SEED=vision-loco-v1` is in the backend and in each spawned worker's environment (`ps eww`). `AMP_TESTING_MODE` is unset. AMP's status endpoint also reports `amp_testing_mode: false`. |
| 7 | Per-item latency, and the seed-fallback rule | ≈ 0.3 s/item plus ≈ 4–5 s per tick/settle every 10 items (≈ 0.75 s/item overall, 275–341 items/run). One seed (1,568 items) ≈ 25–35 min, well under the 3 h limit, so **no fallback: 5 seeds.** Estimate only, because Stage 1/2 pipeline jobs were never exercised. |

## 3. Finding A: AMP cannot learn anything from the proposal, score or margin (Stage 0 → 1 impossible)

- At every retrain, EVAL rejected the candidate: `candidate_auto_rate_est = 0` on 80, 160 and 240 eval rows, against
  a required gain of ≥ 0.03. (The gate counts rows whose predicted P(approve) ≥ the 0.90 Stage 2 threshold.)
  After the default 4 failed retrain cycles, **AMP auto-disabled RLHF for the agent** (`RLHF_AUTO_DISABLED`, and the
  policy files were rewritten with `rlhf_enabled: false`). The agent's scoped worker then exited, and the last tick job stayed
  `queued` with 0 attempts (verified), which is why my settle loop stalled and I stopped the run.
- **Root cause:** the trained model's only features are the four one-hot statuses of the single constant criterion
  (`status.c_perception_output_valid.*`). The stored decision-time feature map is
  `{"status.c_perception_output_valid": "met"}`. `proposal`, `score_z` and `margin_abs` were delivered
  (`metadata.action_context` has them) but never entered `features_json`, the dataset (`x` has one key), or the model.
  The model is constant, so it can never exceed the 0.90 bar.
- **Cause in code:** see §4. AMP builds features only from `action_fields_allowlist`, and that list never reaches
  the decision service.

## 4. Finding B: the HITL server drops three policy fields the plan depends on

`hitl-agent/server/rlhf_integration.js::normalizePolicy()` rebuilds the policy from a fixed short list of fields.
I ran that exact function on the real policy file (`vis-loco-e2e-2/policy/policy_v1.json`, which contains all three):

| Field in the policy file | After `normalizePolicy` (what the RLHF decision service receives) | Consequence |
|---|---|---|
| `action_governance.action_fields_allowlist = [proposal, score_z, margin_abs]` | **undefined** | no action-field features (Finding A) |
| `action_governance.automation.auto_reject_threshold = 1.01` | **undefined** | reject threshold defaults to the approve threshold (0.9), so a binary model at Stage 2 **auto-rejects when P(approve) ≤ 0.10** |
| `action_governance.base_policy_rules = {both false}` | **undefined** | `approve_on_all_pass` and `reject_on_hard_fail` stay **on** (default) at Stage ≥ 1 |

The downstream code (`RLHFDecisionService`, `buildFeatureMap`, the gate) reads all of these fields, so this looks like an
omission in the HITL server's normalizer rather than a design choice. Effects on plan v1 if Stage 2 were reached:
- **Auto-reject would be live.** This violates decision 6 (AMP must not become a second classifier).
- **`approve_on_all_pass` would fire.** Our only criterion is always met, so every Stage ≥ 1 item would get a
  deterministic approve with confidence 1.0, bypassing the learned model. Condition D would collapse to model-only.

## 5. Bugs found and fixed in my own simulator (not AMP problems)

1. The settle-loop fingerprint counted STAGE_TICK job rows that my own ticks add, so it never converged.
2. AMP's tick job id is `hash(now − tick_minutes)` at **minute** resolution. A duplicate id is silently skipped, so
   ticks on a re-used agent, or two ticks with the same `tick_minutes` in one minute, would have been dropped
   (row loss). Ticks now use `tick_minutes = 1440 − k`, which gives unique ids. The window is unaffected, since
   AMP starts each window at `max(payload start, last_processed_at, end − 24 h)`. A guard aborts if a tick
   does not create a new job. This is an implementation note relative to plan §5.4 (which says `tick_minutes = 1440`).

## 6. Other findings that matter for the design

- **Authorization boundary.** An API key cannot complete workitems (needs the `hitl:resolve` capability) and can
  **never** resolve privileged RLHF model/stage approvals. Per Edward's decision, the simulator uses one login
  session as `reviewer@example.org` (password in the gitignored `.env`) for all workitem resolution. That includes
  the admin approvals, each of which is logged in `manifest.summary.admin_approvals`. Paper note: the simulated
  human is a human-admin session, not an API key.
- **AMP counts the workitem completion and the outcome separately.** Both are posted (as the payment simulator
  does). The `callback: failed` in the completion response is only the absent per-agent callback URL and is harmless.
- **What "a category that doesn't promote" looks like in AMP.** With the default `max_failed_retrain_cycles = 4`, AMP
  does not simply stay in Stage 0. After 4 rejected candidates it **turns RLHF off** for the agent. The plan
  should say what that means for reporting (the remaining items are all human).
- **Billing:** Team tier, 25,000 free calls/month, no hard cap (`hard_cap_calls = 0`); $0.008 per overage call in the
  local DB. A full study is about 8k items × roughly 8 calls ≈ 65k calls (rough estimate). Nothing is blocked; overage accrues in the local
  usage tables. Registering 25 native agents does not touch the `remote_agents` limit (25; 4 in use).

## 7. Options for the revision (needs a stronger model plus Edward's decision)

**A. Fix AMP's omission** (recommended). Pass `action_fields_allowlist`, `signal_keys_allowlist`, `base_policy_rules`
and `automation.auto_reject_threshold` through `normalizePolicy` in `hitl-agent/server/rlhf_integration.js` (about 10 lines;
the RLHF library already reads them), then restart `hitl-agent`. Plan v1's semantics then work as written.
Cost: the system under test is modified, so the paper must state the hitl-agent commit plus this patch (it is a fix
of a config-drop bug, not new functionality). This is Edward's call because the brief says not to add AMP functionality.

**B. Stay on unmodified AMP.** The only features AMP's model can see are criterion statuses, so the agent would
have to encode the score and margin as several externally evaluated soft criteria. That needs at least three hacks:
a permanently unmet soft criterion to keep `approve_on_all_pass` from firing, a defined meaning for AMP's
default auto-reject (which flips the vision proposal, making AMP a classifier), and a criteria design that is
itself a threshold rule. This changes what "AMP progressive autonomy" means, and is much harder to defend.

Under either option the E2E must be repeated, and these plan points need explicit v2 decisions:
- the EVAL gate for 0 → 1 is auto-eligibility (≥ 3 % of rows at P ≥ 0.90) computed on 80 training rows with
  Platt scaling on about 16 held-out rows. Whether any category can pass it is unknown until features work;
- what to report when AMP auto-disables RLHF after 4 failed cycles (or whether `max_failed_retrain_cycles`
  is part of the frozen parameters — it is, at the default 4);
- the `c_perception_output_valid` criterion is a constant and contributes nothing.

Per the pre-registration rule, any change is a `*_v2` with a stated reason, and these v1 E2E results stay on record.

## 8. State left on the local system (nothing cleaned up)

- **pm2:** `hitl-agent` and `log-agent-rlhf` were started this session (secret injected at start; not `pm2 save`d).
- **`amp-backend/.env`:** added `RLHF_TRAINING_SEED=vision-loco-v1`; `amp` was restarted once.
- **Agents registered:** `vis-loco-e2e-1`, `vis-loco-smoke`, `vis-loco-smoke-2`, `vis-loco-e2e-2`, each with a policy
  and scoped RLHF worker (still running for the first three). Datasets and models under `amp-backend/.amp-rlhf/`.
  `vis-loco-e2e-2` has RLHF auto-disabled. `vis-loco-e2e-1` had one item completed.
- **Local DB:** the E2E rows above plus billing usage counters.
- **Logins:** one login session as Edward per run; no failed login attempts.

## 9. Code delivered (all in this repo)

`scripts/build_inputs.py` (1,568 input records), `sim/amp_client.py` (AMP REST client + human session),
`sim/amp_db.py` (read-only AMP DB view), `sim/run_amp.py` (one stream, one agent). Known gaps: baselines A–C and
aggregation/tables are not built yet (Component 4), and the Stage 1/2 code paths are unexercised.
