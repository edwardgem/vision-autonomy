"""Section 4 figures (Experiments 1-2). Values come from committed aggregates / per-decision records."""
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pathlib import Path
REPO = Path(__file__).resolve().parents[2]      # repository root
OUT = str(Path(__file__).resolve().parent / "out") + "/"
Path(OUT).mkdir(exist_ok=True)
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
INK, INK2, GRID, GREY = "#0b0b0b", "#52514e", "#e4e3df", "#9b9a95"
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                     "font.size": 8, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.linewidth": 0.6, "legend.frameon": False, "mathtext.fontset": "stix"})
W = 4.8
CATS = ["breakfast_box", "juice_bottle", "pushpins", "screw_bag", "splicing_connectors"]
NICE = {c: c.replace("_", " ") for c in CATS}
STY = {"breakfast_box": (BLUE, "o"), "juice_bottle": (ORANGE, "s"), "pushpins": (AQUA, "^"),
       "screw_bag": (YELLOW, "D"), "splicing_connectors": (MAGENTA, "v")}


def clean(ax, grid="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if grid:
        ax.grid(axis=grid, color=GRID, lw=0.5)
    ax.set_axisbelow(True)


# ---------- Fig 4: Stage 1 agreement on identical rows (items 81-160), Exp 1 basis vs Exp 2 basis ----------
a = pd.read_csv(f"{REPO}/results/exp2/aggregate/stage1_cumulative_agreement.csv")
fig, ax = plt.subplots(figsize=(W, 2.55))
ax.axvspan(0.70, 0.95, color="#f1f0ec", zorder=0); ax.axhspan(0.70, 0.95, color="#f1f0ec", zorder=0)
ax.axvline(0.70, color=INK2, lw=0.8, ls="--"); ax.axhline(0.70, color=INK2, lw=0.8, ls="--")
ax.plot([0.38, 0.95], [0.38, 0.95], color=GRID, lw=0.8)
rng = np.random.default_rng(0)
for c in CATS:
    s = a[a.cat == c]
    col, mk = STY[c]
    jx = rng.uniform(-0.004, 0.004, len(s))
    ax.scatter(s.exp1_exec_agree_items81_160 + jx, s.rec_agree_items81_160, s=22, marker=mk, color=col,
               edgecolor="white", linewidth=0.6, label=NICE[c], zorder=3)
ax.text(0.715, 0.93, "gate passes\n(Exp. 1 basis)", fontsize=6.2, color=INK2, va="top")
ax.text(0.39, 0.93, "gate passes only under the Exp. 2 basis", fontsize=6.2, color=INK2, va="top")
ax.text(0.94, 0.39, "passes under neither basis", fontsize=6.2, color=INK2, va="bottom", ha="right")
ax.annotate("juice bottle s4 (all p ≥ 0.917)", (0.861, 0.861), xytext=(0.76, 0.79), fontsize=6, color=INK2,
            arrowprops=dict(arrowstyle="-", color=INK2, lw=0.5))
ax.set_xlim(0.38, 0.95); ax.set_ylim(0.38, 0.95)
ax.set_xlabel(r"Cumulative agreement, Exp. 1 basis ($\theta_{\mathrm{cum}}=0.90$)")
ax.set_ylabel(r"Exp. 2 basis ($\theta_{\mathrm{cum}}=0.65$)")
clean(ax, None)
ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=6.5, handletextpad=0.3)
fig.tight_layout(pad=0.3); fig.savefig(OUT + "fig_stage1_agreement.png", dpi=300); plt.close(fig)

# ---------- Fig 5: Stage 2 windows of Experiment 2, risk-coverage per window ----------
d = pd.read_csv(f"{REPO}/results/exp2/aggregate/all_decisions_D2.csv")
w = d[d.amp_stage == 2].copy()
runs = sorted(w.groupby(["category", "stream_seed"]).groups.keys(), key=lambda t: (CATS.index(t[0]), t[1]))
fig, axes = plt.subplots(3, 3, figsize=(W, 3.7), sharex=True, sharey=True)
check = []
for ax, (c, sd) in zip(axes.flat, runs):
    s = w[(w.category == c) & (w.stream_seed == sd)].copy()
    s["err"] = s.proposal != s.ground_truth   # proposal error (what static HITL would execute), not the platform's final correctness
    o = s.sort_values(["margin_abs", "image_id"], ascending=[False, True])
    cum = o.err.cumsum().to_numpy(); n = np.arange(1, len(o) + 1)
    ax.plot(n / len(o), cum / n, color=GREY, lw=1.1, label="static HITL (margin sweep)")
    auto = s[s.routing == "autonomous"]
    k = len(auto); e = int((~auto.correct.astype(bool)).sum())
    st_e = int(cum[k - 1]) if k else 0
    check.append((c, sd, len(s), k, e, st_e))
    ax.plot(k / len(s), st_e / k, "o", ms=4, mfc="white", mec=INK2, mew=0.9, label="static, matched coverage", zorder=3)
    ax.plot(k / len(s), e / k, "o", ms=4.5, color=BLUE, mec="white", mew=0.5, label="governance (Stage 2 window)", zorder=4)
    ax.set_title(f"{NICE[c]} s{sd}  (k={k}, err {e} vs {st_e})", fontsize=6.2, pad=2)
    clean(ax)
    ax.tick_params(labelsize=6)
for ax in axes[-1]:
    ax.set_xlabel("coverage", fontsize=7)
for ax in axes[:, 0]:
    ax.set_ylabel("autonomous error", fontsize=7)
axes[0, 0].set_ylim(-0.01, 0.32); axes[0, 0].set_xlim(0, 1.02); axes[0, 0].set_xticks([0, 0.5, 1.0])
h, l = axes[0, 0].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=3, fontsize=6.5, bbox_to_anchor=(0.5, 1.0))
fig.tight_layout(pad=0.3, rect=(0, 0, 1, 0.95), h_pad=0.6, w_pad=0.4)
fig.savefig(OUT + "fig_stage2_windows.png", dpi=300); plt.close(fig)
print(check)

# ---------- Fig 6: autonomous executions by proposal (action) class, Stage 2 windows of Experiment 2 ----------
p = pd.read_csv(f"{REPO}/results/exp2/aggregate/autonomous_by_proposal_exploratory.csv")
s4 = p.cell == "juice_bottle s4"
groups = [("governance,\n8 windows", p[~s4]), ("governance,\njuice bottle s4", p[s4]), ("static, matched\n(all 9 windows)", p)]
fig, axes = plt.subplots(1, 2, figsize=(W, 1.55), sharey=True)
for ax, (cls, lab) in zip(axes, [("def", "Reject part (defective proposal)"), ("good", "Release part (good proposal)")]):
    for yi, (name, g) in enumerate(groups):
        pre = "amp" if name.startswith("governance") else "st"
        tot, bad = int(g[f"{pre}_{cls}"].sum()), int(g[f"{pre}_{cls}_wrong"].sum())
        ax.barh(yi, tot - bad, color=BLUE, height=0.55, edgecolor="white", lw=0.4)
        ax.barh(yi, bad, left=tot - bad, color=ORANGE, height=0.55, hatch="////", edgecolor="white", lw=0.4)
        ax.text(tot + 6, yi, f"{tot} ({bad} wrong)", va="center", fontsize=6.3, color=INK)
    ax.set_title(lab, fontsize=7.5, pad=3); ax.set_xlim(0, 560)
    clean(ax, "x"); ax.tick_params(labelsize=6.5)
    ax.set_xlabel("autonomous executions", fontsize=7)
axes[0].set_yticks(range(3), [g[0] for g in groups]); axes[0].invert_yaxis()
from matplotlib.patches import Patch
fig.legend([Patch(color=BLUE), Patch(fc=ORANGE, hatch="////", ec="white")], ["correct", "wrong"],
           loc="center right", ncol=1, fontsize=6.3, bbox_to_anchor=(0.99, 0.45))
fig.tight_layout(pad=0.3, w_pad=0.8)
fig.savefig(OUT + "fig_action_class.png", dpi=300); plt.close(fig)
