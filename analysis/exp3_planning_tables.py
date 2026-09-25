"""Writes results/exp3_planning/tables.md: every planning number quoted in EXPERIMENT_PLAN_3.md (computed, not typed)."""
import numpy as np, pandas as pd
from scipy.stats import binom
from analysis.exp3_planning import *

REPS = 400
pool = load_pool(ALL5)
L = []
def md(df):
    cols = list(df.columns); L.append("| " + " | ".join(cols) + " |"); L.append("|" + "---|" * len(cols))
    for _, r in df.iterrows(): L.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    L.append("")

def rule(sh, st, rng, comp="twinp", ratio_max=1.0, boot=400):
    if len(sh) < 5 or len(st) < 5: return False
    a, t = sh.amp_good_post_err.to_numpy(), sh[f"{comp}_good_post_err"].to_numpy()
    if t.sum() == 0 or a.sum() / t.sum() > ratio_max: return False
    idx = rng.integers(0, len(sh), (boot, len(sh)))
    if np.quantile(a[idx].sum(1) / np.maximum(1, t[idx].sum(1)), 0.95) >= 1: return False
    if (st.good_revocations > 0).mean() > 0.10: return False
    ex = (st.amp_good_pre_exec + st.amp_good_post_exec).sum(); er = (st.amp_good_pre_err + st.amp_good_post_err).sum()
    return ex > 0 and er / ex <= 0.10

L.append("## T1. Stream composition (seed 1; counts are fixed by construction)\n")
rows = []
for arm in ("shift", "stationary"):
    s = build_stream(pool, np.random.default_rng(1), 380, 250, 0.10, 0.30, arm)
    for seg in (0, 1):
        c = s[s.post == seg].anomaly_type.value_counts()
        rows.append({"arm": arm, "segment": "pre (items 1-380)" if seg == 0 else "post (items 381-630)",
                     "good": int(c.get("good", 0)), "structural": int(c.get("structural", 0)), "logical": int(c.get("logical", 0))})
md(pd.DataFrame(rows))

L.append("## T2. Evidence needed to certify (budget 0.10, one-sided 95% Clopper-Pearson): max proposal errors k in a slice of n\n")
md(pd.DataFrame([{"slice n": n, "max k": max([k for k in range(n) if cpu(k, n, .95) <= .10], default="none")} for n in (30, 40, 50, 60, 80, 100)]))

L.append("## T3. Probe power: P(revoke) = P(LCB95(K, n) > 0.10), K ~ Bin(n, r), exact\n")
rows = []
for n in (10, 15, 20, 30, 40, 60):
    kmin = next(k for k in range(n + 1) if cpl(k, n, .95) > .10)
    rows.append({"probes n": n, "k needed": kmin, **{f"r={r}": round(1 - binom.cdf(kmin - 1, n, r), 3) for r in (0.15, 0.2, 0.25, 0.3, 0.4)}})
md(pd.DataFrame(rows))

L.append(f"## T4. Planning simulation by option ({REPS} streams per arm; eligible = first model accepted and good class authorized before the shift)\n")
opts = [("A: monitor as shipped (cumulative)", None, 0.3, 0.3), ("B: + recent-window rule W=20", 20, 0.3, 0.3),
        ("B, probe rate 0.2", 20, 0.3, 0.2), ("A, weaker shift", None, 0.2, 0.3), ("B, weaker shift", 20, 0.2, 0.3)]
rows, rows2 = [], []
for label, W, pl, pr in opts:
    d = {arm: scenario(pool, dict(BASE, arm=arm, n1=380, n2=250, pi_l=pl, stage0_rows=150, budget_good=0.10,
                                   probe_rate=pr, monitor_window=W), REPS) for arm in ("shift", "stationary")}
    sh, st = eligible_runs(d["shift"]), eligible_runs(d["stationary"])
    r = summarise(d["shift"])
    rows.append({"option": label, "logical prev. post": pl, "probe rate": pr,
                 "P(model accepted)": round(d["shift"].first_model_accepted.mean(), 3),
                 "P(eligible)": round(len(sh) / REPS, 3),
                 "P(revoked after shift)": round((sh.good_first_revoke_after_shift.notna()).mean(), 3),
                 "median items to revoke": sh.good_first_revoke_after_shift.median(),
                 "post escapes AMP": round(sh.amp_good_post_err.mean(), 1), "post escapes T1": round(sh.twinp_good_post_err.mean(), 1),
                 "post escapes T0": round(sh.twin_good_post_err.mean(), 1),
                 "ratio AMP/T1": round(sh.amp_good_post_err.sum() / sh.twinp_good_post_err.sum(), 2),
                 "ratio AMP/T0": round(sh.amp_good_post_err.sum() / sh.twin_good_post_err.sum(), 2)})
    rng = np.random.default_rng(5)
    rows2.append({"option": label,
                  "stationary: P(false revocation)": round((st.good_revocations > 0).mean(), 3),
                  "stationary: AMP good-class auton. error": round((st.amp_good_pre_err + st.amp_good_post_err).sum() / (st.amp_good_pre_exec + st.amp_good_post_exec).sum(), 3),
                  "stationary: correct exec AMP/T1": round(((st.amp_good_pre_exec - st.amp_good_pre_err) + (st.amp_good_post_exec - st.amp_good_post_err)).sum() / ((st.twinp_good_pre_exec - st.twinp_good_pre_err) + (st.twinp_good_post_exec - st.twinp_good_post_err)).sum(), 3),
                  "stationary: human burden AMP": round((st.human_reviews / st.N).mean(), 3),
                  "shift: AMP good-class whole-run error": round((sh.amp_good_pre_err + sh.amp_good_post_err).sum() / (sh.amp_good_pre_exec + sh.amp_good_post_exec).sum(), 3),
                  "assurance R=10": round(assurance(d["shift"], d["stationary"], 10, rule, sims=800), 3),
                  "assurance R=12": round(assurance(d["shift"], d["stationary"], 12, rule, sims=800), 3),
                  "assurance R=15": round(assurance(d["shift"], d["stationary"], 15, rule, sims=800), 3)})
    if label.startswith("B: "):
        e = sh
        extra = {"certified threshold (share)": e.good_first_thr.value_counts(normalize=True).round(3).sort_index(ascending=False).to_dict(),
                 "authorization item q10/q50/q90": e.good_first_auth.quantile([.1, .5, .9]).tolist(),
                 "revocation delay q25/q50/q75 (items after shift)": e.good_first_revoke_after_shift.quantile([.25, .5, .75]).tolist(),
                 "never revoked": round(e.good_first_revoke_after_shift.isna().mean(), 3),
                 "mean probes per run": round(e.amp_probes.mean(), 1),
                 "defective class authorized pre-shift": round((e.def_first_auth.fillna(1e9) <= e.shift_at).mean(), 3)}
md(pd.DataFrame(rows))
L.append("## T5. Stationary arm, whole-run compliance, and assurance of the proposed success rule (§8)\n")
md(pd.DataFrame(rows2))
L.append("## T6. Option B details (shift arm, eligible runs)\n")
for k, v in extra.items(): L.append(f"- {k}: {v}")
open("results/exp3_planning/tables.md", "w").write("\n".join(L) + "\n")
print("\n".join(L))

L2 = ["## T7. Risk-budget feasibility and the size of the shift (option B configuration, 400 streams, shift arm)\n"]
rows = []
for bg in (0.05, 0.10):
    d = scenario(pool, dict(BASE, arm="shift", n1=380, n2=250, pi_l=0.3, stage0_rows=150, budget_good=bg, probe_rate=0.3, monitor_window=20), REPS)
    e = eligible_runs(d)
    rows.append({"good-class budget": bg, "P(eligible)": round(len(e) / REPS, 3),
                 "T0 error of authorized good slice, pre": round(e.twin_good_pre_err.sum() / max(1, e.twin_good_pre_exec.sum()), 3),
                 "T0 error of authorized good slice, post": round(e.twin_good_post_err.sum() / max(1, e.twin_good_post_exec.sum()), 3)})
L = L2
md(pd.DataFrame(rows))
open("results/exp3_planning/tables.md", "a").write("\n" + "\n".join(L) + "\n")
print("\n".join(L))

L = ["## T8. Assurance of the stricter 'halving' rule (rho <= 0.5 AND upper bound < 1), option B, R=12\n"]
d = {arm: scenario(pool, dict(BASE, arm=arm, n1=380, n2=250, pi_l=0.3, stage0_rows=150, budget_good=0.10, probe_rate=0.3,
                               monitor_window=20), REPS) for arm in ("shift", "stationary")}
L.append(f"- assurance: {round(assurance(d['shift'], d['stationary'], 12, lambda a, b, r: rule(a, b, r, 'twinp', 0.5), sims=800), 3)}")
open("results/exp3_planning/tables.md", "a").write("\n" + "\n".join(L) + "\n")
print("\n".join(L))
