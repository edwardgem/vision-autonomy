"""Shared metric definitions (EXPERIMENT_PLAN.md section 7). Positive class = defective."""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config" / "experiment_v1.json").read_text())
CATS = CFG["dataset"]["categories"]
SEEDS = CFG["streams"]["stream_seeds"]
DELTA = float(CFG["static_hitl"]["primary_delta_sigma"])
MIN_N = int(CFG["reporting"]["min_n_for_rate"])
TYPES = ["good", "structural", "logical"]


def load_records():
    return pd.read_csv(ROOT / "results" / "inputs" / "decision_records.csv")


def wilson(k, n, z=1.959964):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def add_flags(df, final_col="final_decision"):
    """correct / FA / FR flags from final decision vs ground truth."""
    df = df.copy()
    gt_def, fin_def = df.ground_truth == "defective", df[final_col] == "defective"
    df["correct"] = df[final_col] == df.ground_truth
    df["false_acceptance"] = (~fin_def) & gt_def
    df["false_rejection"] = fin_def & (~gt_def)
    return df


def metrics(df):
    """df needs: ground_truth, final_decision, routing ('autonomous'|'hitl'), correct, false_acceptance, false_rejection."""
    n = len(df)
    gt_def, gt_good = int((df.ground_truth == "defective").sum()), int((df.ground_truth == "good").sum())
    auto = df[df.routing == "autonomous"]
    fa, fr = int(df.false_acceptance.sum()), int(df.false_rejection.sum())
    err = int((~df.correct).sum())
    a_err = int((~auto.correct).sum())
    a_fa, a_fr = int(auto.false_acceptance.sum()), int(auto.false_rejection.sum())
    return {
        "n": n, "accuracy": (n - err) / n if n else np.nan, "errors": err,
        "fa_count": fa, "fa_rate": fa / gt_def if gt_def else np.nan, "n_gt_defective": gt_def,
        "fr_count": fr, "fr_rate": fr / gt_good if gt_good else np.nan, "n_gt_good": gt_good,
        "autonomous_count": len(auto), "autonomous_rate": len(auto) / n if n else np.nan,
        "hitl_count": n - len(auto), "hitl_rate": (n - len(auto)) / n if n else np.nan,
        "autonomous_errors": a_err, "autonomous_error_rate": a_err / len(auto) if len(auto) else np.nan,
        "autonomous_fa": a_fa, "autonomous_fr": a_fr,
    }


# ---- offline conditions A-C -------------------------------------------------------------------------------------------
def condition_oracle(rec):
    d = rec.copy(); d["routing"] = "hitl"; d["final_decision"] = d.ground_truth
    return add_flags(d)


def condition_model_only(rec):
    d = rec.copy(); d["routing"] = "autonomous"; d["final_decision"] = d.proposal
    return add_flags(d)


def condition_static(rec, delta):
    d = rec.copy()
    d["routing"] = np.where(d.margin_abs < delta, "hitl", "autonomous")
    d["final_decision"] = np.where(d.routing == "hitl", d.ground_truth, d.proposal)
    return add_flags(d)
