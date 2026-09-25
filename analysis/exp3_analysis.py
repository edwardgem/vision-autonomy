"""Experiment 3 analysis (EXPERIMENT_PLAN_3.md sections 7-8). Offline, deterministic, run AFTER the study.

Per run: eligibility, AMP's post-shift escapes, and the comparators computed exactly from the run's own logs
(the model is frozen, every decision logs P from it, and AMP's probe schedule is a deterministic counter):
  T1  static authorization WITH the same probe schedule, never revoked       (PRIMARY comparator)
  T0  static authorization without probes                                   (secondary)
  TM  the same certification rule on raw margin, on AMP's logged evidence ids at AMP's evaluation times (secondary)
Then the preregistered success rule (H1 and H2) with a run-level bootstrap.

Positions: an authority event is mapped to the stream position of the tick that produced it (payload job_id), or,
for an admin-approved authorization, of the tick whose settle approved that workitem. A change made at the tick after
item k takes effect from item k+1.

Usage: python -m analysis.exp3_analysis --runs-dir results/exp3/runs [--out results/exp3/aggregate]
"""
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "amp-backend"))
from authority_status import cp_lower, cp_upper  # noqa: E402  (same algorithm as rlhf stats.ts)

N_PRE = 380
BUDGET = 0.10
CONF = 0.95
MIN_ROWS = 30
MARGIN_GRID = [3.0, 2.5, 2.0, 1.75, 1.5, 1.25, 1.0, 0.75, 0.5, 0.25, 0.0]   # TM: strictest first
BOOT_B, BOOT_SEED = 10000, 20260925
MIN_ELIGIBLE_FOR_ANALYSIS = 5


def probes_due(n, m):
    """rlhf src/authority/authorize.ts probesDue (deterministic counter schedule)."""
    if n <= 0:
        return 0
    init = min(n, m["probe_initial_decisions"])
    rest = max(0, n - m["probe_initial_decisions"])
    by_rate = math.ceil(init * m["probe_rate_initial"] + rest * m["probe_rate"] - 1e-9)
    per, block = m["min_probes_per_decisions"]
    return min(n, max(by_rate, (n // block) * per))


def _jsonl(p):
    return [json.loads(l) for l in open(p)] if Path(p).exists() else []


def load_run(d):
    d = Path(d)
    man = json.loads((d / "manifest.json").read_text())
    recs = pd.DataFrame(_jsonl(d / "amp_decisions.jsonl")).sort_values("stream_position").reset_index(drop=True)
    sim_ev = _jsonl(d / "amp_events.jsonl")
    rl_ev = _jsonl(d / "amp_rlhf_events.jsonl")
    return man, recs, sim_ev, rl_ev


def tick_positions(sim_ev):
    job_pos, wi_pos = {}, {}
    for e in sim_ev:
        if e.get("event") != "tick":
            continue
        job_pos[e["job_id"]] = e["stream_position"]
        for w in e.get("approved_admin") or []:
            wi_pos.setdefault(w, e["stream_position"])
    return job_pos, wi_pos


def certify(values, ok, grid, budget=BUDGET, min_rows=MIN_ROWS, conf=CONF):
    """rlhf certifyClass: fixed-sequence down the grid, sparse thresholds skipped, stop at the first bound failure."""
    v, ok = np.asarray(values, float), np.asarray(ok, int)
    cert = None
    for t in grid:
        m = v >= t
        n = int(m.sum())
        if n < min_rows:
            continue
        if cp_upper(int((ok[m] == 0).sum()), n, conf) > budget:
            break
        cert = t
    return cert


def analyse_run(d, monitoring):
    man, r, sim_ev, rl_ev = load_run(d)
    job_pos, wi_pos = tick_positions(sim_ev)
    ev = lambda t: [e for e in rl_ev if e["event_type"] == t]
    out = {"run_dir": str(d), "agent": man["agent_name"], "arm": man.get("arm"), "seed": man["stream_seed"], "n": len(r)}
    out["complete"] = "summary" in man and len(r) == man["n_items"]
    out["first_model_accepted"] = bool(ev("MODEL_ACTIVATED"))

    auths = [e for e in ev("AUTHORITY_CLASS_AUTHORIZED") if e["payload"].get("action_class") == "good"]
    first = None
    for e in auths:
        pos = wi_pos.get(e["payload"].get("workitem_id")) or job_pos.get(e["payload"].get("job_id"))
        if pos is not None and (first is None or pos < first[0]):
            first = (pos, float(e["payload"]["threshold"]), e["payload"].get("model_version"))
    out["good_auth_pos"], out["good_auth_thr"], out["good_auth_model"] = first if first else (None, None, None)
    out["eligible"] = bool(out["complete"] and out["first_model_accepted"] and first is not None and first[0] <= N_PRE)

    revs = sorted(p for p in (job_pos.get(e["payload"].get("job_id")) for e in ev("AUTHORITY_CLASS_REVOKED")
                              if e["payload"].get("action_class") == "good") if p is not None)
    out["good_revocations"] = len(revs)
    out["good_revoked_pre"] = sum(1 for p in revs if p <= N_PRE)
    post_revs = [p for p in revs if p > N_PRE]
    out["good_first_revoke_items_after_shift"] = (post_revs[0] - N_PRE) if post_revs else None
    reauth = [wi_pos.get(e["payload"].get("workitem_id")) for e in auths]
    out["good_reauthorized_post"] = sum(1 for p in reauth if p is not None and p > N_PRE)

    good = (r.proposal == "good").to_numpy()
    post = (r.segment == "post").to_numpy()
    defective_truth = (r.ground_truth == "defective").to_numpy()
    pos = r.stream_position.to_numpy()
    P = pd.to_numeric(r.amp_approval_probability, errors="coerce").to_numpy()
    amp_exec = (r.routing == "autonomous").to_numpy()

    def tally(name, ex, cls_mask):
        for seg, sm in (("pre", ~post), ("post", post)):
            e = ex & cls_mask & sm
            out[f"{name}_exec_{seg}"] = int(e.sum())
            out[f"{name}_err_{seg}"] = int((e & ((defective_truth & good) | (~defective_truth & ~good))).sum())

    tally("amp_good", amp_exec, good)
    tally("amp_def", amp_exec, ~good)
    out["human_reviews"] = int((~amp_exec).sum())
    out["amp_probes_good"] = int(((r.governance_outcome == "probe") & good).sum())

    t0 = np.zeros(len(r), bool); t1 = np.zeros(len(r), bool)
    if first:
        after = pos > first[0]
        # frozen model: every scored decision after first activation came from ONE model version (the twins need it)
        models = set(r.loc[~np.isnan(P), "amp_model_version"].dropna())
        out["frozen_model_ok"] = len(models) == 1
        out["good_auth_model"] = next(iter(models)) if len(models) == 1 else None
        t0 = good & after & (P >= first[1])
        elig = probes = 0
        for i in np.where(t0)[0]:
            due = probes_due(elig + 1, monitoring); elig += 1
            if probes < due:
                probes += 1
            else:
                t1[i] = True
    tally("t0_good", t0, good)
    tally("t1_good", t1, good)

    # TM: margin twin on AMP's own evidence ids at AMP's evaluation times, frozen at its first pass
    tm = np.zeros(len(r), bool); out["tm_delta"] = out["tm_pos"] = None
    by_id = r.set_index("decision_point_id")
    for e in ev("AUTHORITY_QUALIFICATION_EVALUATED"):
        p = e["payload"]
        if p.get("action_class") != "good" or job_pos.get(p.get("job_id")) is None:
            continue
        ids = [i for i in p.get("evidence_ids", []) if i in by_id.index]
        if not ids:
            continue
        rows = by_id.loc[ids]
        ok = (rows.proposal == rows.ground_truth).astype(int)
        delta = certify(rows.margin_abs.astype(float), ok, MARGIN_GRID)
        if delta is not None:
            out["tm_delta"], out["tm_pos"] = delta, job_pos[p["job_id"]]
            tm = good & (pos > out["tm_pos"]) & (r.margin_abs.astype(float).to_numpy() >= delta)
            break
    tally("tm_good", tm, good)
    return out


def boot_upper_ratio(a, t, B=BOOT_B, seed=BOOT_SEED, q=0.95):
    """One-sided upper percentile bound ("higher" method) of sum(a)/sum(t) over a run-level bootstrap. 0/0 -> 1; x/0 -> inf."""
    rng = np.random.default_rng(seed)
    a, t = np.asarray(a, float), np.asarray(t, float)
    idx = rng.integers(0, len(a), (B, len(a)))
    sa, st = a[idx].sum(1), t[idx].sum(1)
    ratio = np.where(st > 0, sa / np.where(st > 0, st, 1), np.where(sa > 0, np.inf, 1.0))
    return float(np.quantile(ratio, q, method="higher"))   # no interpolation: conservative, well-defined with inf


def success_rule(df):
    sh = df[(df.arm == "shift") & df.eligible]; st = df[(df.arm == "stationary") & df.eligible]
    res = {"eligible_shift": len(sh), "eligible_stationary": len(st)}
    if len(sh) < MIN_ELIGIBLE_FOR_ANALYSIS or len(st) < MIN_ELIGIBLE_FOR_ANALYSIS:
        res.update(verdict="NOT EVALUABLE (fewer than 5 eligible runs in an arm)")
        return res
    A, T1, T0, TM = (sh[c].sum() for c in ("amp_good_err_post", "t1_good_err_post", "t0_good_err_post", "tm_good_err_post"))
    res["escapes_post"] = {"AMP": int(A), "T1": int(T1), "T0": int(T0), "TM": int(TM)}
    res["rho_vs_T1"] = (A / T1) if T1 else (float("inf") if A else 1.0)
    res["rho_vs_T1_upper95"] = boot_upper_ratio(sh.amp_good_err_post, sh.t1_good_err_post)
    res["rho_vs_T0"] = (A / T0) if T0 else None
    res["rho_vs_TM"] = (A / TM) if TM else None
    res["H1"] = bool(res["rho_vs_T1_upper95"] < 1)
    ex = (st.amp_good_exec_pre + st.amp_good_exec_post).sum(); er = (st.amp_good_err_pre + st.amp_good_err_post).sum()
    res["stationary_revoked_share"] = float((st.good_revocations > 0).mean())
    res["stationary_amp_good_error"] = (er / ex) if ex else None
    res["H2a"] = bool(res["stationary_revoked_share"] <= 0.10)
    res["H2b"] = bool(ex > 0 and er / ex <= BUDGET)
    res["SUCCESS"] = bool(res["H1"] and res["H2a"] and res["H2b"])
    res["verdict"] = "SUPPORTED" if res["SUCCESS"] else "NOT SUPPORTED"
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-dir", default="results/exp3/runs")
    ap.add_argument("--out", default="results/exp3/aggregate")
    ap.add_argument("--policy", default="config/exp3/amp_policy_exp3_v1.json")
    a = ap.parse_args()
    mon = json.loads((ROOT / a.policy).read_text())["autonomy_ops"]["authority"]["monitoring"]
    runs = sorted(p.parent for p in (ROOT / a.runs_dir).glob("*/manifest.json"))
    df = pd.DataFrame([analyse_run(d, mon) for d in runs])
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "exp3_runs.csv", index=False)
    res = success_rule(df) if len(df) else {"verdict": "no runs"}
    (out / "exp3_primary.json").write_text(json.dumps(res, indent=2, default=float))
    print(df.to_string(max_cols=12)); print(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()
