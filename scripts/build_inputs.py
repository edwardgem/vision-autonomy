"""Build results/inputs/decision_records.csv (plan section 3) from frozen PatchCore scores + frozen calibration."""
import json, hashlib
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
cal = json.loads((ROOT / "config" / "calibration_v1.json").read_text())["per_category"]
d = pd.read_csv(ROOT / "results" / "patchcore_scores.csv")
t = d[d.split == "test"].copy()
t["tau"] = t.category.map(lambda c: cal[c]["tau"])
t["mu_val"] = t.category.map(lambda c: cal[c]["mu_val"])
t["sigma_val"] = t.category.map(lambda c: cal[c]["sigma_val"])
t["proposal"] = (t.raw_score >= t.tau).map({True: "defective", False: "good"})
t["predicted_class"] = t.proposal
t["score_z"] = (t.raw_score - t.mu_val) / t.sigma_val
t["margin_abs"] = (t.raw_score - t.tau).abs() / t.sigma_val
t["model_confidence"] = t.margin_abs
cols = ["image_id", "category", "anomaly_type", "ground_truth", "raw_score", "tau", "mu_val", "sigma_val",
        "predicted_class", "proposal", "score_z", "margin_abs", "model_confidence"]
t = t.sort_values("image_id")[cols]
out = ROOT / "results" / "inputs" / "decision_records.csv"
t.to_csv(out, index=False, float_format="%.8f")
print(len(t), "rows;", out, hashlib.sha256(out.read_bytes()).hexdigest()[:16])
print(t.groupby("category").size().to_dict())
