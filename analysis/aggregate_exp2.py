"""Experiment 2 aggregation (EXPERIMENT_PLAN_2.md sections 7, 9). Writes ONLY under results/exp2/.

Primary endpoint: pooled Stage 2 autonomous error rate of GOV vs static HITL at matched coverage on the same window items,
window = Stage 2 items from the first Stage 2 decision up to (excluding) the first re-entry to Stage 1.
Secondary: paired D1 (Experiment 1) vs D2 (Experiment 2) tables per cell, T2-T5 with both rows, gate history, determinism, figures.
Descriptive statistics only. Nothing here changes any configuration.
"""
import json, collections
from pathlib import Path
import numpy as np
import pandas as pd

import analysis.aggregate as A            # reuse pm/fmt/write_table/matched_static/sweep (write_table's TAB is redirected below)
from analysis.common import *

EXP2 = ROOT / "results" / "exp2"
A.TAB = EXP2 / "tables"
AGG2, FIG2 = EXP2 / "aggregate", EXP2 / "figures"
for d in (A.TAB, AGG2, FIG2):
    d.mkdir(parents=True, exist_ok=True)
E1_ROOT, E2_ROOT = ROOT / "results" / "runs", EXP2 / "runs"
BOOT_N, BOOT_SEED = 10000, 2026


# ----------------------------------------------------------------------------------------------- loading
def load_root(root):
    """First complete run per (category, seed)."""
    out = {}
    for mp in sorted(root.glob("*/manifest.json")):
        m = json.loads(mp.read_text())
        if "summary" not in m:
            continue
        key = (m["category"], int(m["stream_seed"]))
        if key in out:
            continue
        d = mp.parent
        df = pd.read_csv(d / "amp_decisions.csv").sort_values("stream_position").reset_index(drop=True)
        for c in ("correct", "false_acceptance", "false_rejection", "probe_forced_human", "hard_blocked"):
            df[c] = df[c].astype(bool)
        ev = [json.loads(l) for l in open(d / "amp_rlhf_events.jsonl")]
        out[key] = {"cat": key[0], "seed": key[1], "dir": d, "manifest": m, "df": df, "events": ev}
    return out


def stage2_window(df):
    """Contiguous Stage 2 segment from the first Stage 2 decision until the first re-entry to Stage 1 (exclusive)."""
    st = df.amp_stage.to_numpy()
    if not (st == 2).any():
        return df.iloc[0:0], None
    i0 = int(np.argmax(st == 2))
    j = i0
    while j < len(st) and st[j] == 2:
        j += 1
    reentry = int(df.stream_position.iloc[j]) if j < len(st) and st[j] < 2 else None
    return df.iloc[i0:j], reentry


def gate_rows(run):
    return [e["payload"]["decision_debug"] for e in run["events"] if e["event_type"] == "STAGE_TICK_SUMMARY"
            and (e["payload"].get("decision_debug") or {}).get("stage") == 1]


# ----------------------------------------------------------------------------------------------- primary endpoint
def primary_endpoint(rec, d2):
    rows = []
    for (cat, seed), r in sorted(d2.items()):
        w, reentry = stage2_window(r["df"])
        if w.empty:
            continue
        k = int((w.routing == "autonomous").sum())
        wr = rec[rec.image_id.isin(w.image_id)]
        st = A.matched_static(wr, k)
        sa = st[st.routing == "autonomous"]
        amp_a = w[w.routing == "autonomous"]
        rows.append({"category": cat, "stream_seed": seed, "window_items": len(w), "reentry_pos": reentry, "k": k,
                     "amp_errors": int((~amp_a.correct).sum()), "static_errors": int((~sa.correct).sum()),
                     "amp_fa": int(amp_a.false_acceptance.sum()), "static_fa": int(sa.false_acceptance.sum())})
    t = pd.DataFrame(rows)
    res = {"experiment": "vision-loco-exp2-v1", "window_definition": "first Stage 2 decision until first re-entry to Stage 1 (exclusive)",
           "runs_reaching_stage2": int(len(t)), "min_runs_required": 3}
    if t.empty:
        res.update({"reading": "insufficient data (no run reached Stage 2)"}); return res, t
    K = int(t.k.sum())
    res.update({"total_k": K, "amp_errors": int(t.amp_errors.sum()), "static_errors": int(t.static_errors.sum()),
                "amp_fa": int(t.amp_fa.sum()), "static_fa": int(t.static_fa.sum())})
    if K:
        r_amp, r_st = t.amp_errors.sum() / K, t.static_errors.sum() / K
        res.update({"r_amp": r_amp, "r_static": r_st, "delta": r_amp - r_st,
                    "fa_rate_amp": t.amp_fa.sum() / K, "fa_rate_static": t.static_fa.sum() / K})
        rng = np.random.default_rng(BOOT_SEED)
        idx = rng.integers(0, len(t), size=(BOOT_N, len(t)))
        ks, ea, es = t.k.to_numpy(), t.amp_errors.to_numpy(), t.static_errors.to_numpy()
        kk = ks[idx].sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            d = (ea[idx].sum(1) - es[idx].sum(1)) / kk
        d = d[np.isfinite(d)]
        lo, hi = np.percentile(d, [2.5, 97.5])
        res.update({"delta_ci95": [float(lo), float(hi)], "bootstrap": {"resamples": BOOT_N, "seed": BOOT_SEED, "unit": "runs",
                                                                         "finite_resamples": int(len(d))}})
        if len(t) < res["min_runs_required"]:
            res["reading"] = "insufficient data (fewer than 3 runs reached Stage 2); descriptive only"
        elif res["delta"] <= 0 and hi < 0.05:
            res["reading"] = "consistent with the hypothesis"
        elif lo > 0:
            res["reading"] = "contradicts the hypothesis"
        else:
            res["reading"] = "inconclusive"
    else:
        res["reading"] = "insufficient data (no autonomous decisions in any Stage 2 window)"
    res["reading_rule"] = ("consistent: delta <= 0 and CI upper < +0.05; contradicts: CI lower > 0; otherwise inconclusive; "
                           "< 3 runs reaching Stage 2: insufficient data (EXPERIMENT_PLAN_2.md section 7)")
    return res, t


# ----------------------------------------------------------------------------------------------- tables
def full_stream_by_seed(runs):
    out = {}
    for s in SEEDS:
        fr = [runs[(c, s)]["df"] for c in CATS if (c, s) in runs]
        if len(fr) == len(CATS):
            out[s] = pd.concat(fr, ignore_index=True)
    return out


def main():
    rec = load_records()
    d1, d2 = load_root(E1_ROOT), load_root(E2_ROOT)
    print(f"Experiment 1 cells: {len(d1)}/25 | Experiment 2 cells: {len(d2)}/25")
    (AGG2 / "coverage.json").write_text(json.dumps({"exp1_cells": len(d1), "exp2_cells": len(d2),
                                                    "exp2_missing": [list(x) for x in [(c, s) for s in SEEDS for c in CATS] if x not in d2]}, indent=1))
    if not d2:
        print("no Experiment 2 runs yet"); return

    # ---- concatenated raw D2 decisions
    pd.concat([r["df"].assign(stream_seed=r["seed"]) for r in d2.values()], ignore_index=True).to_csv(AGG2 / "all_decisions_D2.csv", index=False)

    # ---- primary endpoint
    pe, pet = primary_endpoint(rec, d2)
    pet.to_csv(AGG2 / "primary_endpoint_per_run.csv", index=False)
    (EXP2 / "primary_endpoint.json").write_text(json.dumps({**pe, "per_run": pet.to_dict("records")}, indent=2, default=float))
    print("PRIMARY:", json.dumps({k: pe.get(k) for k in ("runs_reaching_stage2", "total_k", "r_amp", "r_static", "delta", "delta_ci95", "reading")}, default=float))

    # ---- paired per-cell table (D1 vs D2)
    rows = []
    for key in sorted(set(d1) & set(d2)):
        cat, seed = key
        rr = {"category": cat, "stream_seed": seed}
        for tag, run in (("D1", d1[key]), ("D2", d2[key])):
            df = run["df"]
            w, reentry = stage2_window(df)
            ev = [e["event_type"] for e in run["events"]]
            aut = df[df.routing == "autonomous"]
            st = df.amp_stage.to_numpy()
            rr.update({f"{tag}_stage1_pos": int(df[df.amp_stage >= 1].stream_position.min()) if (st >= 1).any() else None,
                       f"{tag}_stage2_pos": int(df[df.amp_stage >= 2].stream_position.min()) if (st >= 2).any() else None,
                       f"{tag}_reached_stage2": bool((st == 2).any()), f"{tag}_candidates": ev.count("MODEL_CANDIDATE_READY"),
                       f"{tag}_reentry_pos": reentry, f"{tag}_window_items": len(w),
                       f"{tag}_window_autonomous": int((w.routing == "autonomous").sum()),
                       f"{tag}_window_coverage": float((w.routing == "autonomous").mean()) if len(w) else np.nan,
                       f"{tag}_hitl_rate": float((df.routing == "hitl").mean()),
                       f"{tag}_autonomous_n": len(aut), f"{tag}_autonomous_error_rate": float((~aut.correct).mean()) if len(aut) else np.nan,
                       f"{tag}_accuracy": float(df.correct.mean())})
        rows.append(rr)
    paired = pd.DataFrame(rows)
    paired.to_csv(AGG2 / "paired_cells.csv", index=False, float_format="%.6f")

    # ---- determinism per cell: identical Stage >=1 probabilities before the first stage divergence
    det = []
    for key in sorted(set(d1) & set(d2)):
        a, b = d2[key]["df"], d1[key]["df"]
        if not (a.image_id.to_numpy() == b.image_id.to_numpy()).all():
            det.append({"category": key[0], "stream_seed": key[1], "streams_identical": False}); continue
        div = np.where(a.amp_stage.to_numpy() != b.amp_stage.to_numpy())[0]
        cut = int(div[0]) if len(div) else len(a)
        pa, pb = a.amp_approval_probability.iloc[:cut], b.amp_approval_probability.iloc[:cut]
        both = pa.notna() & pb.notna()
        det.append({"category": key[0], "stream_seed": key[1], "streams_identical": True,
                    "first_stage_divergence_pos": int(a.stream_position.iloc[cut]) if len(div) else None, "compared_items": int(both.sum()),
                    "max_abs_prob_diff": float((pa[both] - pb[both]).abs().max()) if both.any() else None,
                    "score_presence_mismatch": int((pa.isna() != pb.isna()).sum())})
    detdf = pd.DataFrame(det)
    detdf.to_csv(AGG2 / "determinism_per_cell.csv", index=False)
    print("determinism: cells", len(detdf), "| max |dP| overall:", detdf.max_abs_prob_diff.max() if "max_abs_prob_diff" in detdf else None)

    # ---- gate history per run (D1 and D2)
    gh = []
    for tag, runs in (("D1", d1), ("D2", d2)):
        for (cat, seed), r in sorted(runs.items()):
            g = [x for x in gate_rows(r) if x.get("stage1_sample_size_met")]
            gh.append({"experiment": tag, "category": cat, "stream_seed": seed, "ticks_after_sample_gate": len(g),
                       "primary_pass_ticks": sum(bool(x.get("stage1_primary_met")) for x in g),
                       "stability_pass_ticks": sum(bool(x.get("stage1_stability_met")) for x in g),
                       "safety_pass_ticks": sum(bool(x.get("stage1_safety_met")) for x in g),
                       "all_pass_ticks": sum(bool(x.get("stage1_hard_gates_all_met")) for x in g),
                       "basis": next((x.get("stage1_agreement_basis") for x in g if x.get("stage1_agreement_basis")), None)})
    pd.DataFrame(gh).to_csv(AGG2 / "gate_history.csv", index=False)

    # ---- T2 (A-C, D1, D2) full stream
    base = {k: metrics(v) for k, v in A.cond_frames(rec).items()}
    s1, s2 = full_stream_by_seed(d1), full_stream_by_seed(d2)
    t2 = []
    for k, m in base.items():
        t2.append({"Condition": k, "Accuracy": A.fmt(m["accuracy"]), "FA rate": A.fmt(m["fa_rate"]), "FR rate": A.fmt(m["fr_rate"]),
                   "Autonomous rate": A.fmt(m["autonomous_rate"]), "HITL rate": A.fmt(m["hitl_rate"]),
                   "Autonomous error rate": A.fmt(m["autonomous_error_rate"]) if m["autonomous_count"] else "—"})
    for tag, name, sd in (("D1", "D1 GOV, Experiment 1 (execution-threshold gate)", s1), ("D2", "D2 GOV, Experiment 2 (recommendation gate)", s2)):
        if not sd:
            continue
        ms = {s: metrics(df) for s, df in sd.items()}
        col = lambda key: [ms[s][key] for s in sd]
        t2.append({"Condition": f"{name}, {len(sd)} seeds mean ± SD", "Accuracy": A.pm(col("accuracy")), "FA rate": A.pm(col("fa_rate")),
                   "FR rate": A.pm(col("fr_rate")), "Autonomous rate": A.pm(col("autonomous_rate")), "HITL rate": A.pm(col("hitl_rate")),
                   "Autonomous error rate": A.pm(col("autonomous_error_rate"), of=len(sd))})
        pd.DataFrame([{"experiment": tag, "stream_seed": s, **ms[s]} for s in sd]).to_csv(AGG2 / f"T2_per_seed_{tag}.csv", index=False, float_format="%.6f")
    A.write_table("T2_main_comparison_exp2", pd.DataFrame(t2),
                  "T2 (Experiment 2). Full-stream comparison of conditions A-C and GOV under the Experiment 1 (D1) and Experiment 2 (D2) Stage 1 gate.",
                  "Final accuracy must be read together with the HITL rate. A–C do not depend on stream order. D1/D2: pooled over 5 categories per seed, then mean ± SD across seeds.")

    # ---- T3 promotion per category, D1 vs D2
    t3 = []
    for cat in CATS:
        row = {"Category": cat}
        for tag, runs in (("D1", d1), ("D2", d2)):
            rs = [runs[(cat, s)] for s in SEEDS if (cat, s) in runs]
            if not rs:
                continue
            reached = [r for r in rs if (r["df"].amp_stage == 2).any()]
            s2pos = [int(r["df"][r["df"].amp_stage >= 2].stream_position.min()) for r in reached]
            reent = [stage2_window(r["df"])[1] for r in rs]
            ev = [collections.Counter(e["event_type"] for e in r["events"]) for r in rs]
            row.update({f"{tag} runs": len(rs), f"{tag} reached Stage 2": f"{len(reached)}/{len(rs)}",
                        f"{tag} Stage 2 entry (median)": A.fmt(float(np.median(s2pos)), 0) if s2pos else "never",
                        f"{tag} re-entries to Stage 1": sum(x is not None for x in reent),
                        f"{tag} candidates trained (total)": sum(c["MODEL_CANDIDATE_READY"] for c in ev),
                        f"{tag} rollbacks": sum(c["MODEL_ROLLBACK"] for c in ev), f"{tag} RLHF auto-disabled": sum(c["RLHF_AUTO_DISABLED"] > 0 for c in ev)})
        t3.append(row)
    A.write_table("T3_promotion_exp1_vs_exp2", pd.DataFrame(t3).fillna("—"), "T3 (Experiment 2). GOV promotion behaviour per category, D1 (Experiment 1) vs D2 (Experiment 2).",
                  "Re-entry = first return to Stage 1 after Stage 2. Per-cell detail: results/exp2/aggregate/paired_cells.csv.")

    # ---- T4 by anomaly type, D1 vs D2
    t4 = []
    for tag, name, sd in (("A", "A Human oracle", None), ("B", "B Model only", None), ("D1", "D1 GOV (Exp 1)", s1), ("D2", "D2 GOV (Exp 2)", s2)):
        if tag in ("A", "B"):
            f = A.cond_frames(rec)[[k for k in A.cond_frames(rec) if k.startswith(tag)][0]]
            for ty in TYPES:
                m = metrics(f[f.anomaly_type == ty])
                t4.append({"Condition": name, "Type": ty, "N": m["n"], "Error rate": A.fmt(1 - m["accuracy"]), "Autonomous rate": A.fmt(m["autonomous_rate"]),
                           "Autonomous error rate": A.fmt(m["autonomous_error_rate"]) if m["autonomous_count"] else "—"})
        elif sd:
            for ty in TYPES:
                ms = [metrics(df[df.anomaly_type == ty]) for df in sd.values()]
                t4.append({"Condition": f"{name}, mean ± SD ({len(sd)} seeds)", "Type": ty, "N": int(np.mean([m["n"] for m in ms])),
                           "Error rate": A.pm([1 - m["accuracy"] for m in ms]), "Autonomous rate": A.pm([m["autonomous_rate"] for m in ms]),
                           "Autonomous error rate": A.pm([m["autonomous_error_rate"] for m in ms], of=len(ms))})
    A.write_table("T4_by_anomaly_type_exp2", pd.DataFrame(t4), "T4 (Experiment 2). Results by anomaly type over the full stream.",
                  "anomaly_type was never visible to GOV.")

    # ---- T5 Stage 2 windows (window ends at re-entry), D1 and D2 separately
    t5 = []
    for tag, runs in (("D1", d1), ("D2", d2)):
        parts = collections.defaultdict(list)
        n_runs = 0
        for r in runs.values():
            w, _ = stage2_window(r["df"])
            if w.empty:
                continue
            n_runs += 1
            wr = rec[rec.image_id.isin(w.image_id)].copy()
            k = int((w.routing == "autonomous").sum())
            parts["GOV progressive"].append(w)
            parts[f"Static HITL δ={DELTA:g}σ"].append(condition_static(wr, DELTA))
            parts["Static HITL matched coverage"].append(A.matched_static(wr, k))
            parts["Model only"].append(condition_model_only(wr))
        for nm, fr in parts.items():
            m = metrics(pd.concat(fr, ignore_index=True))
            lo, hi = wilson(m["autonomous_errors"], m["autonomous_count"]) if m["autonomous_count"] else (np.nan, np.nan)
            t5.append({"Experiment": tag, "Condition": nm, "Runs": n_runs, "Window items": m["n"], "Autonomous": m["autonomous_count"],
                       "Coverage": A.fmt(m["autonomous_rate"]), "Autonomous errors": m["autonomous_errors"],
                       "Autonomous error rate [Wilson 95%]": (f"{m['autonomous_error_rate']:.3f} [{lo:.3f}, {hi:.3f}]" if m["autonomous_count"] else "—"),
                       "Autonomous FA": m["autonomous_fa"], "Accuracy": A.fmt(m["accuracy"])})
    A.write_table("T5_stage2_window_exp2", pd.DataFrame(t5), "T5 (Experiment 2). Stage 2 window comparison: every condition on exactly the items GOV handled at Stage 2 (window ends at first re-entry to Stage 1), pooled over runs.",
                  "Pooled counts, not seed means; Wilson intervals treat items as independent and are descriptive. Primary endpoint: results/exp2/primary_endpoint.json.")

    make_figures(rec, d1, d2)
    print("tables:", sorted(p.name for p in A.TAB.glob("*.csv")))


# ----------------------------------------------------------------------------------------------- figures
def make_figures(rec, d1, d2):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
    BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"     # validated categorical slots 1-3 (all-pairs safe)
    plt.rcParams.update({"font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6})
    panels = [("All categories", None)] + [(c.replace("_", " "), c) for c in CATS]
    fig, axs = plt.subplots(2, 3, figsize=(9.2, 5.8), sharex=True)
    for ax, (title, cat) in zip(axs.ravel(), panels):
        sub = rec if cat is None else rec[rec.category == cat]
        cv = A.sweep(sub)
        ax.plot([x for x, _, _ in cv], [y for _, y, _ in cv], color=BLUE, lw=1.6, label="Static HITL (δ sweep 0–5σ)")
        m1 = metrics(condition_static(sub, DELTA))
        ax.plot(m1["autonomous_rate"], m1["autonomous_error_rate"], marker="D", ms=6, mfc="white", mec=BLUE, mew=1.6, ls="none", label=f"Static HITL δ={DELTA:g}σ")
        for tag, runs, color, mk in (("D1 GOV (Exp 1)", d1, ORANGE, "o"), ("D2 GOV (Exp 2)", d2, AQUA, "s")):
            pts, nrun = [], 0
            for s in SEEDS:
                fr = [runs[(c, s)]["df"] for c in (CATS if cat is None else [cat]) if (c, s) in runs]
                if len(fr) != (len(CATS) if cat is None else 1):
                    continue
                nrun += 1
                m = metrics(pd.concat(fr, ignore_index=True))
                if m["autonomous_count"]:
                    pts.append((m["autonomous_rate"], m["autonomous_error_rate"]))
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker=mk, ms=5.5, color=color, mec="white", mew=0.8, ls="none", label=f"{tag}: one point per seed (full stream)")
            ax.text(0.02, 0.97 - (0.0 if tag.startswith("D1") else 0.075), f"{tag[:2]}: {len(pts)}/{nrun} seeds with any autonomy", transform=ax.transAxes, va="top", fontsize=6.5, color=MUTED)
        ax.set_title(title, fontsize=9, color=INK, loc="left"); ax.set_xlim(-0.02, 1.02)
    for ax in axs[1]:
        ax.set_xlabel("Coverage (fraction executed autonomously)")
    for ax in axs[:, 0]:
        ax.set_ylabel("Risk (error rate among autonomous)")
    seen = {}
    for a_ in axs.ravel():
        for h_, l_ in zip(*a_.get_legend_handles_labels()):
            seen.setdefault(l_, h_)
    fig.legend(list(seen.values()), list(seen.keys()), loc="lower center", ncol=3, frameon=False, fontsize=7.5)
    fig.suptitle("F1 (Experiment 2). Risk–coverage: static HITL sweep vs GOV under the Experiment 1 and Experiment 2 gates (full stream)", x=0.01, ha="left", fontsize=9.5, color=INK)
    fig.tight_layout(rect=(0, 0.09, 1, 0.95))
    fig.savefig(FIG2 / "F1_risk_coverage_exp2.png", dpi=200); fig.savefig(FIG2 / "F1_risk_coverage_exp2.pdf"); plt.close(fig)

    # F1b: Stage 2 windows pooled per seed (window ends at re-entry): static sweep on those items, GOV D2 and matched static; D1 as hollow marker
    fig, axs = plt.subplots(1, len(SEEDS), figsize=(2.7 * len(SEEDS), 3.2), sharey=True)
    for ax, s in zip(np.atleast_1d(axs), SEEDS):
        ax.set_title(f"stream seed {s}", fontsize=9, loc="left", color=INK)
        ws = [stage2_window(r["df"])[0] for (c, sd), r in d2.items() if sd == s]
        ws = [w for w in ws if len(w)]
        w1 = [stage2_window(r["df"])[0] for (c, sd), r in d1.items() if sd == s]
        w1 = [w for w in w1 if len(w)]
        if not ws:
            ax.text(0.5, 0.5, "no Stage 2 items\n(Experiment 2)" if any(sd == s for _, sd in d2) else "not run", ha="center", transform=ax.transAxes, color=MUTED)
        else:
            w = pd.concat(ws, ignore_index=True); wr = rec[rec.image_id.isin(w.image_id)]
            cv = A.sweep(wr); ax.plot([x for x, _, _ in cv], [y for _, y, _ in cv], color=BLUE, lw=1.5)
            m = metrics(w); ax.plot(m["autonomous_rate"], m["autonomous_error_rate"], marker="s", ms=6, color=AQUA, mec="white", mew=0.8, ls="none")
            km = metrics(A.matched_static(wr, m["autonomous_count"])); ax.plot(km["autonomous_rate"], km["autonomous_error_rate"], marker="^", ms=6, color=BLUE, mec="white", mew=0.8, ls="none")
        if w1:
            m = metrics(pd.concat(w1, ignore_index=True))
            if m["autonomous_count"]:
                ax.plot(m["autonomous_rate"], m["autonomous_error_rate"], marker="o", ms=6, mfc="white", mec=ORANGE, mew=1.6, ls="none")
        ax.set_xlabel("Coverage in Stage 2 window")
    np.atleast_1d(axs)[0].set_ylabel("Risk (error among autonomous)")
    from matplotlib.lines import Line2D
    fig.legend([Line2D([], [], color=BLUE, lw=1.5), Line2D([], [], color=AQUA, marker="s", ls="none"), Line2D([], [], color=BLUE, marker="^", ls="none"),
                Line2D([], [], color=ORANGE, marker="o", mfc="white", ls="none")],
               ["Static HITL sweep (same items)", "D2 GOV (Exp 2)", "Static HITL at D2's coverage", "D1 GOV (Exp 1, own window)"], loc="lower center", ncol=4, frameon=False, fontsize=7.5)
    fig.suptitle("F1b (Experiment 2). Stage 2 windows only (each window ends at first re-entry to Stage 1)", x=0.01, ha="left", fontsize=9.5, color=INK)
    fig.tight_layout(rect=(0, 0.1, 1, 0.93))
    fig.savefig(FIG2 / "F1b_stage2_window_exp2.png", dpi=200); fig.savefig(FIG2 / "F1b_stage2_window_exp2.pdf"); plt.close(fig)


if __name__ == "__main__":
    main()
