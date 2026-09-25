"""Self-test for analysis/exp3_analysis.py on a synthetic run with known answers. python -m analysis.test_exp3_analysis"""
import json, tempfile
from pathlib import Path
import numpy as np
from analysis import exp3_analysis as X
from analysis import exp3_planning as PL

MON = {"probe_rate_initial": 0.3, "probe_initial_decisions": 50, "probe_rate": 0.3, "min_probes_per_decisions": [2, 50]}


def synth(tmp, auth_pos=200, thr=0.9, revoke_pos=None, seed=0):
    rng = np.random.default_rng(seed); n = 630
    recs = []
    for i in range(1, n + 1):
        post = i > 380
        prop = "good" if rng.random() < 0.85 else "defective"
        P = float(rng.uniform(0.7, 1.0)) if i > 150 else None
        truth = prop if rng.random() > (0.3 if post else 0.03) else ("defective" if prop == "good" else "good")
        auto = prop == "good" and P is not None and i > auth_pos and P >= thr and (revoke_pos is None or i <= revoke_pos) and rng.random() > 0.3
        recs.append({"stream_position": i, "proposal": prop, "ground_truth": truth, "amp_approval_probability": P,
                     "amp_model_version": "m1" if P is not None else None, "routing": "autonomous" if auto else "hitl",
                     "segment": "post" if post else "pre", "governance_outcome": "execute" if auto else "hitl",
                     "margin_abs": float(rng.uniform(0, 3)), "decision_point_id": f"req-{i}"})
    sim = [{"event": "tick", "stream_position": k, "job_id": f"job-{k}", "approved_admin": (["wi-auth"] if k == auth_pos else [])}
           for k in range(10, n + 1, 10)]
    rl = [{"event_type": "MODEL_ACTIVATED", "payload": {}},
          {"event_type": "AUTHORITY_CLASS_AUTHORIZED", "payload": {"action_class": "good", "workitem_id": "wi-auth", "threshold": thr, "model_version": "m1"}}]
    if revoke_pos:
        rl.append({"event_type": "AUTHORITY_CLASS_REVOKED", "payload": {"action_class": "good", "job_id": f"job-{revoke_pos}"}})
    d = Path(tmp) / "run"; d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"agent_name": "a", "arm": "shift", "stream_seed": 0, "n_items": n, "summary": {}}))
    (d / "amp_decisions.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    (d / "amp_events.jsonl").write_text("\n".join(json.dumps(e) for e in sim) + "\n")
    (d / "amp_rlhf_events.jsonl").write_text("\n".join(json.dumps(e) for e in rl) + "\n")
    return d, recs


def main():
    with tempfile.TemporaryDirectory() as tmp:
        d, recs = synth(tmp, revoke_pos=450)
        o = X.analyse_run(d, MON)
        assert o["eligible"] and o["good_auth_pos"] == 200 and o["frozen_model_ok"], o
        assert o["good_first_revoke_items_after_shift"] == 70 and o["good_revocations"] == 1
        # T0/T1 recomputed independently with the PLANNING probe schedule
        t0 = [r for r in recs if r["proposal"] == "good" and r["stream_position"] > 200 and r["amp_approval_probability"] is not None
              and r["amp_approval_probability"] >= 0.9]
        t1, elig, probes = [], 0, 0
        for r in t0:
            due = PL.probes_due(elig + 1, 0.3, 50, 0.3); elig += 1
            if probes < due: probes += 1
            else: t1.append(r)
        esc = lambda rs, seg: sum(1 for r in rs if r["segment"] == seg and r["ground_truth"] == "defective")
        assert o["t0_good_exec_post"] == sum(1 for r in t0 if r["segment"] == "post") and o["t0_good_err_post"] == esc(t0, "post")
        assert o["t1_good_exec_pre"] + o["t1_good_exec_post"] == len(t1) and o["t1_good_err_post"] == esc(t1, "post")
        amp = [r for r in recs if r["routing"] == "autonomous"]
        assert o["amp_good_err_post"] == esc(amp, "post")
        # schedule parity with the planning replica over a long range
        assert all(X.probes_due(n, MON) == PL.probes_due(n, 0.3, 50, 0.3) for n in range(0, 2000))
    # certification parity with the planning replica
    rng = np.random.default_rng(3); v = rng.uniform(0.7, 1, 300); ok = (rng.random(300) > 0.05).astype(int)
    assert X.certify(v, ok, PL.GRID) == PL.certify(v, ok, 0.10, 30, 0.95, PL.GRID)
    # bootstrap edge cases
    assert X.boot_upper_ratio([0, 0], [0, 0], B=50) == 1.0 and X.boot_upper_ratio([1, 0], [0, 0], B=50) == float("inf")
    print("exp3_analysis self-test OK")


if __name__ == "__main__":
    main()
