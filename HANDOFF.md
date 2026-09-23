# Vision Progressive Autonomy Experiment — Handoff & Aligned Decisions

Purpose: generate reproducible experimental evidence (CV conference paper) that AMP can
progressively transfer decision authority for visual anomaly decisions from human review
to autonomous execution under policy-governed HITL. **Not** a new CV model, product, UI,
or AMP feature. Four components, each ending with an alignment checkpoint with Edward.

Original task brief: see STATUS.md "Scope" and the four components below.

## Decisions agreed with Edward (2026-09-23)

| # | Decision | Choice |
|---|---|---|
| D1 | AMP target | **Local dev AMP** (pm2 process `amp`, SaaS/Enterprise code path with RLHF). Record git SHAs of `amp-backend`, `hitl-agent`, `rlhf` in every run manifest. |
| D2 | Decision semantics | **Option B**: the vision agent *proposes* a disposition (`good` or `defective`) from PatchCore. AMP governs whether that proposal executes autonomously. Simulated human **approves** the proposal iff it matches ground truth, else **rejects** (corrected final decision = ground truth). Auto-reject at Stage 2 is **disabled** (auto-rejecting a proposal has no operational meaning). |
| D3 | RLHF admin workitems | Simulator **auto-approves** model-approval and Stage 2 promotion workitems (same as payment-agent `--auto-approve-rlhf-admin`). Document this as part of the protocol. |
| D4 | Repo location | `/Users/edwardc/Projects/vision-autonomy` (new, private). |
| D5 | Dataset / model | MVTec LOCO AD (primary); PatchCore via anomalib (v2.6.x, has native `MVTecLOCO` datamodule). Do not tune/modify the model. |

## Methodological guardrails (must be honored in Components 2–4)

1. **No label leakage into AMP.** `anomaly_type` (structural/logical/good) and `ground_truth`
   are recorded for analysis only — never sent as AMP action/signal fields. Allowed AMP
   features: `category`, `predicted_class`, `anomaly_score`, and derived signals computed
   from those (see #3).
2. **Thresholds fixed without test labels.** Do not use anomalib's default adaptive (F1)
   threshold — it is fit on test labels. Candidate approaches (decide in EXPERIMENT_PLAN.md):
   calibrate per-category from LOCO `validation/good` (normal-only, e.g. a fixed quantile),
   or hold out a seeded calibration slice of the test set and evaluate on the remainder.
   The static-HITL band is also fixed a priori. **No post-hoc threshold tuning.**
3. **Non-monotonic correctness.** P(model correct) is lowest near the decision threshold,
   which AMP's logistic regression cannot learn from raw score. The agent should emit a
   derived signal such as `score_margin = |score - threshold|` (normalized per category),
   mirroring payment-agent's derived signals (`amount_over_threshold`, etc.). This is agent
   feature engineering, not AMP modification.
4. **Stream length vs promotion gates.** Test set ≈ 1.5k images. Pre-specify
   `stage1_eval_min_human_rows`, training minimums, tick cadence, and seeded stream order(s)
   so Stage 2 is reachable; run multiple seeds; report metrics overall **and** post-promotion.
5. **AMP behaviors that affect metrics must be set deliberately and reported:**
   Stage 2 probing (`stage2_probe_rate`, default 0.1 — probed items go to human),
   deterministic base-policy rules (`approve_on_all_pass` auto-approves at conf 1.0 at
   Stage 2 — likely disable or define criteria carefully), time-based params (days) under
   accelerated `stage_tick` time, `auto_execute_threshold`, `recommend_threshold`.
6. **Expected negative result is reportable.** PatchCore is weak on LOCO *logical*
   anomalies. Whether AMP keeps humans in the loop there is a finding either way.
   Preserve the Static HITL vs AMP comparison.
7. Keep vision (perception: score/predicted class) and AMP (governance: may this execute?)
   layers explicitly separate in code.

## Reuse map — payment-agent simulator (`../payment-agent`)

Study `simulator/run_e2e.py` and `gateway/hitl_bridge.py`. The vision simulator should call
AMP **directly** (no FastAPI gateway / OIDC / DPoP / step-up — those are payment-demo concerns).

Per-item AMP flow (SaaS path, `X-API-Key` auth):
1. `POST /api/agent/init` → `instance_id` (agent_name prefix; `auto_start`, polling mode)
2. `POST /api/hitl/request` with `caller_id/instance_id`, `org_id`, `agent_name`,
   `hitl{enable,when,who,what:"approval",where:"amp"}`,
   `rlhf{policy_values_source:"external", action_fields, signal_fields, criteria?}`
3. Poll `GET /api/workitems` for the new pending `approval` workitem for this instance
   (skip RLHF admin workitems) **or** detect Stage 2 auto route via
   `GET /api/hitl/get-decision?caller_id=` returning `information == "rlhf_auto_no_workitem"`.
   Workitem `rlhf_payload_json` carries Stage 1 `recommended_decision` / probability — record it.
4. Simulated human: `PUT /api/workitems/{id}/status {status:"Complete", resolution}`
   then `POST /api/rlhf/outcome` (decision_point_id = workitem `rlhf_decision_point_id`,
   `human.role="sim_human"`, `run_mode="sim"`, `sim_run_id`).
5. Optional `POST /api/rlhf/outcome/feedback` (reward signal); lifecycle state + `POST /api/log`.
6. Every N items: `POST /api/rlhf/stage_tick/trigger {tick_minutes}`; auto-approve admin workitems.
Preflight: `POST /api/rlhf/bootstrap`, `GET /api/rlhf/status`. Clean baseline:
`payment-agent/scripts/cleanup_agent_data.sh` pattern. Policy example (RLHF policy with
`action_governance` + `autonomy_ops`): `agents/O-XXXX-ORG/invoice-payment-agent-5c58/policy/policy_v1.json`.

AMP RLHF references: `inquiryon-doc/AMP_DESIGN_AND_DEPLOYMENT.md` §2.5,
`rlhf/docs/AMP_RLHF_Progressive_Autonomy_Playbook_v1.3.md` (stages, gates, probing),
`inquiryon-doc/RLHF_POLICY_SETUP_AND_HITL_REQUEST_GUIDE.md`.
Stage 1→2 gates: `stage1_eval_min_agreement_rate`, `stage1_eval_min_human_rows`,
recent-window agreement, 7-day safety alerts.

## Dataset / model facts gathered so far

- MVTec LOCO AD: 3,644 images, 5 categories (breakfast_box, juice_bottle, pushpins,
  screw_bag, splicing_connectors), structural + logical anomalies, pixel GT masks,
  train/validation (good only) / test (good, logical_anomalies, structural_anomalies).
  License **CC BY-NC-SA 4.0** (non-commercial; fine for research). Cite Bergmann et al.,
  IJCV 2022, doi:10.1007/s11263-022-01578-9. Official page uses a download form; anomalib's
  `src/anomalib/data/datasets/image/mvtec_loco.py` has a direct mydrive URL.
  **Verify exact per-split counts after download** — don't rely on memory.
- anomalib latest 2.6.2 (Python ≥3.10). Machine: Apple M4 Pro, 24 GB, ~100 GB free;
  use python3.11/3.12 venv (system python is 3.14 — likely too new for torch wheels).
- Local AMP runs under pm2 (`amp`). Local org_id / API key / agent registration are
  Component 3 prerequisites — ask Edward if not discoverable from env files.

## Model-switching protocol (agreed with Edward, 2026-09-23)

- Component 1 (dataset/model): Sonnet.
- **Before Component 2 (EXPERIMENT_PLAN.md): tell Edward to switch to a stronger model.** Design decisions
  (threshold calibration, AMP policy/stage settings, leakage rules) are irreversible once runs start.
- Component 3 (simulator + E2E): Sonnet. **If the E2E test shows the stream cannot reach Stage 2, or probing /
  base-policy rules distort metrics (i.e. the plan needs revision), tell Edward to switch to a stronger model.**
- Component 4: Sonnet runs experiments and builds tables; **tell Edward to switch to a stronger model before
  writing RESULTS.md interpretation.**

## Component 1 working notes

- **Download quirk:** `curl` fails DNS for `www.mydrive.ch` on this machine (nslookup works). Workaround:
  `curl -L -C - --resolve www.mydrive.ch:443:91.213.4.64 <url>` (TLS/hostname verification intact).
  URL and SHA-256 (`9e7c84db…e687`) come from anomalib's `MVTecLOCODataset` DOWNLOAD_INFO. Archive is 6,126,996,224 bytes.
- **Leakage confirmed in anomalib:** default `PostProcessor` fits `F1AdaptiveThreshold` on labeled data
  (`gt_label`) → never use its `pred_label`/threshold. Extract raw `pred_score` and apply our own a-priori thresholds.
- Venv: `.venv` (Python 3.12.13; anomalib 2.6.2, torch 2.14.0, lightning 2.6.6). `data/` and `.venv/` are gitignored.

## Component 3 brief (written by Opus at pre-registration `prereg-v1`, for the executing model)

Read EXPERIMENT_PLAN.md (approved, frozen) first. Do not change `config/*_v1.json`. If something in the plan cannot
be implemented as written, STOP and tell Edward (and recommend switching to a stronger model) — do not improvise.

**Build (small, research-grade Python in this repo, `.venv`, httpx):**
1. `scripts/build_inputs.py` → `results/inputs/decision_records.csv` from frozen scores + `config/calibration_v1.json`
   (fields in plan §3). Baselines A–C are computed later, offline, from this file.
2. `sim/amp_client.py` — thin wrappers reusing payment-agent `run_e2e.py`/`hitl_bridge.py` calls (X-API-Key):
   `/api/agent/init`, `/api/hitl/request`, `/api/hitl/get-decision`, `/api/workitems` (+ `/{id}/status`),
   `/api/rlhf/outcome`, `/api/rlhf/outcome/feedback`, `/api/rlhf/stage_tick/trigger`, `/api/rlhf/bootstrap`,
   `/api/rlhf/status`. Reuse `_is_rlhf_admin_workitem` logic for admin WIs.
3. `sim/run_amp.py` — per agent: register agent + install policy (template with `__ORG_ID__`/`__AGENT_NAME__`
   filled; nothing else may differ) → bootstrap → stream loop (plan §5.4) → tick every 10 items with
   `tick_minutes=1440` → settle loop → write outputs (plan §6). One-shot, resumable not required.

**Open implementation questions to resolve by reading code, not guessing:**
- How to create an agent + install an RLHF policy on local AMP (payment agent's policy lives in
  `agents/<org>/<agent>/policy/policy_v1.json`; check backend endpoints for agent creation / policy approval and
  whether approval validates against `rlhf/src/policy_schema.ts`, which lacks `auto_reject_threshold`).
- HITL request: payment used an LLM-evaluated `hitl.when` string. The plan requires "always request HITL, no LLM".
  Find the hitl-agent/backend handling of `when` and use a form that is deterministic (e.g. omit or literal true).
- How to read per-item stage / model score / probe / routing: `rlhf_approval_request.signals_json` has `stage,
  model_score, probe_forced_human, hard_blocked, decision_mode, recommended_decision` (RLHFDecisionService.ts).
- How to detect "RLHF jobs for this agent are idle" for the settle loop (rlhf_jobs table / `/api/rlhf/status`).

**Environment step (approved by Edward):** add `RLHF_TRAINING_SEED=vision-loco-v1` to `amp-backend/.env`,
`pm2 restart amp`, then after bootstrap verify with `ps eww <scoped worker pid> | tr ' ' '\n' | grep RLHF_TRAINING_SEED`.
Also confirm a scoped worker was spawned for the E2E agent (only the payment agent had one at pre-registration).

**E2E acceptance (plan §9) — all must pass before any full run; report results to Edward and stop:**
use agent `vis-loco-e2e-1` (and `-2` if needed), category with stream built from seed 999 (not a study seed).
To reach Stage 2 in E2E you may use the real category stream; do NOT change policy values for the E2E.
Checks: routing + oracle + feedback persist; Stage 0→1→2 via AMP's own jobs/WIs; **zero auto-rejects and
evidence that `auto_reject_threshold: 1.01` is loaded** (e.g. a Stage 2 item with p ≤ 0.10 routed to human, and
the field present in the policy AMP resolved); base-policy rules never fire (no `rules_strict` recommendation at
Stage ≥1 / no base-policy log); tick stats reconcile with items sent; worker has the training seed;
per-item latency → apply the seed-fallback rule (plan §2).
**Hard stop:** any auto-reject, field rejected/ignored, row loss, Stage 2 structurally unreachable, or settle
loop not converging → stop, report, and tell Edward to switch to a stronger model.

**Service startup gotcha (2026-09-23):** AMP needs 3 pm2 apps: `amp` (backend+frontend, `amp-backend/dev.sh`),
`hitl-agent` (:3010, `hitl-agent/ecosystem.config.js`), `log-agent-rlhf` (:4001, `log-agent/ecosystem.config.js`).
The pm2 daemon injects an EMPTY `AMP_INTERNAL_SECRET`, which blocks both services' .env fallback (they skip keys
already present) → log-agent exits `[FATAL] requires AMP_INTERNAL_SECRET in production`. Start/restart them with
the real value (never echo it):
`S="$(grep '^AMP_INTERNAL_SECRET=' ../amp-backend/.env | cut -d= -f2-)"; AMP_INTERNAL_SECRET="$S" pm2 restart <app> --update-env; unset S`
(use `pm2 start <ecosystem>` instead of restart if the app is not registered). Verify with `pm2 jlist` (0 restarts, online).

## Component 3 status (Sonnet, 2026-09-23): HARD STOP - read E2E_REPORT.md first
The E2E failed plan §9 checks 2-4. Do NOT run the full experiment. Root cause: `hitl-agent/server/rlhf_integration.js::normalizePolicy`
drops `action_governance.action_fields_allowlist`, `automation.auto_reject_threshold` and `base_policy_rules`. Needs a v2 plan decision
(fix AMP vs work around it) by a stronger model + Edward. Simulator code exists in `sim/` and `scripts/build_inputs.py`; per-item flow is
validated. Authorization: API key cannot resolve workitems; Edward authorized a human login session (AMP_PASSWORD in gitignored .env) for all
workitem resolution incl. admin approvals. New agents must be FRESH per run (tick job-id collision guard aborts on re-use).

## E2E rerun brief (Opus, 2026-09-23, after hitl-agent fix `746a268`; plan amendment v1.1, tag `prereg-v1.1`)
- **AMP now honours the policy:** `hitl-agent` runs branch `fix/normalize-policy-rlhf-fields` (restarted, verified live:
  features_json contains action.proposal/score_z/margin_abs). Do not modify AMP further. Any new AMP problem → STOP.
- **Simulator updates (Opus):** settle loop now detects AMP auto-disabled RLHF (no stall). The summary reports
  `rlhf_auto_disabled_at_pos` and `stage2_human_with_p_le_0.10`.
- **Run:** `python -m sim.run_amp --category juice_bottle --stream-seed 999 --agent vis-loco-e2e-3 --out-root results/e2e`
  (fresh agent; full 330-item stream; ≈ 5–10 min; run it in the background and poll).
- **Pass criteria (plan §9 + amendment #6):** reconcile_ok; stage 0→1→2 via AMP jobs/workitems with admin approvals
  logged; `auto_rejects == 0`; `stage2_human_with_p_le_0.10 >= 1`; no `violation` events; no model_score of exactly
  0/1 at Stage ≥1 (base rules off); worker has RLHF_TRAINING_SEED; the Stage 1 `amp_recommended_decision` is populated.
- **If juice_bottle does not reach Stage 2** (e.g. RLHF auto-disabled), that is not a code failure. Run ONE more E2E
  on `screw_bag` (seed 999, agent `vis-loco-e2e-4`). If neither reaches Stage 2, STOP and tell Edward to switch to
  a stronger model: Stage 2 reachability is then a plan question. Never change policy values to force promotion.
- **After a pass:** write `E2E_REPORT.md` §10 "Rerun" (checks table plus evidence paths), update STATUS, and stop for
  Edward's review. Do NOT start the study runs.
- **Commits:** no Co-Authored-By lines (Edward's standing rule).
