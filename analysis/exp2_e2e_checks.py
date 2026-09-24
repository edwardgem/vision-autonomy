"""Experiment 2 E2E acceptance checks (EXPERIMENT_PLAN_2.md section 8). Engineering validation only - never study evidence.

Usage: python -m analysis.exp2_e2e_checks <exp2_run_dir> [--ref <exp1_e2e_run_dir>]
"""
import argparse, glob, json
from pathlib import Path
import numpy as np
import pandas as pd
from sim.amp_db import AmpDB
from sim.amp_client import load_env

MODELS = Path("/Users/edwardc/Projects/amp-backend/.amp-rlhf/models")


def load(run_dir):
    d = Path(run_dir)
    m = json.loads((d / "manifest.json").read_text())
    df = pd.read_csv(d / "amp_decisions.csv").sort_values("stream_position").reset_index(drop=True)
    ev = [json.loads(l) for l in open(d / "amp_rlhf_events.jsonl")]
    oe = [json.loads(l) for l in open(d / "amp_events.jsonl")]
    return m, df, ev, oe


def first_model(org, agent):
    vs = sorted((MODELS / org / agent).glob("v_*/model_artifact.json"))
    return json.loads(vs[0].read_text()) if vs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--ref", default=None)
    a = ap.parse_args()
    m, df, ev, oe = load(a.run_dir)
    org, agent = m["org_id"], m["agent_name"]
    db = AmpDB(org)
    res = {"agent": agent, "run_dir": a.run_dir}

    # -- summary / generic E2E checks
    s = m["summary"]
    res["generic"] = {"reconcile_ok": s["reconcile_ok"], "auto_rejects": s["auto_rejects"], "failed_jobs": len(s["failed_jobs"]),
                      "violations": sum(1 for e in oe if e["event"] == "violation"), "worker_training_seed": m["worker_training_seed"],
                      "amp_testing_mode": m["amp_testing_mode"], "admin_approvals": len(s["admin_approvals"]),
                      "params_basis": m["amp_rlhf_params"].get("stage1_agreement_basis"),
                      "first_stage1_pos": s["first_stage1_pos"], "first_stage2_pos": s["first_stage2_pos"],
                      "by_stage_routing": s["by_stage_routing"]}

    # -- parameter effect: AMP-stored cumulative counts == recommendation-basis recomputation over ALL Stage 1 rows
    st = db.agent_state(agent)
    md = st["metadata"]
    s1 = df[(df.amp_stage == 1) & df.amp_recommended_decision.isin(["approve", "reject"])]
    rec_count, rec_agree = len(s1), int((s1.amp_recommended_decision == s1.oracle_response).sum())
    s1x = df[(df.amp_stage == 1) & df.amp_approval_probability.notna()]
    exe_agree = int(((s1x.amp_approval_probability >= s1x.amp_threshold_used.astype(float)).map({True: "approve", False: "reject"})
                     == s1x.oracle_response).sum())
    res["parameter_effect"] = {"stored_basis": md.get("stage1_agreement_basis"),
                               "stored_count": md.get("stage1_agreement_count"), "stored_agree": md.get("stage1_agreement_agree"),
                               "recommendation_recompute": [rec_count, rec_agree],
                               "execution_threshold_recompute": [len(s1x), exe_agree],
                               "match_recommendation": md.get("stage1_agreement_count") == rec_count and md.get("stage1_agreement_agree") == rec_agree}

    # -- recent-20 definition unchanged: AMP's last Stage 1 recent rate == stored-recommendation recomputation over last 20 Stage 1 rows
    dbg = [e["payload"]["decision_debug"] for e in ev if e["event_type"] == "STAGE_TICK_SUMMARY"
           and (e["payload"].get("decision_debug") or {}).get("stage") == 1 and e["payload"]["decision_debug"].get("stage1_recent_rows")]
    if dbg:
        last = dbg[-1]
        n = int(last["stage1_recent_rows"])
        # the last Stage 1 tick's window: rows up to the last Stage 1 row
        tail = s1.tail(n)
        rr = float((tail.amp_recommended_decision == tail.oracle_response).mean())
        res["recent20"] = {"amp_recent_rate": last["stage1_recent_rate"], "recompute_recommendation": rr,
                           "match": abs(rr - float(last["stage1_recent_rate"])) < 1e-9}
    # gate history
    g = [e["payload"]["decision_debug"] for e in ev if e["event_type"] == "STAGE_TICK_SUMMARY" and (e["payload"].get("decision_debug") or {}).get("stage") == 1]
    res["gate_history"] = [{k: x.get(k) for k in ("stage1_agreement_basis", "stage1_sample_size_met", "stage1_primary_met", "stage1_stability_met",
                                                   "stage1_safety_met", "stage1_hard_gates_all_met", "stage1_recent_rate")}
                           for x in g if x.get("stage1_sample_size_met")][:6]

    # -- Stage 2 execution still P >= 0.90
    s2 = df[df.amp_stage == 2]
    if len(s2):
        auto, hum = s2[s2.routing == "autonomous"], s2[s2.routing == "hitl"]
        res["stage2"] = {"items": len(s2), "autonomous": len(auto), "human": len(hum),
                         "threshold_used_values": sorted(set(float(x) for x in s2.amp_threshold_used.dropna())),
                         "min_p_autonomous": float(auto.amp_approval_probability.min()) if len(auto) else None,
                         "autonomous_below_0.90": int((auto.amp_approval_probability < 0.90).sum()),
                         "human_non_probe_at_or_above_0.90": int(((hum.amp_approval_probability >= 0.90) & ~hum.probe_forced_human).sum()),
                         "escalations": hum.escalation_reason.value_counts().to_dict()}

    # -- retrain / re-entry trace (F4)
    types = [e["event_type"] for e in ev]
    stages = df.amp_stage.to_numpy()
    reentry_pos = [int(df.stream_position[i]) for i in range(1, len(stages)) if stages[i] < stages[i - 1]]
    res["retrain_reentry"] = {"candidates": types.count("MODEL_CANDIDATE_READY"), "activations": types.count("MODEL_ACTIVATED"),
                              "upgrade_proposals": [e["payload"].get("status") for e in ev if e["event_type"] == "MODEL_UPGRADE_PROPOSAL"],
                              "stage_regressions_at": reentry_pos,
                              "stage2_promotion_workitems": types.count("STAGE2_PROMOTION_WORKITEM_CREATED"),
                              "final_stage": st["stage"], "final_stage1_eval_rows": st["stage1_eval_rows"],
                              "stored_promotion_approved": md.get("stage1_promotion_approved"),
                              "final_cumulative_rate": md.get("stage1_agreement_rate")}

    # -- determinism vs Experiment 1 E2E reference
    if a.ref:
        rm, rdf, _, _ = load(a.ref)
        j = df.merge(rdf, on="stream_position", suffixes=("_e2", "_e1"))
        assert (j.image_id_e2 == j.image_id_e1).all(), "streams differ"
        same_stage = j[j.amp_stage_e2 == j.amp_stage_e1]
        div = j[j.amp_stage_e2 != j.amp_stage_e1]
        first_div = int(div.stream_position.min()) if len(div) else None
        pre = j if first_div is None else j[j.stream_position < first_div]
        both = pre[pre.amp_approval_probability_e2.notna() & pre.amp_approval_probability_e1.notna()]
        diff = (both.amp_approval_probability_e2 - both.amp_approval_probability_e1).abs()
        m2, m1 = first_model(org, agent), first_model(rm["org_id"], rm["agent_name"])
        wdiff = None
        if m2 and m1 and m2["feature_names"] == m1["feature_names"]:
            wdiff = float(np.max(np.abs(np.array(m2["weights"]) - np.array(m1["weights"])))) + abs(m2["bias"] - m1["bias"])
        res["determinism"] = {"reference": rm["agent_name"], "first_stage_divergence_pos": first_div,
                              "compared_scored_items_before_divergence": int(len(both)),
                              "max_abs_prob_diff": float(diff.max()) if len(both) else None,
                              "missing_score_mismatch": int((pre.amp_approval_probability_e2.isna() != pre.amp_approval_probability_e1.isna()).sum()),
                              "routing_mismatch_before_divergence": int((pre.routing_e2 != pre.routing_e1).sum()),
                              "first_model_same_features": bool(m2 and m1 and m2["feature_names"] == m1["feature_names"]),
                              "first_model_max_param_diff": wdiff,
                              "pass": bool(len(both) and float(diff.max()) < 1e-9)}
    print(json.dumps(res, indent=1, default=str))
    out = Path(a.run_dir) / "e2e_acceptance.json"
    out.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
