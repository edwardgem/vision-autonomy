"""Section 3 figures for the CVC 2027 paper. All values computed from frozen artifacts or exact formulas."""
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from scipy.stats import beta, binom

from pathlib import Path
REPO = Path(__file__).resolve().parents[2]      # repository root
OUT = str(Path(__file__).resolve().parent / "out") + "/"
Path(OUT).mkdir(exist_ok=True)
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                     "font.size": 8, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.linewidth": 0.6, "legend.frameon": False, "mathtext.fontset": "stix"})
W = 4.8


def clean(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.5); ax.set_axisbelow(True)


def ucb(k, n, a=0.05):
    return 1.0 if k >= n else beta.ppf(1 - a, k + 1, n - k)


def lcb(k, n, a=0.05):
    return 0.0 if k <= 0 else beta.ppf(a, k, n - k + 1)


# ---------- Fig 1: proposal error by category and ground-truth type ----------
d = pd.read_csv(f"{REPO}/results/inputs/decision_records.csv")
d["err"] = d.proposal != d.ground_truth
cats = ["breakfast_box", "juice_bottle", "pushpins", "screw_bag", "splicing_connectors"]
labels = ["breakfast\nbox", "juice\nbottle", "pushpins", "screw\nbag", "splicing\nconnectors", "All"]
tab = d.groupby(["category", "anomaly_type"]).err.mean().unstack()
tab.loc["All"] = d.groupby("anomaly_type").err.mean()
fig, ax = plt.subplots(figsize=(W, 2.0))
x = np.arange(6); bw = 0.26
series = [("good", "Good part (false alarm)", BLUE, None), ("structural", "Structural anomaly (missed)", ORANGE, None),
          ("logical", "Logical anomaly (missed)", AQUA, "////")]
for j, (t, lab, c, h) in enumerate(series):
    v = tab.loc[cats + ["All"], t].to_numpy()
    ax.bar(x + (j - 1) * bw, v, bw - 0.03, color=c, label=lab, hatch=h, edgecolor="white", linewidth=0.4)
    for xi, vi in zip(x, v):
        ax.text(xi + (j - 1) * bw, vi + 0.015, f"{vi:.2f}", ha="center", va="bottom", fontsize=5.5, color=INK2)
ax.axvline(4.5, color=GRID, lw=0.8)
ax.set_xticks(x, labels); ax.set_ylim(0, 1.08); ax.set_ylabel("Proposal error rate")
clean(ax); ax.legend(loc="upper left", ncol=3, fontsize=6.5, bbox_to_anchor=(0, 1.13))
fig.tight_layout(pad=0.3); fig.savefig(OUT + "fig_perception.png", dpi=300); plt.close(fig)

# ---------- Fig 2: Experiment 3 stream and lifecycle schematic ----------
fig, ax = plt.subplots(figsize=(W, 1.75))
rows = {"Shift arm": 1.0, "Stationary arm": 0.0}
comp = {"Shift arm": [(0, 380, [(342, BLUE), (38, ORANGE)]), (380, 630, [(150, BLUE), (25, ORANGE), (75, AQUA)])],
        "Stationary arm": [(0, 380, [(342, BLUE), (38, ORANGE)]), (380, 630, [(225, BLUE), (25, ORANGE)])]}
for name, y in rows.items():
    for s0, s1, parts in comp[name]:
        tot = sum(p for p, _ in parts); cur = s0
        for p, c in parts:
            wdt = (s1 - s0) * p / tot
            ax.add_patch(Rectangle((cur, y - 0.3), wdt, 0.6, fc=c, hatch="////" if c == AQUA else None,
                                   ec="white", lw=0.6))
            cur += wdt
    ax.text(-8, y, name, ha="right", va="center", fontsize=7.5, color=INK)
for xv, lab in [(150, "Stage 0 ends (150 human rows)"), (380, "change point (item 381)")]:
    ax.plot([xv, xv], [-0.45, 1.75], color=INK, lw=0.8, ls="--")
    ax.text(xv, 1.8, lab, ha="center", va="bottom", fontsize=6.5, color=INK)
ax.annotate("", xy=(310, 1.47), xytext=(190, 1.47), arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.7))
ax.text(192, 1.52, "authorization (planning q10–q90)", ha="left", va="bottom", fontsize=5.8, color=INK2)
ax.text(386, -0.62, "post, stationary: good 90%, structural 10%", ha="left", fontsize=6.0, color=INK2)
ax.text(386, 1.36, "post, shift: good 60%, struct. 10%, logical 30%", ha="left", fontsize=6.0, color=INK2)
ax.text(190, -0.62, "pre: good 90%, structural 10%", ha="center", fontsize=6.2, color=INK2)
ax.set_xlim(-110, 640); ax.set_ylim(-0.8, 2.25); ax.set_yticks([])
ax.set_xticks([0, 100, 200, 300, 380, 500, 630]); ax.set_xlabel("Stream position (items)")
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
handles = [Rectangle((0, 0), 1, 1, color=BLUE), Rectangle((0, 0), 1, 1, color=ORANGE),
           Rectangle((0, 0), 1, 1, fc=AQUA, hatch="////", ec="white")]
ax.legend(handles, ["good", "structural", "logical"], loc="upper left", ncol=1, fontsize=6.2,
          bbox_to_anchor=(-0.01, 1.04), handlelength=1.2)
fig.tight_layout(pad=0.3); fig.savefig(OUT + "fig_exp3_stream.png", dpi=300); plt.close(fig)

# ---------- Fig 3: certification requirement and probe revocation power ----------
eps = 0.10
fig, (a1, a2) = plt.subplots(1, 2, figsize=(W, 1.95))
ns = np.arange(30, 151)
kmax = [max([k for k in range(n + 1) if ucb(k, n) <= eps], default=-1) for n in ns]
a1.step(ns, kmax, where="post", color=BLUE, lw=1.4)
for n in (30, 50, 100):
    k = kmax[n - 30]; a1.plot(n, k, "o", ms=3.5, color=BLUE, mec="white", mew=0.6, zorder=3)
a1.text(32, 8.6, "n = 30:  k* = 0\nn = 50:  k* = 1\nn = 100: k* = 4", va="top", fontsize=6.2, color=INK2)
a1.set_xlabel("Slice size $n_t$ (human-labelled rows)"); a1.set_ylabel("Max errors $k^*$ that certify")
a1.set_yticks(range(0, 10, 2)); a1.set_ylim(-0.3, 9)
a1.set_title("(a) Qualification: UCB$_{95}(k,n)\\leq 0.10$", fontsize=7.5)
clean(a1)
rs = np.linspace(0, 0.5, 201)
for n, c in [(10, ORANGE), (20, BLUE), (40, AQUA)]:
    kneed = min(k for k in range(n + 1) if lcb(k, n) > eps)
    pw = [binom.sf(kneed - 1, n, r) for r in rs]
    a2.plot(rs, pw, color=c, lw=1.4, label=f"{n} probes (revoke if $k\\geq${kneed})")
a2.axvline(eps, color=INK2, lw=0.8, ls="--"); a2.text(eps + 0.01, 0.95, "budget", fontsize=6, color=INK2)
a2.set_xlabel("True error of authorized slice $r$"); a2.set_ylabel("P(revoke)")
a2.set_title("(b) Monitoring: P(LCB$_{95}(k,n)>0.10$)", fontsize=7.5)
a2.legend(fontsize=6, loc="lower right"); a2.set_ylim(0, 1.02); clean(a2)
fig.tight_layout(pad=0.3, w_pad=1.2); fig.savefig(OUT + "fig_bounds.png", dpi=300); plt.close(fig)

# verification against plan T2/T3
print({n: kmax[n - 30] for n in (30, 40, 50, 60, 80, 100)})
for n in (10, 20, 40):
    kneed = min(k for k in range(n + 1) if lcb(k, n) > eps)
    print(n, kneed, [round(binom.sf(kneed - 1, n, r), 3) for r in (0.15, 0.2, 0.25, 0.3, 0.4)])
print(tab.round(3))
