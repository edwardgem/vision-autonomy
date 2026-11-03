# Policy-Governed Progressive Autonomy for Vision Agents

Research code, preregistered plans, per-decision run records and analyses for a study of **when a vision agent should
be allowed to act on its own predictions without human review**. The accompanying paper has been accepted at
CVC 2027.

## Motivation

AI agents no longer only generate content. They plan, invoke tools and take actions. When an agent acts, a mistake no
longer ends as a wrong answer: it becomes an operational, financial, physical or social consequence. Deploying agents
responsibly therefore requires governance that makes agent activity observable, keeps decisions accountable, and
retains meaningful human oversight as autonomy increases. The premise of this work is that **autonomy should not be
assumed at deployment. It should be earned from validated evidence and remain subject to human oversight afterwards.**

This matters most once agents act on what they see. Vision-language-action systems couple perception directly to
action, and so do systems in autonomous driving, robotic manipulation, drones and industrial inspection. A model can
recognize a scene very well and still be too unreliable for unrestricted action: **perception capability does not
imply decision authority.** We therefore separate two questions that are usually conflated:

- the **vision model** answers a domain question, e.g. *is this part good or defective?*;
- an independent **governance layer** answers an authority question: *has the agent earned the right to execute this
  particular proposed action without human review?* It is not a second classifier and never overrides the proposal.
  Without authority, it routes the decision to a human or to a policy-defined safe fallback.

Industrial visual inspection makes this concrete. It has objective ground truth and asymmetric consequences:
releasing a defective part is a different failure from scrapping a good one. In our testbed the fixed detector's
proposals are correct for only 68% of test images, and their reliability differs sharply by action. A *defective*
proposal is wrong 5.1% of the time; a *good* (release) proposal is wrong 46.4% of the time. A single, agent-level grant
of autonomy would treat both actions as equally trustworthy.

## Research questions and findings

The governance lifecycle is **Learn → Qualify → Authorize → Monitor → Requalify**. Authority is certified per action
class with an exact one-sided Clopper–Pearson bound on the error of the decisions it would authorize, applied to each
proposal, monitored with human-reviewed probes, and revoked when the risk budget is violated. Automatic mechanisms can
only tighten authority; loosening it requires new evidence and human approval.

| | Question | Result |
|---|---|---|
| **RQ1** (Experiment 1) | Does learned decision reliability translate into autonomous authority under stage-based qualification? | Not by itself. The learned probability separated correct from incorrect proposals (AUROC 0.70–0.84), but authority was granted in 1 of 25 runs. The near-oracle accuracy of 0.997 reflected 98.1% human review. |
| **RQ2** (Experiment 2) | Are qualification of an operating state and authorization of an individual action separable, and is a confidence threshold enough to make authority selective? | Separable. Changing only the qualification rule raised promotion to 9 of 25 runs, with the per-decision threshold unchanged. The equal-coverage comparison with a static threshold was inconclusive, and one uninformative model made the threshold non-selective. Authority emerged almost only for *rejecting* parts (336 of 337 executions outside that run). |
| **RQ3** (Experiment 3) | When the reliability of an authorized action degrades, is authority withdrawn in time, without false withdrawal when reliability is stable? | **Preregistered verdict: supported.** After an unannounced new failure mode appeared, revocation cut wrong autonomous releases from 206 (static twin with identical authorization and probes) to 128, ρ = 0.621 (one-sided 95% upper bound 0.816), with no revocation in the stationary arm. It did **not** keep risk within budget during the change: 4 of 10 changes went undetected, and the post-change error was 0.23. |

The contribution is the governance mechanism and its empirical characterization, not a new computer-vision model.

## Setup

- **Dataset:** [MVTec LOCO AD](https://www.mvtec.com/company/research/datasets/mvtec-loco), all 5 categories. The test
  split (1,568 images, 63.3% anomalous) is the evaluation stream. The dataset is **not** included; download it to
  `data/MVTec_LOCO/` (see `DATASET_AND_MODEL.md`).
- **Perception (fixed):** PatchCore (anomalib 2.6.2 defaults, seed 0), one model per category, trained on normal
  images only. Raw scores are frozen in `results/patchcore_scores.csv`. Thresholds come from validation-normal
  quantiles (`config/calibration_v1.json`); no test label is used for any choice.
- **Governance:** AMP, an independent governance platform (a separate system, not in this repository), driven by the
  simulator in `sim/`. Human reviewers are simulated by a ground-truth oracle.
- **Preregistration:** each experiment's plan and frozen configuration were committed and tagged before its study runs.

| Tag | Experiment |
|---|---|
| `prereg-v1`, `prereg-v1.1` | Experiment 1 (`EXPERIMENT_PLAN.md`, amendments inside) |
| `prereg-exp2-v1` | Experiment 2 (`EXPERIMENT_PLAN_2.md`) |
| `prereg-exp3-v1` | Experiment 3 (`EXPERIMENT_PLAN_3.md`) |

## Repository layout

| Path | Contents |
|---|---|
| `EXPERIMENT_PLAN*.md` | Preregistered plans (1–3), with amendments and decision records |
| `RESULTS*.md` | Results for Experiments 1–3: observations, then interpretation, then discussion; errata are appended, never silent |
| `DATASET_AND_MODEL.md` | Dataset inspection, PatchCore configuration, calibration decisions |
| `AMP_AUTHORITY_DESIGN.md`, `AUTHORITY_READINESS.md`, `TARGET_MODEL_REVIEW.md`, `AMP_ISSUES.md` | Design and review of the authority lifecycle, and platform issues found by the experiments |
| `E2E_REPORT.md` | Engineering acceptance tests of the simulator against the platform |
| `config/` | Frozen calibration, policies and experiment configs (per experiment; SHA-256 recorded in every run manifest) |
| `scripts/` | Dataset inspection, PatchCore scoring, construction of the frozen decision records |
| `sim/` | Simulator and study drivers that stream decisions through the governance platform |
| `analysis/` | Baselines, aggregation, preregistered endpoint analyses, Experiment 3 planning replica and self-test |
| `regression/` | Legacy-replay regression of Experiments 1–2 against the platform's authority mode |
| `results/` | Per-decision run records (`runs/`, `exp2/runs/`, `exp3/runs/`), aggregates, tables and figures |
| `paper/figures/` | Scripts that regenerate every figure in the paper from committed results |

## Reproducing

**From the committed results** (no dataset or platform needed). Python 3.12 with numpy, pandas, scipy, scikit-learn
and matplotlib:

```bash
python -m analysis.baselines          # conditions A-C (oracle, model only, static HITL)
python -m analysis.aggregate          # Experiment 1 tables T1-T5, figures
python -m analysis.aggregate_exp2     # Experiment 2 primary endpoint and tables
python -m analysis.exp3_analysis --runs-dir results/exp3/runs   # Experiment 3 preregistered endpoint (H1, H2)
python -m analysis.exp3_secondary     # Experiment 3 secondary tables
python paper/figures/sec3_figures.py  # paper figures (see paper/figures/README.md)
python paper/figures/sec4_exp12_figures.py
python paper/figures/sec4_exp3_figures.py
python -m analysis.test_cp_bounds     # tests of the Clopper-Pearson bounds
python -m analysis.test_exp3_analysis # self-test of the Experiment 3 analysis on a synthetic run
```

The Clopper–Pearson bounds in `analysis/cp_bounds.py` use the same algorithm as the governance platform, so
qualification and revocation decisions recomputed here match the platform's exactly.

**From the images** (needs the dataset and `anomalib==2.6.2`; about 36 min on CPU):

```bash
python scripts/inspect_dataset.py                          # -> results/dataset_manifest.json
TQDM_DISABLE=1 python scripts/score_patchcore.py --seed 0  # -> results/patchcore_scores.csv
python scripts/build_inputs.py                             # -> results/inputs/decision_records.csv
```

**New study runs** need a running instance of the governance platform and its RLHF workers
(`RLHF_TRAINING_SEED=vision-loco-v1`). See the preregistered plans for the exact procedure.

## Limitations

MVTec LOCO AD is a controlled benchmark with an anomaly-heavy test split, and the Experiment 3 change is constructed.
Reviewers are simulated as perfect and instantaneous. The 0.10 risk budget was set by the available evidence, not by
industrial requirements. PatchCore is used in a single fixed configuration. See the threats-to-validity sections of
each `RESULTS*.md`.

## License

- **Code** (`analysis/`, `sim/`, `scripts/`, `regression/`, `paper/figures/`): [Apache License 2.0](LICENSE).
- **Data derived from MVTec LOCO AD** (everything under `results/`, including scores, decision records, tables and
  figures): the dataset's license, **CC BY-NC-SA 4.0** (attribution, non-commercial, share-alike). The dataset itself
  is not redistributed here.
- **The governance platform** that the simulator drives is a separate system and is not covered by this repository.

## Citation

Please cite the dataset:

> Bergmann, P., Batzner, K., Fauser, M., Sattlegger, D., Steger, C.: Beyond Dents and Scratches: Logical Constraints
> in Unsupervised Anomaly Detection and Localization. International Journal of Computer Vision 130, 947–969 (2022).
> doi:10.1007/s11263-022-01578-9

PatchCore: Roth, K., et al.: Towards Total Recall in Industrial Anomaly Detection. In: CVPR 2022.

A citation for the paper will be added once the proceedings reference is available.
