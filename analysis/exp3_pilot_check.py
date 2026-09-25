"""Experiment 3 pilot check (EXPERIMENT_PLAN_3.md section 10). Criteria fixed BEFORE the pilot results were seen
(committed while the pilots were running). Only two adjustments are permitted; nothing else may change.

  ADJ-1 Stage 0 length:  150 -> 200 iff the first model was rejected (no MODEL_ACTIVATED) in either pilot run.
  ADJ-2 Grid lower extent: append [0.75, 0.70] to both classes' grids iff the good class was certified at the current
        grid floor (0.80) in either pilot run.
Everything else (budget, probe rate, shift, monitoring rule, endpoints, comparators, success rule, sample size) is
reported for information only and is NOT adjustable on the basis of this check.
Usage: python -m analysis.exp3_pilot_check [--pilot-dir results/exp3/pilot]
"""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from analysis.exp3_analysis import analyse_run, load_run, ROOT

GRID_FLOOR = 0.80
PLANNING = {"P(first model accepted)": 0.87, "authorization item q10/q50/q90": [190, 210, 310],
            "share certified at grid floor": 0.406, "mean probes per run": 53.4,
            "P(revoked after shift | eligible)": 0.818, "median items to revoke": 100,
            "stationary P(false revocation)": 0.012}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--pilot-dir", default="results/exp3/pilot"); a = ap.parse_args()
    pol = json.loads((ROOT / "config/exp3/amp_policy_exp3_v1.json").read_text())
    mon = pol["autonomy_ops"]["authority"]["monitoring"]
    rows, lines = [], []
    for m in sorted((ROOT / a.pilot_dir).glob("*/manifest.json")):
        o = analyse_run(m.parent, mon); man, r, _, rl = load_run(m.parent)
        g = r[(r.proposal == "good") & r.amp_approval_probability.notna()]
        o["P_good_quantiles_q10_q50_q90"] = [round(float(x), 4) for x in np.quantile(g.amp_approval_probability.astype(float), [.1, .5, .9])] if len(g) else None
        o["share_P_good_below_floor"] = round(float((g.amp_approval_probability.astype(float) < GRID_FLOOR).mean()), 3) if len(g) else None
        o["good_certified_at_floor"] = o["good_auth_thr"] is not None and abs(o["good_auth_thr"] - GRID_FLOOR) < 1e-9
        o["probes_total"] = int((r.governance_outcome == "probe").sum())
        o["qualification_evaluations_good"] = sum(1 for e in rl if e["event_type"] == "AUTHORITY_QUALIFICATION_EVALUATED" and e["payload"].get("action_class") == "good")
        rows.append(o)
    df = pd.DataFrame(rows)
    adj1 = bool((~df.first_model_accepted).any())
    adj2 = bool(df.good_certified_at_floor.any())
    res = {"ADJ-1 stage0 150->200": adj1, "ADJ-2 grid + [0.75, 0.70]": adj2, "planning_reference": PLANNING,
           "runs": df.to_dict(orient="records")}
    out = ROOT / a.pilot_dir / "pilot_check.json"
    out.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
