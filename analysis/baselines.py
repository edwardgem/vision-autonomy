"""Conditions A (human oracle), B (model only), C (static HITL / selective prediction) as per-decision CSVs.
Deterministic functions of results/inputs/decision_records.csv; independent of stream order, so identical across seeds."""
import sys
from analysis.common import *

rec = load_records()
out = ROOT / "results" / "baselines"; out.mkdir(parents=True, exist_ok=True)
AMP_NA = {c: "n/a" for c in ["amp_stage", "amp_model_version", "amp_approval_probability", "amp_recommended_decision",
                             "probe_forced_human", "hard_blocked", "decision_point_id", "workitem_id", "instance_id"]}
conds = {"oracle": ("A_human_oracle", condition_oracle(rec)),
         "model_only": ("B_model_only", condition_model_only(rec)),
         "static_hitl": (f"C_static_hitl_delta{DELTA}", condition_static(rec, DELTA))}
for fname, (label, d) in conds.items():
    d = d.copy()
    d.insert(0, "condition", label)
    d["escalation_reason"] = np.where(d.routing == "hitl", "static_low_margin" if fname == "static_hitl" else
                                      ("human_oracle_reviews_all" if fname == "oracle" else "n/a"), "n/a")
    d["oracle_response"] = np.where(d.routing == "hitl", np.where(d.proposal == d.ground_truth, "approve", "reject"), "n/a")
    for k, v in AMP_NA.items():
        d[k] = v
    d.to_csv(out / f"{fname}.csv", index=False, float_format="%.8f")
    m = metrics(d)
    print(f"{label:28s} acc={m['accuracy']:.4f} FA={m['fa_rate']:.4f} FR={m['fr_rate']:.4f} auto={m['autonomous_rate']:.4f} "
          f"auto_err={m['autonomous_error_rate']:.4f}")
