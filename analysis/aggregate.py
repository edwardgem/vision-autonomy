"""Aggregate study runs into the preregistered tables T1-T5 and figures F1/F1b (EXPERIMENT_PLAN.md sections 7-8).

Everything here is descriptive and follows the preregistered definitions; nothing is tuned. Missing (seed, category)
runs are reported as missing, never imputed.
"""
import json, glob, collections
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from analysis.common import *

RUNS = ROOT / "results" / "runs"
AGG = ROOT / "results" / "aggregate"
TAB = ROOT / "results" / "tables"
FIG = ROOT / "results" / "figures"
for d in (AGG, TAB, FIG):
    d.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------------------------------------ loading
def load_runs():
    runs = []
    for mp in sorted(RUNS.glob("*/manifest.json")):
        m = json.loads(mp.read_text())
        if "summary" not in m:
            continue
        d = mp.parent
        df = pd.read_csv(d / "amp_decisions.csv")
        for c in ("correct", "false_acceptance", "false_rejection", "probe_forced_human", "hard_blocked"):
            df[c] = df[c].astype(bool)
        ev = [json.loads(l) for l in open(d / "amp_rlhf_events.jsonl")]
        oe = [json.loads(l) for l in open(d / "amp_events.jsonl")]
        runs.append({"seed": int(m["stream_seed"]), "category": m["category"], "agent": m["agent_name"], "dir": d,
                     "manifest": m, "df": df, "rlhf_events": ev, "orch_events": oe})
    return runs


# ------------------------------------------------------------------------------------------------ formatting
def pm(vals, nd=3, of=None):
    """mean ± SD over the defined values; tagged (n=k/N) whenever fewer than N seeds/runs contribute."""
    vals = list(vals)
    v = np.array([x for x in vals if x == x], dtype=float)
    total = of if of is not None else len(vals)
    if len(v) == 0:
        return "n/a"
    txt = f"{v.mean():.{nd}f}" if len(v) == 1 or v.std(ddof=1) == 0 else f"{v.mean():.{nd}f} ± {v.std(ddof=1):.{nd}f}"
    return txt + (f" (n={len(v)}/{total})" if len(v) < total else "")


def fmt(x, nd=3):
    return "n/a" if x != x else f"{x:.{nd}f}"


def write_table(name, df, caption, note=""):
    df.to_csv(TAB / f"{name}.csv", index=False)
    cols = list(df.columns)
    md = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    md += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    (TAB / f"{name}.md").write_text(f"**{caption}**\n\n" + "\n".join(md) + (f"\n\n{note}\n" if note else "\n"))
    esc = lambda s: str(s).replace("±", "$\\pm$").replace("_", "\\_").replace("%", "\\%")
    tex = ["\\begin{table}[t]\\centering\\small", f"\\caption{{{esc(caption)}}}", f"\\label{{tab:{name}}}",
           "\\begin{tabular}{" + "l" + "r" * (len(cols) - 1) + "}\\hline", " & ".join(esc(c) for c in cols) + " \\\\ \\hline"]
    tex += [" & ".join(esc(v) for v in r) + " \\\\" for r in df.itertuples(index=False)]
    tex += ["\\hline\\end{tabular}", "\\end{table}"]
    (TAB / f"{name}.tex").write_text("\n".join(tex) + "\n")


# ------------------------------------------------------------------------------------------------ conditions on any frame
def cond_frames(rec):
    """A,B,C on an arbitrary record frame (columns of decision_records)."""
    return {"A Human oracle": condition_oracle(rec), "B Model only": condition_model_only(rec),
            f"C Static HITL (δ={DELTA:g}σ)": condition_static(rec, DELTA)}


def matched_static(win, k):
    """Static HITL at matched coverage: auto-execute the k highest-margin items of the window (ties by image_id)."""
    d = win.copy().sort_values(["margin_abs", "image_id"], ascending=[False, True])
    d["routing"] = "hitl"
    d.iloc[:k, d.columns.get_loc("routing")] = "autonomous"
    d["final_decision"] = np.where(d.routing == "hitl", d.ground_truth, d.proposal)
    return add_flags(d)


def rec_cols(df):
    return df[["image_id", "category", "anomaly_type", "ground_truth", "proposal", "margin_abs"]]


# ------------------------------------------------------------------------------------------------ main
def main():
    rec = load_records()
    runs = load_runs()
    have = sorted({(r["seed"], r["category"]) for r in runs})
    print(f"{len(runs)} completed runs; seeds={sorted({s for s, _ in have})}")
    expected = [(s, c) for s in SEEDS for c in CATS]
    missing = [x for x in expected if x not in have]
    (AGG / "coverage.json").write_text(json.dumps({"completed": [list(x) for x in have], "missing": [list(x) for x in missing]}, indent=1))

    # ---- concatenated raw D decisions
    allD = pd.concat([r["df"].assign(stream_seed=r["seed"]) for r in runs], ignore_index=True) if runs else pd.DataFrame()
    if len(allD):
        allD.to_csv(AGG / "all_decisions_D.csv", index=False)

    # ---- per-run metrics + Wilson CIs
    rows = []
    for r in runs:
        m = metrics(r["df"])
        row = {"stream_seed": r["seed"], "category": r["category"], **m}
        for nm, k, n in (("accuracy", m["n"] - m["errors"], m["n"]), ("fa_rate", m["fa_count"], m["n_gt_defective"]),
                         ("fr_rate", m["fr_count"], m["n_gt_good"]), ("autonomous_rate", m["autonomous_count"], m["n"]),
                         ("autonomous_error_rate", m["autonomous_errors"], m["autonomous_count"])):
            lo, hi = wilson(k, n)
            row[f"{nm}_ci95_lo"], row[f"{nm}_ci95_hi"] = lo, hi
        rows.append(row)
    per_run = pd.DataFrame(rows)
    per_run.to_csv(AGG / "per_run_metrics.csv", index=False, float_format="%.6f")

    # ============================================================ T1 dataset & perception
    t1 = []
    for c in CATS:
        g = rec[rec.category == c]
        y = g.ground_truth == "defective"
        aucs = {"all": roc_auc_score(y, g.raw_score)}
        for ty in ("logical", "structural"):
            s = g[g.anomaly_type.isin(["good", ty])]
            aucs[ty] = roc_auc_score(s.ground_truth == "defective", s.raw_score)
        mo = metrics(condition_model_only(g))
        t1.append({"Category": c, "Good": int((g.anomaly_type == "good").sum()), "Structural": int((g.anomaly_type == "structural").sum()),
                   "Logical": int((g.anomaly_type == "logical").sum()), "AUROC all": fmt(aucs["all"]),
                   "AUROC logical": fmt(aucs["logical"]), "AUROC structural": fmt(aucs["structural"]),
                   "tau": fmt(float(g.tau.iloc[0]), 2), "Proposal FA rate": fmt(mo["fa_rate"]), "Proposal FR rate": fmt(mo["fr_rate"])})
    mo = metrics(condition_model_only(rec))
    t1.append({"Category": "All (macro AUROC)", "Good": int((rec.anomaly_type == "good").sum()), "Structural": int((rec.anomaly_type == "structural").sum()),
               "Logical": int((rec.anomaly_type == "logical").sum()),
               "AUROC all": fmt(np.mean([float(x["AUROC all"]) for x in t1])), "AUROC logical": fmt(np.mean([float(x["AUROC logical"]) for x in t1])),
               "AUROC structural": fmt(np.mean([float(x["AUROC structural"]) for x in t1])), "tau": "-",
               "Proposal FA rate": fmt(mo["fa_rate"]), "Proposal FR rate": fmt(mo["fr_rate"])})
    write_table("T1_dataset_perception", pd.DataFrame(t1), "T1. Test stream and PatchCore perception (seed 0, frozen scores). Proposal = raw score >= tau (0.95 quantile of validation-normal scores).",
                "Test stream is anomaly-heavy (63.3%): a benchmark distribution, not a production rate. AUROC is threshold-free; FA/FR rates are for the fixed-threshold proposal.")

    if not runs:
        print("no completed runs yet; T1 written only")
        return

    # ============================================================ per-seed pooled frames
    seeds_present = sorted({r["seed"] for r in runs})
    full_seeds = [s for s in seeds_present if all((s, c) in have for c in CATS)]

    def pooled(seed):
        return pd.concat([r["df"] for r in runs if r["seed"] == seed], ignore_index=True)

    # ============================================================ T2 main comparison (full stream)
    t2, per_seed = [], []
    base = {k: metrics(v) for k, v in cond_frames(rec).items()}
    D_by_seed = {s: metrics(pooled(s)) for s in full_seeds}
    for k, m in base.items():
        t2.append({"Condition": k, "Accuracy": fmt(m["accuracy"]), "FA rate": fmt(m["fa_rate"]), "FR rate": fmt(m["fr_rate"]),
                   "Autonomous rate": fmt(m["autonomous_rate"]), "HITL rate": fmt(m["hitl_rate"]),
                   "Autonomous error rate": fmt(m["autonomous_error_rate"]) if m["autonomous_count"] else "—"})
        per_seed.append({"condition": k, "stream_seed": "all", **m})
    if D_by_seed:
        col = lambda key: [D_by_seed[s][key] for s in full_seeds]
        t2.append({"Condition": f"D GOV progressive (n={len(full_seeds)} seeds, mean ± SD)", "Accuracy": pm(col("accuracy")),
                   "FA rate": pm(col("fa_rate")), "FR rate": pm(col("fr_rate")), "Autonomous rate": pm(col("autonomous_rate")),
                   "HITL rate": pm(col("hitl_rate")), "Autonomous error rate": pm(col("autonomous_error_rate"))})
        for s in full_seeds:
            per_seed.append({"condition": "D GOV progressive", "stream_seed": s, **D_by_seed[s]})
    write_table("T2_main_comparison", pd.DataFrame(t2), "T2. Main comparison over the full 1,568-image stream. FA = defect executed as good (rate over GT-defective); FR = good executed as defective (rate over GT-good).",
                "A–C do not depend on stream order (single value). D is pooled over the 5 categories within each seed, then mean ± SD across seeds. Stages 0 and 1 are 100% HITL, so D's full-stream autonomy is bounded by how early each run reaches Stage 2 (at least the first 160 items are always human).")
    pd.DataFrame(per_seed).to_csv(AGG / "T2_per_seed.csv", index=False, float_format="%.6f")

    # ============================================================ T3 GOV promotion per category
    t3_rows = []
    for r in runs:
        df = r["df"].sort_values("stream_position")
        st = df.amp_stage.to_numpy()
        s1 = int(df[df.amp_stage >= 1].stream_position.min()) if (st >= 1).any() else None
        s2 = int(df[df.amp_stage >= 2].stream_position.min()) if (st >= 2).any() else None
        reentries = int(((st[1:] < st[:-1])).sum())
        ec = collections.Counter(e["event_type"] for e in r["rlhf_events"])
        dis = next((e["stream_position"] for e in r["orch_events"] if e["event"] == "rlhf_auto_disabled_detected"), None)
        w = df[df.amp_stage == 2]
        wm = metrics(w) if len(w) else None
        t3_rows.append({"stream_seed": r["seed"], "category": r["category"], "stage1_entry_pos": s1, "stage2_entry_pos": s2,
                        "reached_stage2": s2 is not None, "candidates_trained": ec["MODEL_CANDIDATE_READY"], "activations": ec["MODEL_ACTIVATED"],
                        "stage_regressions": reentries, "rollbacks": ec["MODEL_ROLLBACK"], "rlhf_auto_disabled": ec["RLHF_AUTO_DISABLED"] > 0,
                        "auto_disabled_at_pos": dis, "stage2_items": len(w), "stage2_autonomous": wm["autonomous_count"] if wm else 0,
                        "stage2_autonomy_rate": wm["autonomous_rate"] if wm else np.nan,
                        "stage2_autonomous_error_rate": wm["autonomous_error_rate"] if wm else np.nan,
                        "stage2_autonomous_errors": wm["autonomous_errors"] if wm else 0,
                        "admin_approvals": len(r["manifest"]["summary"]["admin_approvals"])})
    t3r = pd.DataFrame(t3_rows).sort_values(["category", "stream_seed"])
    t3r.to_csv(AGG / "T3_per_run.csv", index=False, float_format="%.6f")
    t3 = []
    for c in CATS:
        g = t3r[t3r.category == c]
        if g.empty:
            continue
        rs = g[g.reached_stage2]
        t3.append({"Category": c, "Runs": len(g), "Seeds reaching Stage 2": f"{len(rs)}/{len(g)}",
                   "Stage 1 entry (item, median)": fmt(g.stage1_entry_pos.median(), 0) if g.stage1_entry_pos.notna().any() else "never",
                   "Stage 2 entry (item, median)": fmt(rs.stage2_entry_pos.median(), 0) if len(rs) else "never",
                   "Candidates trained (mean)": fmt(g.candidates_trained.mean(), 1), "Stage regressions (total)": int(g.stage_regressions.sum()),
                   "Rollbacks (total)": int(g.rollbacks.sum()), "RLHF auto-disabled (runs)": int(g.rlhf_auto_disabled.sum()),
                   "Stage 2 autonomy rate": pm(rs.stage2_autonomy_rate, of=len(g)) if len(rs) else "n/a",
                   "Stage 2 autonomous error rate": pm(rs.stage2_autonomous_error_rate, of=len(g)) if len(rs) else "n/a"})
    write_table("T3_amp_promotion", pd.DataFrame(t3), f"T3. GOV promotion behaviour per category ({len(SEEDS)} preregistered stream seeds; 'Runs' = completed runs).",
                "Entry positions are stream positions of the first Stage ≥1 / Stage 2 decision. Stage 2 rates are mean ± SD across the seeds that reached Stage 2, over their Stage 2 items only. Per-run detail: results/aggregate/T3_per_run.csv.")

    # ============================================================ T4 by anomaly type
    def by_type(df):
        out = {}
        for ty in TYPES:
            g = df[df.anomaly_type == ty]
            out[ty] = metrics(g)
        return out

    t4 = []
    frames = {**cond_frames(rec)}
    for k, f in frames.items():
        bt = by_type(f)
        for ty in TYPES:
            m = bt[ty]
            t4.append({"Condition": k, "Type": ty, "N": m["n"], "Accuracy": fmt(m["accuracy"]),
                       "Miss rate (FA)" if False else "Error rate": fmt(1 - m["accuracy"]),
                       "Autonomous rate": fmt(m["autonomous_rate"]),
                       "Autonomous error rate": fmt(m["autonomous_error_rate"]) if m["autonomous_count"] else "—"})
    if full_seeds:
        bts = {s: by_type(pooled(s)) for s in full_seeds}
        for ty in TYPES:
            g = lambda key: [bts[s][ty][key] for s in full_seeds]
            t4.append({"Condition": f"D GOV progressive (mean ± SD, {len(full_seeds)} seeds)", "Type": ty, "N": int(np.mean(g("n"))),
                       "Accuracy": pm(g("accuracy")), "Error rate": pm([1 - a for a in g("accuracy")]),
                       "Autonomous rate": pm(g("autonomous_rate")), "Autonomous error rate": pm(g("autonomous_error_rate"))})
    write_table("T4_by_anomaly_type", pd.DataFrame(t4), "T4. Results by anomaly type over the full stream (good / structural / logical).",
                "Error rate = 1 − accuracy: for defect types it is the false-acceptance rate, for good images the false-rejection rate. anomaly_type was never visible to GOV.")

    # ============================================================ T5 Stage-2 window comparison
    t5_run, t5_agg = [], collections.defaultdict(list)
    for r in runs:
        w = r["df"][r["df"].amp_stage == 2]
        if w.empty:
            continue
        wr = rec[rec.image_id.isin(w.image_id)].copy()
        k = int((w.routing == "autonomous").sum())
        comps = {"GOV progressive": add_flags(w.assign(final_decision=w.final_decision)),
                 f"Static HITL δ={DELTA:g}σ": condition_static(wr, DELTA),
                 "Static HITL matched coverage": matched_static(wr, k),
                 "Model only": condition_model_only(wr)}
        for nm, d in comps.items():
            m = metrics(d)
            t5_run.append({"stream_seed": r["seed"], "category": r["category"], "condition": nm, **m})
            t5_agg[(r["seed"], nm)].append(d)
    t5r = pd.DataFrame(t5_run)
    t5r.to_csv(AGG / "T5_per_run.csv", index=False, float_format="%.6f")
    t5 = []
    if len(t5r):
        for nm in ["GOV progressive", f"Static HITL δ={DELTA:g}σ", "Static HITL matched coverage", "Model only"]:
            per = []
            for s in seeds_present:
                fr = t5_agg.get((s, nm))
                if fr:
                    per.append(metrics(pd.concat(fr, ignore_index=True)))
            if not per:
                continue
            tot = metrics(pd.concat([d for (s, n), v in t5_agg.items() if n == nm for d in v], ignore_index=True))
            t5.append({"Condition": nm, "Stage 2 items (total)": tot["n"], "Autonomous (total)": tot["autonomous_count"],
                       "Autonomous rate (mean ± SD over seeds)": pm([p["autonomous_rate"] for p in per], of=len(seeds_present)),
                       "Autonomous error rate (mean ± SD)": pm([p["autonomous_error_rate"] for p in per], of=len(seeds_present)),
                       "Autonomous FA (total)": tot["autonomous_fa"],
                       "Autonomous FA / autonomous (mean ± SD)": pm([p["autonomous_fa"] / p["autonomous_count"] if p["autonomous_count"] else np.nan for p in per], of=len(seeds_present)),
                       "Accuracy (mean ± SD)": pm([p["accuracy"] for p in per], of=len(seeds_present))})
    write_table("T5_stage2_window", pd.DataFrame(t5), "T5. Stage 2 window comparison: all conditions evaluated on exactly the items GOV handled at Stage 2 (runs that reached Stage 2).",
                "Static HITL at matched coverage auto-executes the same NUMBER of items GOV executed autonomously (chosen by largest margin, ties by image_id): no free parameter. Seeds are pooled over categories; per-run detail: results/aggregate/T5_per_run.csv.")

    # ============================================================ figures
    make_figures(rec, runs, seeds_present, t5_agg)
    print("tables:", sorted(p.name for p in TAB.glob("*.csv")))


# ------------------------------------------------------------------------------------------------ figures
def sweep(rec):
    xs = []
    for d in np.round(np.arange(CFG["static_hitl"]["risk_coverage_sweep"]["delta_min"], CFG["static_hitl"]["risk_coverage_sweep"]["delta_max"] + 1e-9,
                                CFG["static_hitl"]["risk_coverage_sweep"]["step"]), 4):
        m = metrics(condition_static(rec, d))
        if m["autonomous_count"]:
            xs.append((m["autonomous_rate"], m["autonomous_error_rate"], d))
    return xs


def make_figures(rec, runs, seeds_present, t5_agg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
    BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"     # validated categorical slots 1-3 (all-pairs safe)
    plt.rcParams.update({"font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6})
    panels = [("All categories", rec)] + [(c.replace("_", " "), rec[rec.category == c]) for c in CATS]
    fig, axs = plt.subplots(2, 3, figsize=(9.2, 5.6), sharex=True, sharey=False)
    for ax, (title, sub) in zip(axs.ravel(), panels):
        cv = sweep(sub)
        ax.plot([x for x, _, _ in cv], [y for _, y, _ in cv], color=BLUE, lw=1.6, label="Static HITL (δ sweep 0–5σ)")
        m1 = metrics(condition_static(sub, DELTA))
        ax.plot(m1["autonomous_rate"], m1["autonomous_error_rate"], marker="D", ms=6, mfc="white", mec=BLUE, mew=1.6, ls="none", label=f"Static HITL δ={DELTA:g}σ")
        mo = metrics(condition_model_only(sub))
        ax.plot(1.0, mo["autonomous_error_rate"], marker="s", ms=6, color=MUTED, ls="none", label="Model only")
        cat = None if title == "All categories" else title.replace(" ", "_")
        pts, n_seeds_run = [], 0
        for s in seeds_present:
            rr = [r["df"] for r in runs if r["seed"] == s and (cat is None or r["category"] == cat)]
            if cat is None and len(rr) != len(CATS):
                continue
            if not rr:
                continue
            n_seeds_run += 1
            m = metrics(pd.concat(rr, ignore_index=True))
            if m["autonomous_count"]:
                pts.append((m["autonomous_rate"], m["autonomous_error_rate"]))
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", ms=5.5, color=ORANGE, mec="white", mew=0.8, ls="none", label="GOV progressive (one point per seed, full stream)")
        ax.set_title(title, fontsize=9, color=INK, loc="left")
        ax.text(0.02, 0.97, f"GOV: {len(pts)}/{n_seeds_run} seeds made any autonomous decision\n(others = 0% coverage, not plottable)",
                transform=ax.transAxes, va="top", fontsize=6.5, color=MUTED)
        ax.set_xlim(-0.02, 1.02)
    for ax in axs[1]:
        ax.set_xlabel("Coverage (fraction executed autonomously)")
    for ax in axs[:, 0]:
        ax.set_ylabel("Risk (error rate among autonomous)")
    seen = {}
    for a_ in axs.ravel():
        for h_, l_ in zip(*a_.get_legend_handles_labels()):
            seen.setdefault(l_, h_)
    h, l = list(seen.values()), list(seen.keys())
    fig.legend(h, l, loc="lower center", ncol=4, frameon=False, fontsize=8)
    fig.suptitle("F1. Risk–coverage: static HITL sweep vs GOV progressive autonomy (full stream)", x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    fig.savefig(FIG / "F1_risk_coverage.png", dpi=200); fig.savefig(FIG / "F1_risk_coverage.pdf")
    plt.close(fig)

    # F1b: Stage-2 window, one panel per seed (window items pooled over the categories that reached Stage 2)
    fig, axs = plt.subplots(1, len(SEEDS), figsize=(2.7 * len(SEEDS), 3.1), sharey=True)
    for ax, s in zip(np.atleast_1d(axs), SEEDS):
        ws = [r["df"][r["df"].amp_stage == 2] for r in runs if r["seed"] == s]
        ws = [w for w in ws if len(w)]
        ax.set_title(f"stream seed {s}", fontsize=9, loc="left", color=INK)
        if not ws:
            ax.text(0.5, 0.5, "no Stage 2\nitems" if any(r["seed"] == s for r in runs) else "not run", ha="center", transform=ax.transAxes, color=MUTED)
            continue
        w = pd.concat(ws, ignore_index=True)
        wr = rec[rec.image_id.isin(w.image_id)]
        cv = sweep(wr)
        ax.plot([x for x, _, _ in cv], [y for _, y, _ in cv], color=BLUE, lw=1.5)
        m = metrics(w)
        ax.plot(m["autonomous_rate"], m["autonomous_error_rate"], marker="o", ms=6, color=ORANGE, mec="white", mew=0.8, ls="none")
        km = metrics(matched_static(wr, m["autonomous_count"]))
        ax.plot(km["autonomous_rate"], km["autonomous_error_rate"], marker="^", ms=6, color=AQUA, mec="white", mew=0.8, ls="none")
        ax.set_xlabel("Coverage in Stage 2 window")
    np.atleast_1d(axs)[0].set_ylabel("Risk (error among autonomous)")
    from matplotlib.lines import Line2D
    fig.legend([Line2D([], [], color=BLUE, lw=1.5), Line2D([], [], color=ORANGE, marker="o", ls="none"), Line2D([], [], color=AQUA, marker="^", ls="none")],
               ["Static HITL sweep (same items)", "GOV progressive", "Static HITL at GOV's coverage"], loc="lower center", ncol=3, frameon=False, fontsize=8)
    fig.suptitle("F1b. Stage 2 window only: risk–coverage on the items GOV handled at Stage 2", x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0.1, 1, 0.93))
    fig.savefig(FIG / "F1b_stage2_window.png", dpi=200); fig.savefig(FIG / "F1b_stage2_window.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
