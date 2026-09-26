"""Experiment 3 figure for Section 4.5. Recomputes governance/T1/T0 decisions per item from the raw run records and
asserts the totals equal the preregistered analysis (exp3_primary.json / exp3_runs.csv)."""
import glob, json, math
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Rectangle
from matplotlib.lines import Line2D

from pathlib import Path
REPO = Path(__file__).resolve().parents[2]      # repository root
OUT = str(Path(__file__).resolve().parent / "out") + "/"
Path(OUT).mkdir(exist_ok=True)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, LIGHT = "#0b0b0b", "#52514e", "#e4e3df", "#d9d8d3"
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                     "font.size": 8, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.linewidth": 0.6, "legend.frameon": False})
M = {"probe_initial_decisions": 50, "probe_rate_initial": 0.3, "probe_rate": 0.3, "min_probes_per_decisions": [2, 50]}


def probes_due(n, m):
    if n <= 0:
        return 0
    init = min(n, m["probe_initial_decisions"]); rest = max(0, n - m["probe_initial_decisions"])
    by_rate = math.ceil(init * m["probe_rate_initial"] + rest * m["probe_rate"] - 1e-9)
    per, block = m["min_probes_per_decisions"]
    return min(n, max(by_rate, (n // block) * per))


sec = pd.read_csv(f"{REPO}/results/exp3/aggregate/secondary_runs.csv")
prim = json.load(open(f"{REPO}/results/exp3/aggregate/exp3_primary.json"))
sh = sec[(sec.arm == "shift") & sec.eligible].sort_values("seed")
rows, cum = [], {"gov": np.zeros(250), "T1": np.zeros(250), "T0": np.zeros(250)}
for _, s in sh.iterrows():
    f = glob.glob(f"{REPO}/results/exp3/runs/*vis-exp3-shift-s{int(s.seed)}-*/amp_decisions.csv")
    assert len(f) == 1
    r = pd.read_csv(f[0])
    pos = r.stream_position.to_numpy(); good = (r.proposal == "good").to_numpy()
    bad = (r.ground_truth == "defective").to_numpy()
    P = pd.to_numeric(r.amp_approval_probability, errors="coerce").to_numpy()
    gov = (r.routing == "autonomous").to_numpy() & good
    t0 = good & (pos > s.auth_pos) & (P >= s.auth_thr)
    t1 = np.zeros(len(r), bool); elig = probes = 0
    for i in np.where(t0)[0]:
        due = probes_due(elig + 1, M); elig += 1
        if probes < due:
            probes += 1
        else:
            t1[i] = True
    post = pos > 380
    for name, ex in (("gov", gov), ("T1", t1), ("T0", t0)):
        e = ex & bad & post
        idx = pos[e] - 381
        np.add.at(cum[name], idx, 1)
        col = {"gov": "amp_esc_post", "T1": "t1_esc_post", "T0": "t0_esc_post"}[name]
        assert int(e.sum()) == int(s[col]), (s.seed, name, int(e.sum()), s[col])
    rej_probe = pos[(r.governance_outcome == "probe").to_numpy() & (r.oracle_response == "reject").to_numpy()]
    esc = pos[gov & bad]
    rows.append(dict(seed=int(s.seed), auth=s.auth_pos, thr=s.auth_thr,
                     rev=(s.revoke_pos if s.revocations > 0 else None), rej=rej_probe, esc=esc))
tot = {k: int(v.sum()) for k, v in cum.items()}
assert tot == {"gov": prim["escapes_post"]["GOV"], "T1": prim["escapes_post"]["T1"], "T0": prim["escapes_post"]["T0"]}, tot
print("totals match preregistered:", tot)

fig, (a1, a2) = plt.subplots(2, 1, figsize=(4.8, 4.3), gridspec_kw={"height_ratios": [2.3, 1.35]})
for y, row in enumerate(rows):
    a1.add_patch(Rectangle((0.5, y - 0.3), row["auth"] - 0.5, 0.6, fc=LIGHT, ec="none"))
    end = row["rev"] if row["rev"] is not None else 630.5
    a1.add_patch(Rectangle((row["auth"], y - 0.3), end - row["auth"], 0.6, fc=BLUE, ec="none"))
    if row["rev"] is not None:
        a1.add_patch(Rectangle((row["rev"], y - 0.3), 630.5 - row["rev"], 0.6, fc=LIGHT, ec="white", hatch="////", lw=0))
    a1.scatter(row["esc"], np.full(len(row["esc"]), y + 0.42), s=5, color=ORANGE, lw=0, zorder=3)
    a1.scatter(row["rej"], np.full(len(row["rej"]), y - 0.42), marker="|", s=14, color=INK, lw=0.7, zorder=3)
    a1.text(634, y, f"θ={row['thr']:.2f}", va="center", fontsize=5.8, color=INK2)
a1.axvline(380.5, color=INK, lw=0.9, ls="--")
a1.text(383, -0.55, "change point (item 381)", ha="left", va="center", fontsize=6.3, color=INK)
a1.set_yticks(range(len(rows)), [f"s{r['seed']}" for r in rows]); a1.invert_yaxis()
a1.set_xlim(0, 665); a1.set_ylim(len(rows) - 0.4, -0.85)
a1.set_ylabel("eligible shift run (seed)", fontsize=7)
a1.tick_params(labelsize=6.3)
for s_ in ("top", "right"):
    a1.spines[s_].set_visible(False)
a1.set_title("(a) Authority timeline of the release (good) class", fontsize=7.5, pad=3)
h = [Patch(fc=LIGHT, label="human review (Stage 0 / qualifying)"), Patch(fc=BLUE, label="authorized"),
     Patch(fc=LIGHT, hatch="////", ec="white", label="revoked → human review"),
     Line2D([], [], marker="o", ls="", ms=2.5, color=ORANGE, label="wrong autonomous release"),
     Line2D([], [], marker="|", ls="", ms=5, color=INK, label="probe rejected by reviewer")]
fig.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=3, fontsize=5.8, handlelength=1.4,
           columnspacing=0.9)

x = np.arange(381, 631)
for name, col, lab in (("T0", AQUA, "T0 (static, no probes)"), ("T1", ORANGE, "T1 (static twin, same probes)"),
                       ("gov", BLUE, "governance platform")):
    c = np.cumsum(cum[name]); a2.plot(x, c, color=col, lw=1.5)
    a2.text(632, c[-1], f"{lab}: {int(c[-1])}", va="center", fontsize=6.2, color=INK)
a2.set_xlim(381, 740); a2.set_xticks([381, 450, 500, 550, 600, 630])
a2.set_xlabel("stream position (post-change segment)", fontsize=7)
a2.set_ylabel("cumulative escapes", fontsize=7)
a2.set_title("(b) Post-change escapes pooled over the 10 eligible shift runs", fontsize=7.5, pad=3)
a2.grid(axis="y", color=GRID, lw=0.5); a2.set_axisbelow(True); a2.tick_params(labelsize=6.3)
for s_ in ("top", "right"):
    a2.spines[s_].set_visible(False)
fig.tight_layout(pad=0.3, h_pad=0.9, rect=(0, 0, 1, 0.93))
fig.savefig(OUT + "fig_exp3_timeline.png", dpi=300); plt.close(fig)
