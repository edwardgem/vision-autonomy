"""Experiment 3 secondary / descriptive analyses (EXPERIMENT_PLAN_3.md section 8 'Secondary') for RESULTS-3.md.

Writes results/exp3/aggregate/secondary_tables.md (every number quoted in RESULTS-3.md), secondary_runs.csv and
fig_exp3_cumulative_escapes.png. The PRIMARY result is analysis/exp3_analysis.py's (preregistered, unchanged).

POST-HOC CORRECTION (disclosed in RESULTS-3.md section 5): the preregistered code maps authority events to stream
positions only through the simulator's tick log. AMP's own scheduler also ran STAGE_TICK jobs, and events from those
ticks were dropped. Here an event whose job_id is not in the tick log is placed by timestamp: position = the last
decision recorded at or before the event (a change after item k takes effect from item k+1). On every event that the
tick log does cover, this rule reproduces the tick mapping exactly (checked below and reported).
Usage: python -m analysis.exp3_secondary
"""
import bisect, json
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from analysis.exp3_analysis import ROOT, N_PRE, BUDGET, MARGIN_GRID, analyse_run, certify, load_run, probes_due

OUT = ROOT / "results/exp3/aggregate"
POLICY = json.loads((ROOT / "config/exp3/amp_policy_exp3_v1.json").read_text())
MON = POLICY["autonomy_ops"]["authority"]["monitoring"]
L = []
check = {"ts_vs_tick_agree": 0, "ts_vs_tick_disagree": 0}


def md(df, index=False):
    df = df.reset_index() if index else df
    L.append("| " + " | ".join(map(str, df.columns)) + " |"); L.append("|" + "---|" * len(df.columns))
    for _, r in df.iterrows():
        L.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v) for v in r.values) + " |")
    L.append("")


def rate(k, n):
    return round(k / n, 4) if n else None


def run_detail(d):
    man, r, sim_ev, rl_ev = load_run(d)
    pre = analyse_run(d, MON)                                   # preregistered numbers (for reconciliation)
    ts = [datetime.fromisoformat(x.replace("Z", "")) for x in r.timestamp]
    pos = r.stream_position.to_numpy()
    job_pos, wi_pos = {}, {}
    for e in sim_ev:
        if e.get("event") == "tick":
            job_pos[e["job_id"]] = e["stream_position"]
            for w in e.get("approved_admin") or []:
                wi_pos.setdefault(w, e["stream_position"])

    def locate(e):
        j = e["payload"].get("job_id")
        k = bisect.bisect_right(ts, datetime.fromisoformat(e["ts"]))
        by_ts = int(pos[k - 1]) if k else 0
        if j in job_pos:
            check["ts_vs_tick_agree" if job_pos[j] == by_ts else "ts_vs_tick_disagree"] += 1
            return job_pos[j]
        w = e["payload"].get("workitem_id")
        return wi_pos.get(w, by_ts) if w else by_ts

    good = (r.proposal == "good").to_numpy(); post = (r.segment == "post").to_numpy()
    defect = (r.ground_truth == "defective").to_numpy()
    P = pd.to_numeric(r.amp_approval_probability, errors="coerce").to_numpy()
    amp = (r.routing == "autonomous").to_numpy() & good
    t0 = np.zeros(len(r), bool); t1 = np.zeros(len(r), bool); tm = np.zeros(len(r), bool)
    if pre["good_auth_pos"] is not None and not np.isnan(pre["good_auth_pos"]):
        t0 = good & (pos > pre["good_auth_pos"]) & (P >= pre["good_auth_thr"])
        elig = probes = 0
        for i in np.where(t0)[0]:
            due = probes_due(elig + 1, MON); elig += 1
            if probes < due:
                probes += 1
            else:
                t1[i] = True
    # TM with ALL of AMP's good-class evaluations (corrected positions)
    by_id = r.set_index("decision_point_id"); tm_delta = tm_pos = None; n_eval = 0
    evals = sorted(((locate(e), e) for e in rl_ev if e["event_type"] == "AUTHORITY_QUALIFICATION_EVALUATED"
                    and e["payload"].get("action_class") == "good"), key=lambda t: t[0])   # stable: DB order within a tick
    n_eval = len(evals)
    for p_eval, e in evals:
        ids = [i for i in e["payload"].get("evidence_ids", []) if i in by_id.index]
        if not ids:
            continue
        rows = by_id.loc[ids]
        delta = certify(rows.margin_abs.astype(float), (rows.proposal == rows.ground_truth).astype(int), MARGIN_GRID)
        if delta is not None:
            tm_delta, tm_pos = delta, p_eval
            tm = good & (pos > p_eval) & (r.margin_abs.astype(float).to_numpy() >= delta)
            break
    auths_good = sorted(locate(e) for e in rl_ev if e["event_type"] == "AUTHORITY_CLASS_AUTHORIZED" and e["payload"].get("action_class") == "good")
    revs = sorted(((locate(e), e["payload"].get("reason", "")) for e in rl_ev
                  if e["event_type"] == "AUTHORITY_CLASS_REVOKED" and e["payload"].get("action_class") == "good"), key=lambda t: t[0])
    warns = sum(1 for e in rl_ev if e["event_type"] == "AUTHORITY_MONITORING_WARNING" and e["payload"].get("action_class") == "good")
    def_auth = sum(1 for e in rl_ev if e["event_type"] == "AUTHORITY_CLASS_AUTHORIZED" and e["payload"].get("action_class") == "defective")
    viol = sum(1 for e in sim_ev if e.get("event") == "violation")
    summ = man.get("summary", {})
    rev_pos = revs[0][0] if revs else None
    o = dict(arm=man["arm"], seed=man["stream_seed"], eligible=pre["eligible"], first_model_accepted=pre["first_model_accepted"],
             frozen_model_ok=pre.get("frozen_model_ok"), reconcile_ok=summ.get("reconcile_ok"), failed_jobs=len(summ.get("failed_jobs") or []),
             auto_rejects=summ.get("auto_rejects"), violations=viol, auth_pos=pre["good_auth_pos"], auth_thr=pre["good_auth_thr"],
             revocations=len(revs), revoke_pos=rev_pos,
             revoke_rule=("recent-window" if revs and "recent-window" in revs[0][1] else ("cumulative" if revs else None)),
             revoke_items_after_shift=(rev_pos - N_PRE) if rev_pos is not None and rev_pos > N_PRE else None,
             revocations_pre=sum(1 for p, _ in revs if p <= N_PRE), warnings=warns,
             reauthorizations=sum(1 for p in auths_good if revs and p > revs[0][0]), def_class_authorized=def_auth,
             probes=int(((r.governance_outcome == "probe") & good).sum()),
             probes_post=int(((r.governance_outcome == "probe") & good & post).sum()),
             probe_errors_post=int(((r.governance_outcome == "probe") & good & post & (r.oracle_response == "reject")).sum()),
             probes_post_before_rev=int(((r.governance_outcome == "probe") & good & post & ((pos <= rev_pos) if rev_pos else True)).sum()),
             human_reviews=int((r.routing != "autonomous").sum()), n_items=len(r), tm_delta=tm_delta, tm_pos=tm_pos, tm_evaluations=n_eval,
             tm_evaluations_prereg_visible=sum(1 for _, e in evals if e["payload"].get("job_id") in job_pos))
    for name, ex in (("amp", amp), ("t1", t1), ("t0", t0), ("tm", tm)):
        for seg, sm in (("pre", ~post), ("post", post)):
            o[f"{name}_exec_{seg}"] = int((ex & sm).sum()); o[f"{name}_esc_{seg}"] = int((ex & sm & defect).sum())
    o["amp_esc_post_before_rev"] = int((amp & post & defect & ((pos <= rev_pos) if rev_pos else True)).sum())
    o["amp_exec_post_after_rev"] = int((amp & post & (pos > rev_pos)).sum()) if rev_pos else 0
    # reconciliation with the preregistered analysis (mapping-independent quantities must be identical)
    for mine, theirs in (("amp_esc_post", "amp_good_err_post"), ("t1_esc_post", "t1_good_err_post"), ("t0_esc_post", "t0_good_err_post"),
                         ("amp_exec_pre", "amp_good_exec_pre"), ("t1_exec_post", "t1_good_exec_post")):
        assert o[mine] == pre[theirs], (d, mine, o[mine], pre[theirs])
    o["prereg_revocations"] = pre["good_revocations"]; o["prereg_tm_esc_post"] = pre["tm_good_err_post"]
    flags = pd.DataFrame({"pos": pos, "post": post, "category": r.category, "anomaly_type": r.anomaly_type,
                          "amp": amp & defect, "t1": t1 & defect, "t0": t0 & defect})
    pre_route = tuple(zip(r.routing[~post], [None if np.isnan(v) else round(float(v), 6) for v in P[~post]]))
    return o, flags, pre_route


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runs = sorted(p.parent for p in (ROOT / "results/exp3/runs").glob("*/manifest.json"))
    det, flags, pre_routes = [], {}, {}
    for d in runs:
        o, f, pr = run_detail(d)
        det.append(o); flags[(o["arm"], o["seed"])] = f; pre_routes[(o["arm"], o["seed"])] = pr
    df = pd.DataFrame(det).sort_values(["arm", "seed"]).reset_index(drop=True)
    for c in ("seed", "auth_pos", "revoke_pos", "revoke_items_after_shift", "tm_pos", "tm_evaluations", "tm_evaluations_prereg_visible", "tm_esc_post", "prereg_tm_esc_post"):
        df[c] = df[c].astype("Int64")
    det_def_exec = [analyse_run(d, MON)["amp_def_exec_pre"] + analyse_run(d, MON)["amp_def_exec_post"] for d in runs]
    df.to_csv(OUT / "secondary_runs.csv", index=False)
    E = df[df.eligible]; sh, st = E[E.arm == "shift"], E[E.arm == "stationary"]
    prim = json.loads((OUT / "exp3_primary.json").read_text())

    L.append("# Experiment 3: secondary tables (generated by analysis/exp3_secondary.py; do not edit by hand)\n")
    L.append(f"Mapping check (post-hoc correction): timestamp placement vs tick-log placement on events the tick log covers: "
             f"agree {check['ts_vs_tick_agree']}, disagree {check['ts_vs_tick_disagree']}.\n")

    L.append("## S1. Run integrity and eligibility\n")
    g = df.groupby("arm")
    md(pd.DataFrame({"runs": g.size(), "complete & reconciled": g.reconcile_ok.sum(), "failed jobs": g.failed_jobs.sum(),
                     "protocol violations": g.violations.sum(), "auto-rejects": g.auto_rejects.sum(),
                     "first model accepted": g.first_model_accepted.sum(), "eligible": g.eligible.sum(),
                     "frozen model ok (eligible)": E.groupby("arm").frozen_model_ok.sum()}), index=True)
    inel = df[~df.eligible]
    L.append(f"- Ineligible runs (first model rejected): {', '.join(f'{a} s{s}' for a, s in zip(inel.arm, inel.seed))}\n")
    same = [s for s in sorted(set(df.seed)) if pre_routes.get(("shift", s)) == pre_routes.get(("stationary", s))]
    L.append(f"- Pre-shift determinism: AMP routing and P on items 1-380 identical between the two arms for {len(same)} of "
             f"{len(set(df.seed))} seeds (same seed = same pre-shift stream).\n")

    L.append("## S2. Primary endpoint (from exp3_primary.json, preregistered analysis)\n")
    L.append("```json\n" + json.dumps(prim, indent=2) + "\n```\n")
    L.append("Per eligible shift run (post-shift escapes = autonomous good releases of defective parts, items 381-630):\n")
    t = sh[["seed", "auth_pos", "auth_thr", "revocations", "revoke_rule", "revoke_items_after_shift", "probes_post", "probe_errors_post", "amp_esc_post", "t1_esc_post", "t0_esc_post", "tm_esc_post"]].copy()
    t["AMP/T1"] = [rate(a, b) for a, b in zip(t.amp_esc_post, t.t1_esc_post)]
    md(t)

    L.append("## S3. Revocation (shift arm, eligible runs; corrected event placement)\n")
    rv = sh[sh.revocations > 0]
    md(pd.DataFrame([{"runs revoked": f"{len(rv)} of {len(sh)}", "rule that fired": {k: int(v) for k, v in rv.revoke_rule.value_counts().items()},
                      "items after shift, min/median/max": [int(rv.revoke_items_after_shift.min()), float(rv.revoke_items_after_shift.median()), int(rv.revoke_items_after_shift.max())] if len(rv) else None,
                      "revocations before the shift": int(sh.revocations_pre.sum()), "re-authorizations after revocation": int(sh.reauthorizations.sum()),
                      "AMP escapes before revocation (revoked runs)": int(rv.amp_esc_post_before_rev.sum()),
                      "AMP autonomous good executions placed after revocation (async boundary, see note)": int(rv.amp_exec_post_after_rev.sum()),
                      "post-shift probes before revocation (revoked runs), median": float(rv.probes_post_before_rev.median()) if len(rv) else None,
                      "preregistered code counted revocations": int(sh.prereg_revocations.gt(0).sum())}]))
    nr = sh[sh.revocations == 0]
    L.append(f"- Not revoked ({len(nr)} runs: seeds {', '.join(map(str, nr.seed))}): AMP escapes equal T1 escapes in each "
             f"({'yes' if (nr.amp_esc_post == nr.t1_esc_post).all() else 'NO'}); post-shift escapes AMP {int(nr.amp_esc_post.sum())}, T1 {int(nr.t1_esc_post.sum())}.")
    L.append(f"- Revoked ({len(rv)} runs): post-shift escapes AMP {int(rv.amp_esc_post.sum())}, T1 {int(rv.t1_esc_post.sum())}, T0 {int(rv.t0_esc_post.sum())}.")
    L.append(f"- Monitoring warnings (good class): shift arm {int(sh.warnings.sum())}, stationary arm {int(st.warnings.sum())}.")
    L.append(f"- Stationary arm revocations (raw events, corrected placement): {int(st.revocations.sum())} in {len(st)} eligible runs.\n")

    L.append("## S4. Autonomous error of the good class against the 0.10 budget (pooled over eligible runs)\n")
    rows = []
    for arm, A in (("shift", sh), ("stationary", st)):
        for sysn in ("amp", "t1", "t0"):
            rows.append({"arm": arm, "system": sysn.upper(),
                         "pre: errors/exec": f"{int(A[f'{sysn}_esc_pre'].sum())}/{int(A[f'{sysn}_exec_pre'].sum())}", "pre rate": rate(A[f"{sysn}_esc_pre"].sum(), A[f"{sysn}_exec_pre"].sum()),
                         "post: errors/exec": f"{int(A[f'{sysn}_esc_post'].sum())}/{int(A[f'{sysn}_exec_post'].sum())}", "post rate": rate(A[f"{sysn}_esc_post"].sum(), A[f"{sysn}_exec_post"].sum()),
                         "whole run rate": rate(A[f"{sysn}_esc_pre"].sum() + A[f"{sysn}_esc_post"].sum(), A[f"{sysn}_exec_pre"].sum() + A[f"{sysn}_exec_post"].sum())})
    md(pd.DataFrame(rows))

    L.append("## S5. Useful autonomy and human burden (eligible runs; 630 items per run)\n")
    rows = []
    for arm, A in (("shift", sh), ("stationary", st)):
        n = int(A.n_items.sum())
        for sysn in ("amp", "t1", "t0"):
            ex = int(A[f"{sysn}_exec_pre"].sum() + A[f"{sysn}_exec_post"].sum()); er = int(A[f"{sysn}_esc_pre"].sum() + A[f"{sysn}_esc_post"].sum())
            rows.append({"arm": arm, "system": sysn.upper(), "autonomous executions": ex, "correct autonomous": ex - er,
                         "wrong autonomous (escapes)": er, "human-reviewed share": round(1 - ex / n, 3)})
    md(pd.DataFrame(rows))
    L.append(f"- Mean good-class probes per eligible run: shift {round(sh.probes.mean(), 1)}, stationary {round(st.probes.mean(), 1)}.")
    dz = df[df.def_class_authorized > 0]
    L.append(f"- Defective class: authorized in {len(dz)} of {len(df)} runs ({', '.join(f'{a} s{s_}' for a, s_ in zip(dz.arm, dz.seed))}); "
             f"autonomous defective executions over all runs: {int(sum(o_ for o_ in det_def_exec))}.\n")

    L.append("## S6. Post-shift escapes by category and anomaly type (shift arm, eligible runs)\n")
    F = pd.concat([flags[("shift", s)].assign(seed=s) for s in sh.seed])
    F = F[F.post]
    md(F.groupby("category")[["amp", "t1", "t0"]].sum().astype(int), index=True)
    md(F.groupby("anomaly_type")[["amp", "t1", "t0"]].sum().astype(int), index=True)

    L.append("## S7. Margin twin TM (secondary): preregistered code vs corrected event placement\n")
    md(sh[["seed", "tm_evaluations", "tm_evaluations_prereg_visible", "tm_delta", "tm_pos", "tm_esc_post", "prereg_tm_esc_post"]])
    L.append(f"- TM post-shift escapes, eligible shift runs: preregistered code {int(sh.prereg_tm_esc_post.sum())}; corrected {int(sh.tm_esc_post.sum())}; "
             f"AMP/TM corrected = {rate(sh.amp_esc_post.sum(), sh.tm_esc_post.sum())}.\n")

    L.append("## S8. Planning replica vs observed (option B)\n")
    md(pd.DataFrame([
        {"quantity": "P(first model accepted)", "planning": 0.87, "observed": f"{int(df.first_model_accepted.sum())}/{len(df)} = {rate(df.first_model_accepted.sum(), len(df))}"},
        {"quantity": "P(eligible)", "planning": 0.838, "observed": f"{int(df.eligible.sum())}/{len(df)} = {rate(df.eligible.sum(), len(df))}"},
        {"quantity": "P(revoked after shift | eligible)", "planning": 0.818, "observed": f"{len(rv)}/{len(sh)} = {rate(len(rv), len(sh))}"},
        {"quantity": "median items to revoke", "planning": 100, "observed": float(rv.revoke_items_after_shift.median()) if len(rv) else None},
        {"quantity": "ratio AMP/T1 (pooled)", "planning": 0.46, "observed": round(prim["rho_vs_T1"], 3)},
        {"quantity": "ratio AMP/T0 (pooled)", "planning": 0.32, "observed": round(prim["rho_vs_T0"], 3)},
        {"quantity": "stationary P(false revocation)", "planning": 0.012, "observed": f"{int(st.revocations.gt(0).sum())}/{len(st)}"},
        {"quantity": "shift: AMP whole-run good-class error", "planning": 0.116, "observed": rate(sh.amp_esc_pre.sum() + sh.amp_esc_post.sum(), sh.amp_exec_pre.sum() + sh.amp_exec_post.sum())},
        {"quantity": "stationary: AMP good-class error", "planning": 0.035, "observed": rate(st.amp_esc_pre.sum() + st.amp_esc_post.sum(), st.amp_exec_pre.sum() + st.amp_exec_post.sum())},
    ]))

    # figure: cumulative post-shift escapes, pooled over eligible shift runs
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    x = np.arange(1, 251); cum = {}
    for k in ("amp", "t1", "t0"):
        c = np.zeros(250)
        for s in sh.seed:
            f = flags[("shift", s)]; f = f[f.post]
            c += np.cumsum(f[k].to_numpy()[:250])
        cum[k] = c
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    styles = {"t0": ("#8C8C8C", "T0: static, no probes"), "t1": ("#D95F02", "T1: static, same probes"), "amp": ("#1B6AC9", "AMP: lifecycle (revocation)")}
    for k in ("t0", "t1", "amp"):
        ax.plot(x, cum[k], lw=2, color=styles[k][0], label=styles[k][1])
        ax.annotate(f"{int(cum[k][-1])}", (250, cum[k][-1]), xytext=(4, 0), textcoords="offset points", va="center", fontsize=8, color="#333333")
    rp = rv.revoke_items_after_shift.dropna().to_numpy()
    ax.plot(rp, np.zeros_like(rp) - 3, "|", ms=8, color="#1B6AC9", label="AMP revocations (per run)")
    ax.set_xlabel("items after the shift (item 381 = 1)"); ax.set_ylabel("cumulative escapes (pooled, 10 runs)")
    ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", color="#E6E6E6", lw=0.8); ax.set_xlim(0, 262)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(OUT / "fig_exp3_cumulative_escapes.png"); plt.close(fig)
    L.append("## Figure\n\n`results/exp3/aggregate/fig_exp3_cumulative_escapes.png`: cumulative post-shift escapes pooled over the "
             "10 eligible shift runs (AMP, T1, T0), with each run's revocation point.\n")
    (OUT / "secondary_tables.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
