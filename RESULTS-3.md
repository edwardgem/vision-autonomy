# RESULTS-3.md — Experiment 3: authority lifecycle under a controlled reliability change

- **Plan:** `EXPERIMENT_PLAN_3.md`, preregistered as tag `prereg-exp3-v1`.
- **Run:** 2026-09-25, executed by Sonnet per the HANDOFF run brief. Written by Opus.
- **Sources:**
  - Primary: `results/exp3/aggregate/exp3_primary.json`, produced by the preregistered `analysis/exp3_analysis.py`, unchanged.
  - Secondary: `results/exp3/aggregate/secondary_tables.md`, produced by `analysis/exp3_secondary.py`.
  - Every number below is copied from those two files.
- **Structure:** §2–§4 are observation; §5 onward is interpretation.

## 0. Summary

- **Preregistered verdict: SUPPORTED.** H1 and H2 both hold.
- **H1.** Over 10 eligible shift runs, GOV made **128** post-shift escapes, against **206** for the static twin T1 (same authorization, same probes, never revoked).
  - ρ = 0.621, with a one-sided 95% run-bootstrap upper bound of 0.816 < 1.
- **H2.** In 10 eligible stationary runs:
  - the good class was revoked in **0** runs;
  - GOV's good-class autonomous error was 0.0339, within the 0.10 budget.
- **The whole effect comes from revocation.**
  - The good class was revoked in 6 of 10 shift runs, each time by the P8 recent-window rule, a median of 98 items after the shift (range 70–230).
  - In the 4 runs without revocation, GOV and T1 made identical escapes (65 and 65).
- **Not claimed, and not achieved: budget compliance under the shift.**
  - GOV's whole-run good-class error in the shift arm was 0.1229, above the 0.10 budget.
  - Revocation reduced the *number* of wrong releases. The error rate of the releases made after the shift was essentially that of the static twin (0.2278 vs 0.2291).
- **The effect is smaller than planned.** ρ was 0.621 against 0.46 in planning, and P(revoked) was 6/10 against 0.818.

## 1. What was executed

- **Runs:** 24, all complete: 12 study seeds (0–11) × 2 arms, 630 items each, one fresh agent per run.
  - No failed jobs, no protocol violations, no auto-rejects (S1).
- **Eligibility:** 10 per arm, so the top-up rule was not needed.
  - Seeds 9 and 11 were ineligible in both arms: the first model was rejected. The two arms share an identical pre-shift stream per seed, so this is the same outcome twice.
- **Determinism:** GOV's routing and P on items 1–380 were identical between the arms for 12 of 12 seeds (S1).
- **Frozen model:** a single model version scored every decision in all 20 eligible runs (S1).
- **Nothing was changed** in the plan, configs, GOV or the preregistered analysis. One post-hoc correction to *secondary* event placement is disclosed in §4.

## 2. Primary endpoint (preregistered; EXPERIMENT_PLAN_3.md §8)

| | Post-shift escapes (items 381–630), 10 eligible shift runs |
|---|---|
| GOV | 128 |
| T1: static authorization, same probes, never revoked | 206 |
| T0: static authorization, no probes | 293 |
| TM: margin twin (preregistered code) | 204 |

- **H1:** ρ = ΣAMP/ΣT1 = 0.621. The run-bootstrap one-sided 95% upper bound is 0.816, which is < 1, so **H1 holds**.
- **H2a:** the stationary-arm revocation share is 0.0 (limit 0.10), so **H2a holds**.
- **H2b:** the stationary-arm GOV good-class autonomous error is 0.0339 (limit 0.10), so **H2b holds**.
- **Success = H1 and H2 → SUPPORTED.**
- **For reference:** ρ vs T0 = 0.437; ρ vs TM = 0.627 on the preregistered code, 0.5664 on corrected placement (S7).

**Per run (S2):**

| seed | authorized at item | certified threshold | revoked | items after shift | post-shift probes (errors) | GOV | T1 | T0 |
|---|---|---|---|---|---|---|---|---|
| 0 | 210 | 0.93 | yes | 230 | 35 (6) | 23 | 24 | 31 |
| 1 | 190 | 0.7 | yes | 110 | 26 (6) | 10 | 33 | 51 |
| 2 | 190 | 0.93 | no | – | 37 (5) | 17 | 17 | 22 |
| 3 | 190 | 0.9 | no | – | 50 (6) | 26 | 26 | 32 |
| 4 | 280 | 0.97 | no | – | 14 (0) | 6 | 6 | 6 |
| 5 | 230 | 0.97 | no | – | 26 (5) | 16 | 16 | 21 |
| 6 | 200 | 0.93 | yes | 70 | 12 (5) | 8 | 22 | 31 |
| 7 | 190 | 0.85 | yes | 86 | 17 (5) | 7 | 27 | 43 |
| 8 | 240 | 0.93 | yes | 110 | 17 (5) | 10 | 17 | 26 |
| 10 | 220 | 0.95 | yes | 70 | 10 (5) | 5 | 18 | 30 |

## 3. Secondary observations (preregistered, descriptive)

### 3.1 Revocation (S3)

- **How often:** revoked in **6 of 10** eligible shift runs.
- **Which rule:** all 6 were triggered by the **recent-window rule (P8)**; the cumulative rule did not fire first in any run.
- **When:** 70, 70, 86, 110, 110 and 230 items after the shift (median 98).
- **Timing boundaries:**
  - no revocation before the shift;
  - no re-authorization after a revocation (the class stayed revoked for the rest of each run).
- **Runs that were revoked (6):** post-shift escapes were GOV 63, T1 141, T0 212.
  - Of GOV's 63, 62 occurred before the revocation took effect.
  - One autonomous execution is placed after a revocation. It is the asynchronous boundary of a scheduler tick (§4): the decision was made before the revocation event and recorded after it.
- **Runs that were not revoked (4: seeds 2, 3, 4, 5):** GOV's escapes equal T1's in every run (65 and 65 in total).
  - Their post-shift probes showed 5–6 errors in 26–50 probes in seeds 2, 3 and 5, and 0 in 14 probes in seed 4.
- **Monitoring warnings** (point estimate over budget, no revocation): 7 in the shift arm, 1 in the stationary arm.
- **Stationary arm:** 0 revocations in 10 eligible runs.

### 3.2 Error against the budget (S4, pooled over eligible runs)

| arm | system | pre-shift rate | post-shift rate | whole run |
|---|---|---|---|---|
| shift | GOV | 0.0423 (31/732) | 0.2278 (128/562) | 0.1229 |
| shift | T1 | 0.0423 (31/732) | 0.2291 (206/899) | 0.1453 |
| shift | T0 | 0.041 (43/1050) | 0.2278 (293/1286) | 0.1438 |
| stationary | GOV | 0.0423 (31/732) | 0.028 (30/1070) | 0.0339 |
| stationary | T1 | 0.0423 (31/732) | 0.028 (30/1070) | 0.0339 |
| stationary | T0 | 0.041 (43/1050) | 0.0261 (40/1531) | 0.0322 |

- **Before the shift:** all systems are within budget.
- **After the shift:** every system's executions are wrong about 23% of the time. GOV's whole-run error in the shift arm, 0.1229, exceeds the budget, as planning anticipated (0.116, S8).

### 3.3 Useful autonomy and human burden (S5, eligible runs, 630 items per run)

| arm | system | correct autonomous | wrong autonomous | human-reviewed share |
|---|---|---|---|---|
| shift | GOV | 1135 | 159 | 0.795 |
| shift | T1 | 1394 | 237 | 0.741 |
| shift | T0 | 2000 | 336 | 0.629 |
| stationary | GOV | 1741 | 61 | 0.714 |
| stationary | T1 | 1741 | 61 | 0.714 |
| stationary | T0 | 2498 | 83 | 0.59 |

- **Stationary arm:** consequences cost nothing. GOV equals T1 exactly, because there were no revocations.
- **Shift arm:** revocation returned work to humans. GOV had 1135 correct and 159 wrong autonomous decisions, against 1394 and 237 for T1.
- **The cost of probing:** the difference between T1 and T0 (for example 0.714 vs 0.59 human-reviewed share in the stationary arm).
- **Probe counts:** a mean of 56.2 good-class probes per eligible shift run and 77.9 per stationary run.

### 3.4 Where the escapes came from (S6, shift arm, post-shift)

- **Anomaly type:** logical anomalies account for **112 of GOV's 128** escapes (T1: 180 of 206; T0: 253 of 293). Structural: GOV 16, T1 26, T0 40.
- **Category:** screw_bag (GOV 48, T1 82) and pushpins (GOV 26, T1 45) contribute most. breakfast_box (14 / 21) and juice_bottle (10 / 15) contribute least.

### 3.5 Other preregistered secondaries

- **The defective class:**
  - authorized in 1 of 24 runs (shift, seed 4);
  - never executed autonomously in any run (0 executions).
  - As planned, Experiment 3 is effectively about the release ("good") class.
- **The TM margin twin (S7):**
  - it never certified in 3 of 10 eligible shift runs (seeds 0, 4, 10), which means zero autonomy and zero escapes;
  - it certified at margin 0.0 in seed 1;
  - so ρ vs TM compares GOV partly against a twin that did nothing, and is not a meaningful effect size.

### 3.6 Planning replica against observation (S8)

| quantity | planning | observed |
|---|---|---|
| P(eligible) | 0.838 | 20/24 = 0.8333 |
| P(revoked after shift, eligible) | 0.818 | 6/10 = 0.6 |
| median items to revoke | 100 | 98.0 |
| ratio GOV/T1 (pooled) | 0.46 | 0.621 |
| stationary false revocation | 0.012 | 0/10 |
| shift, GOV whole-run error | 0.116 | 0.1229 |

The replica predicted the timing, the stationary behaviour and the budget overshoot well, but it overestimated how often revocation would happen.

## 4. Deviation: post-hoc correction of event placement (secondary quantities only)

**What happened.**
- The preregistered analysis places authority events on the stream via the simulator's tick log (EXPERIMENT_PLAN_3.md §8).
- GOV's own scheduler also runs STAGE_TICK jobs, and events from those ticks were not in the tick log, so the code dropped them.
- As a result it counted **5** revocations in the shift arm instead of **6**, missing seed 7, which was revoked 86 items after the shift by a scheduler tick. It also evaluated TM on a subset of GOV's evaluations.

**What it does not affect:**
- **Primary endpoint and H1:** unaffected. Escapes come from GOV's decision records; T1 and T0 depend only on the first authorization, which maps through the approved workitem.
- **Reconciliation:** the secondary script recomputes GOV, T1 and T0 escapes independently and asserts equality with the preregistered numbers for every run.
- **H2a:** unaffected. The raw events contain **0** stationary-arm revocations.

**The correction.**
- An event whose tick is not in the log is placed by timestamp, at the last decision recorded before it.
- On every event the tick log does cover, this reproduces the tick placement exactly (431 agree, 0 disagree).
- Corrected values are labelled as such: the revocation count and timing (§3.1), and TM (S7).
- For scheduler-tick events, the placement is exact only to within one in-flight item.

## 5. Interpretation (limited to the endpoints)

**What the experiment shows.**
- **The preregistered claim holds** in this environment: a feature-invisible reliability change, i.e. a new logical failure mode at 30%, on pooled LOCO.
  - GOV's lifecycle withdrew authority it had granted and made fewer wrong autonomous releases after the change than the same authorization held statically with the same probes.
  - It did not withdraw authority when nothing changed.
- **The comparison isolates consequences.** T1 has GOV's authorization, threshold, model and probe schedule, so the whole difference is attributable to revocation. The per-run table confirms it: GOV and T1 are identical wherever no revocation happened.
- **The recent-window rule did the work.** Every revocation came from P8, the rule added after planning showed that the cumulative monitor dilutes a change.

**What it does not show.**
- **It does not show risk-controlled autonomy under change.**
  - Detection took a median of 98 items and roughly 17 post-shift probes. The escapes made in that time (62 in the 6 revoked runs) pushed GOV's whole-run error above the budget.
  - Probe-based monitoring bounds exposure; it does not prevent it.
- **Detection is not reliable at this probe budget.** 4 of 10 changes went undetected over 250 items. In one detected run (seed 0) detection came too late to matter (23 vs 24 escapes).
  - The 20-probe window needs 5 errors inside one window at a 10% budget. With a true post-shift slice error near 23%, the exact power per full window lies between 0.37 (true error 0.20) and 0.585 (0.25) (planning table T3).
- **The effect size is modest and uncertain:** ρ = 0.621, upper bound 0.816, and not the ~0.46 planning suggested.

## 6. Discussion: possible explanations (not established here)

1. **Why revocation was less frequent than planned (6/10 vs 0.818).** The replica used a logistic proxy for GOV's model and a slightly different grid. Real GOV certified at higher thresholds in several runs (0.93–0.97), which gives a smaller authorized slice and fewer post-shift probes (as few as 10–17 in revoked runs, 14 in seed 4). Fewer probes mean less power.
2. **Why the error rate of executions is unchanged.** The model sees only score features, and logical anomalies are indistinguishable by score. Nothing in GOV's decision can make an individual release safer; only withdrawing the authority helps. That is the design premise, and the data are consistent with it (112 of 128 escapes are logical).
3. **What would reduce exposure,** each a hypothesis for future work:
   - a higher probe rate after authorization (at a burden cost);
   - a smaller window or a sequential test (CUSUM, SPRT) instead of a fixed-window lower bound;
   - downstream outcome feedback (the confirmed-failure path, off by design here);
   - a declared change signal where one exists (sketch E-C).

## 7. Threats to validity

In addition to EXPERIMENT_PLAN_3.md §11:
- **Few runs.** 10 eligible runs per arm, from one reused image pool. Inference is conditional on the pool, and the bootstrap CI reflects run-level variation only.
- **A constructed shift.** Change point, type and prevalence (0.10 → 0.40) are by design. External validity is limited to "a new, score-invisible failure mode appears". MVTec AD 2 remains the natural follow-up.
- **Idealized oracle and frozen model.** Retraining and requalification on model change are out of scope.
- **The loose 0.10 budget,** set by evidence supply.
- **The post-hoc event-placement correction** (§4) affects secondary quantities only, and is reported beside the preregistered values.

## 8. Artifacts

- **Runs:** `results/exp3/runs/`, with per-run manifests, decisions, simulator events and RLHF events, plus `study_log.jsonl`.
- **Primary:** `results/exp3/aggregate/exp3_primary.json` and `exp3_runs.csv` (preregistered `analysis/exp3_analysis.py`).
- **Secondary:** `results/exp3/aggregate/secondary_tables.md`, `secondary_runs.csv` and `fig_exp3_cumulative_escapes.png` (`analysis/exp3_secondary.py`).
- **Pilot:** `results/exp3/pilot/`.
- **Planning:** `results/exp3_planning/`.
