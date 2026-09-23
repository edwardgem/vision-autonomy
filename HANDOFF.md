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
