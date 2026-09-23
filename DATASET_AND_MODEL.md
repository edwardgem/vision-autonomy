# DATASET_AND_MODEL.md — Component 1 findings

Status: for review (2026-09-23). Everything below was measured on the downloaded data, not taken from documentation,
unless marked *(docs)*.

## 1. Dataset: MVTec LOCO AD

**Source / integrity.** anomalib's direct link to `mvtec_loco_anomaly_detection.tar.xz` (6,126,996,224 bytes);
SHA-256 `9e7c84db…e687` **matches** anomalib's published hash. Stored in `data/MVTec_LOCO/` (gitignored).
Note: `curl` cannot resolve `www.mydrive.ch` on this machine; workaround in HANDOFF.md.

**License / citation.** CC BY-NC-SA 4.0 (non-commercial; research use fine; derived tables need attribution and
share-alike). Cite Bergmann, Batzner, Fauser, Sattlegger, Steger, *Beyond Dents and Scratches: Logical Constraints in
Unsupervised Anomaly Detection and Localization*, IJCV 130 (2022), doi:10.1007/s11263-022-01578-9.

**Structure.** `<category>/{train/good, validation/good, test/{good,logical_anomalies,structural_anomalies}, ground_truth/{logical,structural}_anomalies/<image_stem>/*.png}`.
- `train` and `validation` contain **normal images only**. Anomalies exist only in `test`.
- Ground truth is **pixel masks** for anomalous test images (some images have several masks). There is no image-level
  label file: the image-level label is the folder name (`good` vs `*_anomalies`). Mask dirs match test images 1:1 (verified).
- Native image sizes differ per category (1600×1280, 800×1600, 1700×1000, 1600×1100, 1700×850).

**Counts (measured, `results/dataset_manifest.json`).**

| Category | Train good | Val good | Test good | Test logical | Test structural | Test total |
|---|---|---|---|---|---|---|
| breakfast_box | 351 | 62 | 102 | 83 | 90 | 275 |
| juice_bottle | 335 | 54 | 94 | 142 | 94 | 330 |
| pushpins | 372 | 69 | 138 | 91 | 81 | 310 |
| screw_bag | 360 | 60 | 122 | 137 | 82 | 341 |
| splicing_connectors | 360 | 60 | 119 | 108 | 85 | 312 |
| **Total** | **1,778** | **305** | **575** | **561** | **432** | **1,568** |

- Test set is **63.3 % anomalous** (36.7 % good; 35.8 % logical; 27.6 % structural). Anomaly prevalence is far above
  a realistic production base rate; results must be described as such.
- **Discrepancy:** on-disk PNG total is 3,651 (1,778 + 305 + 1,568); MVTec's page states 3,644. Cause unknown
  (7 images); does not affect the experiment but should not be quoted in the paper as 3,644 without a footnote.

**Structural vs logical.** Structural = local defects (dents, scratches, contamination). Logical = constraint violations
(wrong count / position / combination of otherwise normal parts). Type is available **only** as the test folder name
and is therefore analysis-only metadata (see leakage rule in HANDOFF.md).

**Transformations needed.** (1) Build an image-level table from folder names: `image_id`, `category`, `anomaly_type`
∈ {good, logical, structural}, `ground_truth` ∈ {good, defective}. (2) Nothing else — PatchCore consumes the PNGs
directly (resize 256×256). No masks are needed for image-level decisions; pixel GT is unused.

## 2. Model: PatchCore (anomalib 2.6.2)

**Configuration (all anomalib defaults; nothing tuned).** `wide_resnet50_2` (ImageNet pretrained), layers
`layer2`+`layer3`, coreset ratio 0.1, 9 nearest neighbours, resize to 256×256 **without** centre crop, one model per
category fitted on `train/good` only. Torch 2.14.0, CPU, seed 0. Fit ≈ 5–6.5 min/category, all five ≈ 36 min.

**Output.** One continuous image-level `pred_score` per image (higher = more anomalous). Scores are **not comparable
across categories** (val-good mean ranges 30.5–48.8), so any threshold or model-confidence signal must be per-category
or per-category normalised.

**Label-leakage trap avoided.** anomalib's default post-processor fits an F1-optimal threshold on labelled data
(`F1AdaptiveThreshold` on `gt_label`). We disable post-processing/evaluator and use **raw scores only**. Its
`pred_label`/threshold must never be used.

**Raw scores:** `results/patchcore_scores.csv` (305 validation + 1,568 test rows; columns `image_id, category, split,
anomaly_type, ground_truth, raw_score`). Run metadata: `results/patchcore_run_meta.json`.

**Sanity check — image-level AUROC on test (descriptive only):**

| Category | All | Good vs logical | Good vs structural |
|---|---|---|---|
| breakfast_box | 0.857 | 0.864 | 0.851 |
| juice_bottle | 0.925 | 0.908 | 0.950 |
| pushpins | 0.741 | 0.696 | 0.792 |
| screw_bag | 0.704 | **0.611** | 0.861 |
| splicing_connectors | 0.833 | 0.782 | 0.898 |

Consistent with the literature: PatchCore is weaker on logical anomalies; `screw_bag` logical and `pushpins` are near
"barely better than chance". This is a *feature* for the experiment: it gives regions where AMP should refuse autonomy.

## 3. Recommended configuration

- **Dataset:** MVTec LOCO AD, all 5 categories, the **1,568-image test split** is the evaluation stream.
- **Model:** PatchCore exactly as above; per-category models; raw scores frozen in `patchcore_scores.csv` so the
  vision layer runs **once** and every experimental condition consumes identical inputs (also keeps AMP and vision
  cleanly separated and the runs reproducible).
- **Validation split (305 good images)** is the only non-test data with scores; it is normal-only.

## 4. Material uncertainties / decisions needed before Component 2

1. **Threshold calibration source.** Validation (good-only) can support only "quantile of normal" thresholds, not
   an F1-optimal one. Check done (normal images only, no anomaly labels used): validation-good and test-good score
   distributions differ modestly (KS p = 0.10, 0.038, 0.024, 0.004, 0.36 for the five categories; `screw_bag` mean is
   1.25 higher on validation, ≈0.6 SD). So validation-only thresholds carry a small, known distribution shift.
   Alternative — seeded calibration slice of test — shrinks the evaluation stream and only 575 test-good exist.
   **I deliberately did not evaluate any thresholded accuracy on test labels**, to avoid informing the choice.
2. **Only 1,568 evaluation images at 63 % anomaly prevalence.** Whether AMP can reach Stage 2 and still leave a
   post-promotion evaluation window depends on gate settings; needs a feasibility check in Component 2/3.
3. **Non-square resize.** Default 256×256 resize distorts `juice_bottle` (1:2), `splicing_connectors` (2:1), etc.
   Kept as the anomalib default per "do not optimise"; disclose in the paper.
4. **Dataset count discrepancy** 3,651 vs 3,644 (§1) — cosmetic.
5. **Seed sensitivity.** Coreset selection is randomised; only seed 0 has been run. If we want an error bar on the
   vision layer, re-run seeds (36 min each) — recommend deciding in the plan.
6. **Second-dataset stretch goals (VisA, MVTec AD 2)** untouched, as instructed.

## 5. Reproduce

```bash
python3.12 -m venv .venv && source .venv/bin/activate && pip install anomalib==2.6.2
# download + extract LOCO to data/MVTec_LOCO (see HANDOFF.md for the DNS workaround), then:
python scripts/inspect_dataset.py                 # -> results/dataset_manifest.json
TQDM_DISABLE=1 python scripts/score_patchcore.py --seed 0   # -> results/patchcore_scores.csv (~36 min CPU)
```
