"""Experiment 3 PLANNING simulator (design aid only; not the experiment, not GOV).

Offline replica of GOV's authority lifecycle rules (rlhf src/authority/*; Clopper-Pearson from analysis/cp_bounds.py,
the same algorithm as the platform's) run over the real frozen PatchCore test scores, to size Experiment 3 BEFORE it is
preregistered: stream construction, evidence budgets, risk budgets, probe power, and the static-authorization twin.

Approximations (declared; the experiment itself runs real GOV):
  - GOV's reliability model is approximated by a logistic regression on (is_defective_proposal, score_z, margin_abs),
    fitted on the Stage 0 rows' 80% train split; acceptance = both labels present in train and test, test AUROC >= 0.55.
  - The model is FROZEN after first activation (no retrain), matching the recommended primary configuration.
  - Ticks every 10 items; an authorization proposal is approved at the tick that raises it (auto-approve admin).
  - No downstream outcome feedback (confirmed-failure path off): probe-only monitoring.
Usage: python -m analysis.exp3_planning [--reps 200] [--out results/exp3_planning]
"""
import argparse, itertools, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from analysis.cp_bounds import cp_upper, cp_lower  # same algorithm as the platform's implementation

ROOT = Path(__file__).resolve().parents[1]

SENSITIVE = ["screw_bag", "pushpins", "splicing_connectors"]
ALL5 = ["breakfast_box", "juice_bottle", "pushpins", "screw_bag", "splicing_connectors"]
GRID = [0.99, 0.98, 0.97, 0.95, 0.93, 0.9, 0.85, 0.8]
TICK = 10


def load_pool(categories):
    df = pd.read_csv(ROOT / "results/patchcore_scores.csv")
    df = df[(df.split == "test") & df.category.isin(categories)].copy()
    cal = json.load(open(ROOT / "config/calibration_v1.json"))["per_category"]
    tau = df.category.map(lambda c: cal[c]["tau"]); mu = df.category.map(lambda c: cal[c]["mu_val"])
    sig = df.category.map(lambda c: cal[c]["sigma_val"])
    df["is_def"] = (df.raw_score >= tau).astype(int)
    df["score_z"] = (df.raw_score - mu) / sig
    df["margin"] = (df.raw_score - tau).abs() / sig
    df["correct"] = ((df.is_def == 1) == (df.ground_truth == "defective")).astype(int)
    return df.reset_index(drop=True)


def build_stream(pool, rng, n1, n2, pi_s, pi_l, arm):
    """pre: good + structural at pi_s; post (shift arm): good + structural pi_s + logical pi_l; stationary arm: pre regime."""
    idx = {t: list(rng.permutation(pool.index[pool.anomaly_type == t])) for t in ("good", "structural", "logical")}
    def take(t, k):
        if k > len(idx[t]):
            raise ValueError(f"supply: need {k} {t}, have {len(idx[t])}")
        out, idx[t] = idx[t][:k], idx[t][k:]
        return out
    g1 = round(n1 * (1 - pi_s)); pre = take("good", g1) + take("structural", n1 - g1)
    if arm == "shift":
        s2, l2 = round(n2 * pi_s), round(n2 * pi_l); post = take("good", n2 - s2 - l2) + take("structural", s2) + take("logical", l2)
    else:
        g2 = round(n2 * (1 - pi_s)); post = take("good", g2) + take("structural", n2 - g2)
    order = list(rng.permutation(pre)) + list(rng.permutation(post))
    s = pool.loc[order].reset_index(drop=True)
    s["post"] = np.r_[np.zeros(n1, int), np.ones(n2, int)]
    return s


def probes_due(n, rate0, n0, rate, floor=(2, 50)):
    if n <= 0:
        return 0
    by_rate = math.ceil(min(n, n0) * rate0 + max(0, n - n0) * rate - 1e-9)
    return min(n, max(by_rate, (n // floor[1]) * floor[0]))


def certify(rows_p, rows_ok, budget, min_rows, conf, grid):
    """Fixed-sequence over the descending grid; sparse thresholds skipped; stop at first bound failure."""
    p, ok = np.asarray(rows_p), np.asarray(rows_ok)
    cert = None
    for t in grid:
        m = p >= t; n = int(m.sum())
        if n < min_rows:
            continue
        k = int((ok[m] == 0).sum())
        if cpu(k, n, conf) > budget:
            break
        cert = t
    return cert


_cpu_cache = {}
def cpu(k, n, conf):
    key = (k, n, conf)
    if key not in _cpu_cache:
        _cpu_cache[key] = cp_upper(k, n, conf)
    return _cpu_cache[key]


_cpl_cache = {}
def cpl(k, n, conf):
    key = (k, n, conf)
    if key not in _cpl_cache:
        _cpl_cache[key] = cp_lower(k, n, conf)
    return _cpl_cache[key]


def run_one(s, cfg, seed):
    n0 = cfg["stage0_rows"]; conf = cfg["confidence"]
    X = s[["is_def", "score_z", "margin"]].to_numpy(float); y = s.correct.to_numpy(); cls = s.is_def.to_numpy()
    # ---- Stage 0 + first model (80/20 split, acceptance = label diversity + test AUROC >= 0.55)
    rng = np.random.default_rng(seed + 7)
    perm = rng.permutation(n0); tr, te = perm[: int(n0 * 0.8)], perm[int(n0 * 0.8):]
    accepted = len(set(y[tr])) == 2 and len(set(y[te])) == 2
    if accepted:
        lr = LogisticRegression(C=1.0, max_iter=1000).fit(X[tr], y[tr])
        accepted = roc_auc_score(y[te], lr.predict_proba(X[te])[:, 1]) >= 0.55
    out = {"first_model_accepted": bool(accepted)}
    N = len(s); route = np.array(["human"] * N, dtype=object); P = np.full(N, np.nan)
    if accepted:
        P[n0:] = lr.predict_proba(X[n0:])[:, 1]
    budget = {0: cfg["budget_good"], 1: cfg["budget_def"]}
    scope = {c: {"status": "qualifying", "since": n0, "thr": None, "auth_at": None, "elig": 0, "probes": 0,
                 "first_thr": None, "first_auth": None, "revoked_at": [], "authorized_at": []} for c in (0, 1)}
    human_rows = []  # (i, cls, P, correct)
    for i in range(N):
        if accepted and i >= n0:
            c = cls[i]; sc = scope[c]
            if sc["status"] == "authorized" and P[i] >= sc["thr"]:
                due = probes_due(sc["elig"] + 1, cfg["probe_rate0"], cfg["probe_n0"], cfg["probe_rate"])
                sc["elig"] += 1
                if sc["probes"] < due:
                    sc["probes"] += 1; route[i] = "probe"
                else:
                    route[i] = "execute"
        if route[i] in ("human", "probe"):
            human_rows.append((i, cls[i], P[i], y[i], route[i]))
        # ---- tick
        if accepted and (i + 1) % TICK == 0 and i + 1 >= n0:
            for c in (0, 1):
                sc = scope[c]
                if sc["status"] == "qualifying":
                    ev = [(p, ok) for (j, cc, p, ok, _) in human_rows if cc == c and j >= sc["since"] and not np.isnan(p)]
                    if ev:
                        thr = certify([e[0] for e in ev], [e[1] for e in ev], budget[c], cfg["min_rows"], conf, GRID)
                        if thr is not None:
                            sc.update(status="authorized", thr=thr, auth_at=i + 1, elig=0, probes=0)
                            sc["authorized_at"].append(i + 1)
                            if sc["first_thr"] is None:
                                sc["first_thr"], sc["first_auth"] = thr, i + 1
                elif sc["status"] == "authorized":
                    pr = [ok for (j, cc, p, ok, r) in human_rows if cc == c and r == "probe" and j >= sc["auth_at"]]
                    n, k = len(pr), sum(1 for ok in pr if ok == 0)
                    revoke = bool(n) and cpl(k, n, conf) > budget[c]
                    W = cfg.get("monitor_window")          # HYPOTHETICAL variant (not in GOV): also test the last W probes
                    if W and not revoke and n >= min(W, cfg.get("window_min", 10)):
                        w = pr[-W:]; kw = sum(1 for ok in w if ok == 0)
                        revoke = cpl(kw, len(w), conf) > budget[c]
                    if revoke:
                        sc.update(status="qualifying", since=i + 1, thr=None)
                        sc["revoked_at"].append(i + 1)
    # ---- outcomes: GOV vs static-authorization twin (same model, same first certified threshold, never withdrawn, no probes)
    post = s.post.to_numpy() == 1; shift_at = int((~post).sum())
    twin = np.zeros(N, bool)
    for c in (0, 1):
        sc = scope[c]
        if sc["first_auth"] is not None:
            twin |= (cls == c) & (np.arange(N) >= sc["first_auth"]) & (P >= sc["first_thr"])
    amp = route == "execute"
    # T1: same first authorization AND the same deterministic probe schedule, but no consequences (never revoked)
    twin_p = np.zeros(N, bool)
    for c in (0, 1):
        sc = scope[c]
        if sc["first_auth"] is None:
            continue
        elig = probes = 0
        for i in np.where((cls == c) & (np.arange(N) >= sc["first_auth"]) & (P >= sc["first_thr"]))[0]:
            due = probes_due(elig + 1, cfg["probe_rate0"], cfg["probe_n0"], cfg["probe_rate"]); elig += 1
            if probes < due:
                probes += 1
            else:
                twin_p[i] = True
    for c, name in ((0, "good"), (1, "def")):
        m = cls == c
        for seg, sm in (("pre", ~post), ("post", post)):
            for sysname, ex in (("amp", amp), ("twin", twin), ("twinp", twin_p)):
                e = ex & m & sm
                out[f"{sysname}_{name}_{seg}_exec"] = int(e.sum())
                out[f"{sysname}_{name}_{seg}_err"] = int((e & (y == 0)).sum())
        sc = scope[c]
        out[f"{name}_first_auth"] = sc["first_auth"]; out[f"{name}_first_thr"] = sc["first_thr"]
        out[f"{name}_revocations"] = len(sc["revoked_at"])
        out[f"{name}_revoked_pre"] = sum(1 for r in sc["revoked_at"] if r <= shift_at)
        rp = [r for r in sc["revoked_at"] if r > shift_at]
        out[f"{name}_first_revoke_after_shift"] = (rp[0] - shift_at) if rp else None
        out[f"{name}_reauthorized_post"] = sum(1 for a in sc["authorized_at"] if a > shift_at)
    out["human_reviews"] = int((route != "execute").sum()); out["N"] = N; out["shift_at"] = shift_at
    out["amp_probes"] = int((route == "probe").sum())
    return out


def scenario(pool, cfg, reps, base_seed=1000):
    rows = []
    for r in range(reps):
        rng = np.random.default_rng(base_seed + r)
        s = build_stream(pool, rng, cfg["n1"], cfg["n2"], cfg["pi_s"], cfg["pi_l"], cfg["arm"])
        rows.append(run_one(s, cfg, base_seed + r))
    return pd.DataFrame(rows)


def summarise(df):
    acc = df[df.first_model_accepted]
    f = lambda col: acc[col].mean() if len(acc) else float("nan")
    g_auth = acc.good_first_auth.notna()
    return {
        "reps": len(df), "p_first_model_accepted": df.first_model_accepted.mean(),
        "p_good_authorized_pre_shift": (acc.good_first_auth.fillna(1e9) <= acc.shift_at).mean() if len(acc) else float("nan"),
        "p_def_authorized_pre_shift": (acc.def_first_auth.fillna(1e9) <= acc.shift_at).mean() if len(acc) else float("nan"),
        "median_good_first_auth": acc.good_first_auth.median(),
        "good_pre_exec_amp": f("amp_good_pre_exec"), "good_pre_exec_twin": f("twin_good_pre_exec"),
        "good_pre_err_rate_amp": acc.amp_good_pre_err.sum() / max(1, acc.amp_good_pre_exec.sum()),
        "good_post_exec_amp": f("amp_good_post_exec"), "good_post_exec_twin": f("twin_good_post_exec"),
        "good_post_escapes_amp": f("amp_good_post_err"), "good_post_escapes_twin": f("twin_good_post_err"),
        "good_post_err_rate_amp": acc.amp_good_post_err.sum() / max(1, acc.amp_good_post_exec.sum()),
        "good_post_err_rate_twin": acc.twin_good_post_err.sum() / max(1, acc.twin_good_post_exec.sum()),
        "p_good_revoked_post_given_auth": (acc[g_auth].good_first_revoke_after_shift.notna()).mean() if g_auth.any() else float("nan"),
        "median_items_to_revoke": acc.good_first_revoke_after_shift.median(),
        "p_good_false_revoke_pre": (acc[g_auth].good_revoked_pre > 0).mean() if g_auth.any() else float("nan"),
        "p_def_revoked_any": (acc.def_revocations > 0).mean() if len(acc) else float("nan"),
        "def_exec_amp": (acc.amp_def_pre_exec + acc.amp_def_post_exec).mean(),
        "def_err_rate_amp": (acc.amp_def_pre_err.sum() + acc.amp_def_post_err.sum()) / max(1, (acc.amp_def_pre_exec + acc.amp_def_post_exec).sum()),
        "human_burden": (acc.human_reviews / acc.N).mean(), "probes": f("amp_probes"),
        "good_run_err_rate_amp": (acc.amp_good_pre_err.sum() + acc.amp_good_post_err.sum()) / max(1, (acc.amp_good_pre_exec + acc.amp_good_post_exec).sum()),
        "good_run_err_rate_twin": (acc.twin_good_pre_err.sum() + acc.twin_good_post_err.sum()) / max(1, (acc.twin_good_pre_exec + acc.twin_good_post_exec).sum()),
        "good_correct_exec_amp": ((acc.amp_good_pre_exec - acc.amp_good_pre_err) + (acc.amp_good_post_exec - acc.amp_good_post_err)).mean(),
        "good_correct_exec_twin": ((acc.twin_good_pre_exec - acc.twin_good_pre_err) + (acc.twin_good_post_exec - acc.twin_good_post_err)).mean(),
        "p_good_revoked_any_given_auth": (acc[g_auth].good_revocations > 0).mean() if g_auth.any() else float("nan"),
    }


def eligible_runs(df):
    """Primary analysis set: first model accepted AND good class authorized before the shift."""
    return df[df.first_model_accepted & (df.good_first_auth.fillna(1e9) <= df.shift_at)]


def assurance(shift_df, stat_df, R, rule, sims=2000, seed=5):
    """P(the preregistered success rule passes) when R shift runs and R stationary runs are drawn from the planning
    distribution (runs failing the eligibility condition are drawn too and dropped, as the plan prescribes)."""
    rng = np.random.default_rng(seed); ok = 0
    for _ in range(sims):
        sh = shift_df.iloc[rng.integers(0, len(shift_df), R)]
        st = stat_df.iloc[rng.integers(0, len(stat_df), R)]
        ok += rule(eligible_runs(sh), eligible_runs(st), rng)
    return ok / sims


def rule_v1(sh, st, rng, boot=400):
    """H1: post-shift escapes GOV vs twin, pooled ratio <= 0.5 AND run-bootstrap one-sided 95% upper bound < 1.
    H2: stationary arm: good class revoked in <= 10% of eligible runs, and GOV's pooled good-class autonomous
    error <= budget (0.10). Needs >= 5 eligible runs in each arm."""
    if len(sh) < 5 or len(st) < 5:
        return False
    a, t = sh.amp_good_post_err.to_numpy(), sh.twin_good_post_err.to_numpy()
    if t.sum() == 0 or a.sum() / t.sum() > 0.5:
        return False
    idx = rng.integers(0, len(sh), (boot, len(sh)))
    ratios = a[idx].sum(1) / np.maximum(1, t[idx].sum(1))
    if np.quantile(ratios, 0.95) >= 1:
        return False
    if (st.good_revocations > 0).mean() > 0.10:
        return False
    ex = (st.amp_good_pre_exec + st.amp_good_post_exec).sum(); er = (st.amp_good_pre_err + st.amp_good_post_err).sum()
    return ex > 0 and er / ex <= 0.10


BASE = dict(arm="shift", n1=280, n2=150, pi_s=0.10, pi_l=0.30, stage0_rows=150, budget_good=0.10, budget_def=0.10,
            min_rows=30, confidence=0.95, probe_rate0=0.3, probe_n0=50, probe_rate=0.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--out", default="results/exp3_planning")
    a = ap.parse_args()
    out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)
    pools = {"sensitive3": load_pool(SENSITIVE), "all5": load_pool(ALL5)}
    grid = []
    for pool_name, (n1, n2), pi_l, stage0, bg, pr, arm in itertools.product(
            ["sensitive3"], [(250, 150), (280, 150), (220, 200)], [0.2, 0.3, 0.4], [80, 150], [0.05, 0.10], [0.1, 0.2, 0.3],
            ["shift", "stationary"]):
        if arm == "stationary" and pi_l != 0.3:
            continue
        cfg = dict(BASE, arm=arm, n1=n1, n2=n2, pi_l=pi_l, stage0_rows=stage0, budget_good=bg, probe_rate=pr)
        try:
            df = scenario(pools[pool_name], cfg, a.reps)
        except ValueError as e:
            print("skip", cfg, e); continue
        row = {"pool": pool_name, **{k: cfg[k] for k in ("arm", "n1", "n2", "pi_l", "stage0_rows", "budget_good", "probe_rate")}, **summarise(df)}
        grid.append(row); print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()}), flush=True)
    pd.DataFrame(grid).to_csv(out / "planning_grid.csv", index=False)


if __name__ == "__main__":
    main()
