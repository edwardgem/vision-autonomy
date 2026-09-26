"""Experiment 3 stream construction (EXPERIMENT_PLAN_3.md section 2). Deterministic given (arm, seed).

Pooled five LOCO categories, test split, frozen decision records (same features as Experiments 1-2).
  pre  (items 1..n_pre):   good + structural at pi_s
  post (n_pre+1..n_pre+n_post), shift arm:      good, structural pi_s, logical pi_l  (a new failure mode appears)
  post,                         stationary arm: good + structural at pi_s             (the pre regime continues)
Sampling is without replacement within a run. anomaly_type / ground_truth never leave the simulator.
"""
import numpy as np
import pandas as pd
from sim.amp_client import ROOT


def build_exp3_stream(arm, seed, n_pre=380, n_post=250, pi_s=0.10, pi_l=0.30, records=None):
    if arm not in ("shift", "stationary"):
        raise ValueError(f"unknown arm {arm}")
    d = records if records is not None else pd.read_csv(ROOT / "results" / "inputs" / "decision_records.csv")
    rng = np.random.default_rng(seed)
    pools = {t: list(rng.permutation(d[d.anomaly_type == t].sort_values("image_id").index.to_numpy()))
             for t in ("good", "structural", "logical")}

    def take(t, k):
        if k > len(pools[t]):
            raise ValueError(f"supply: need {k} {t}, have {len(pools[t])}")
        out, pools[t] = pools[t][:k], pools[t][k:]
        return out

    g1 = round(n_pre * (1 - pi_s))
    pre = take("good", g1) + take("structural", n_pre - g1)
    if arm == "shift":
        s2, l2 = round(n_post * pi_s), round(n_post * pi_l)
        post = take("good", n_post - s2 - l2) + take("structural", s2) + take("logical", l2)
    else:
        g2 = round(n_post * (1 - pi_s))
        post = take("good", g2) + take("structural", n_post - g2)
    order = list(rng.permutation(pre)) + list(rng.permutation(post))
    s = d.loc[order].reset_index(drop=True)
    s["segment"] = ["pre"] * n_pre + ["post"] * n_post
    return s
