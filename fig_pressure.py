"""Figure: relay pressure -- three-world scorecard + learned bridge map."""
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize

from experiment_pressure import DenseWorld, PressureFlood

GREEN = "#2ca02c"
GRAY = "#7f7f7f"
RED = "#d62728"
BLUE = "#1f77b4"

fig = plt.figure(figsize=(13.4, 5.2))
gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1.0], wspace=0.16)

# ---- (a) three-world scorecard (numbers from experiment_pressure.py) ----
ax = fig.add_subplot(gs[0])
worlds = ["DENSE\n3 cliques + 2 bridges\n(suppression regime)",
          "BRAID d=50\nsparse chain\n(persistence regime)",
          "NORWAY\norganic replay\n(mixed regime)"]
configs = [
    ("plain flood", GRAY, [(78.5, 47.1), (17.7, 49.5), (32.7, 18.5)]),
    ("cancel@1 (shipped-style)", BLUE, [(35.1, 4.2), (0.0, 9.2), (30.7, 15.4)]),
    ("blanket persist R=3", "#9467bd", [(90.4, 80.0), (96.3, 134.0), (53.9, 59.0)]),
    ("PRESSURE (no config)", GREEN, [(83.7, 18.4), (97.7, 133.2), (54.1, 58.3)]),
]
n_w, n_c = len(worlds), len(configs)
width = 0.19
for ci, (label, color, vals) in enumerate(configs):
    xs = [wi + (ci - (n_c - 1) / 2) * width for wi in range(n_w)]
    ys = [v[0] for v in vals]
    b = ax.bar(xs, ys, width * 0.92, color=color,
               edgecolor="white", linewidth=0.5, label=label)
    for x, (cov, tx) in zip(xs, vals):
        ax.text(x, cov + 1.5, f"{cov:.0f}%", ha="center", fontsize=7.6,
                fontweight="bold")
        ax.text(x, max(cov - 7, 2.5), f"{tx:.0f}tx", ha="center", fontsize=6.8,
                color="white" if cov > 12 else "#333")
ax.set_xticks(range(n_w))
ax.set_xticklabels(worlds, fontsize=8.5)
ax.set_ylabel("coverage / delivery  %")
ax.set_ylim(0, 108)
ax.legend(fontsize=8, loc="upper left", ncol=2)
ax.grid(alpha=0.25, axis="y")
ax.set_title("(a)  one config-free rule vs static policies, three regimes\n"
             "(bars: effectiveness; inset numbers: airtime per packet)",
             fontsize=10, loc="left")

# ---- (b) learned pressure map of the dense world ----
axb = fig.add_subplot(gs[1])
world = DenseWorld(0.9, 0.8, seed=11)
proto = PressureFlood()
for _ in range(330):
    proto.flood(world, world.src, hop_limit=10)

pos = {}
centers = [(-2.4, 0.0), (0.0, 0.0), (2.4, 0.0)]
for c in range(3):
    cx, cy = centers[c]
    for i in range(20):
        ang = 2 * math.pi * i / 20 + math.pi / 20
        r = 0.85
        pos[f"!{c:02x}{i:02x}0000"] = (cx + r * math.cos(ang),
                                       cy + r * math.sin(ang))
# bridge endpoints face their partner clique
pos["!00130000"] = (centers[0][0] + 0.85, 0.0)
pos["!01000000"] = (centers[1][0] - 0.85, 0.0)
pos["!01130000"] = (centers[1][0] + 0.85, 0.0)
pos["!02000000"] = (centers[2][0] - 0.85, 0.0)

bridges = [("!00130000", "!01000000"), ("!01130000", "!02000000")]
for a, b in bridges:
    (x1, y1), (x2, y2) = pos[a], pos[b]
    axb.plot([x1, x2], [y1, y2], "-", color="#999", lw=1.6, zorder=1)
    axb.plot([x1, x2], [y1, y2], "--", color=RED, lw=1.0, zorder=2)

norm = Normalize(vmin=0.0, vmax=1.0)
cmap = plt.get_cmap("RdYlGn")
for n, (x, y) in pos.items():
    p = proto.pressure(n)
    big = p >= 0.7
    axb.scatter([x], [y], s=200 if big else 90, c=[cmap(norm(p))],
                edgecolors="#333" if big else "#999",
                linewidths=1.6 if big else 0.6, zorder=3)
axb.scatter(*pos[world.src], s=260, facecolors="none", edgecolors=BLUE,
            linewidths=2.2, zorder=4)
axb.annotate("src", pos[world.src], textcoords="offset points",
             xytext=(0, 14), color=BLUE, fontsize=9, ha="center",
             fontweight="bold")
for a, b in bridges:
    for n, dy in ((a, -18), (b, 18)):
        axb.annotate("bridge", pos[n], textcoords="offset points",
                     xytext=(0, dy), fontsize=7.6, ha="center", color=RED)
for c, (cx, cy) in enumerate(centers):
    axb.text(cx, 1.12, f"clique {c + 1}", ha="center", fontsize=8.6,
             color="#555")
axb.text(0, -1.42, "each clique: 20 nodes, all hear all; cliques joined only by the two dashed bridge links",
         ha="center", fontsize=8.2, color="#555")

sm = cm.ScalarMappable(norm=norm, cmap=cmap)
cb = fig.colorbar(sm, ax=axb, shrink=0.75, pad=0.02)
cb.set_label("learned relay pressure", fontsize=8.5)
axb.set_xlim(-3.7, 3.7)
axb.set_ylim(-1.6, 1.6)
axb.axis("off")
axb.set_title("(b)  the dense world after 330 packets: interiors fade toward\n"
              "silence, bridge endpoints self-promote \u2014 no role was ever assigned",
              fontsize=10, loc="left")

fig.suptitle("Relay pressure: two locally-measured numbers (crowding, novelty) replace the role system",
             fontsize=11.5, fontweight="bold", y=1.02)
fig.savefig("fig_pressure.png", dpi=150, bbox_inches="tight")
print("wrote fig_pressure.png")
