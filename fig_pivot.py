"""Figure 17: PIVOT self-organizing relay backbone."""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

# --- panel (a): three-node rule ---
fig = plt.figure(figsize=(14, 9.5))
gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.1], hspace=0.34, wspace=0.22)

import math

ax0 = fig.add_subplot(gs[0, 0])
ax0.set_xlim(0, 10)
ax0.set_ylim(0, 6)
ax0.set_aspect("equal")
ax0.axis("off")
ax0.set_title("(a)  three-node rule: direct beats pivot when cheaper", loc="left", fontsize=10)

def node(ax, x, y, label, r=0.42, color="#1f77b4", fc="white", tc="#111"):
    ax.add_patch(Circle((x, y), r, fc=fc, ec=color, lw=2, zorder=4))
    ax.text(x, y, label, ha="center", va="center", fontsize=12,
            fontweight="bold", color=tc, zorder=5)

yc = 3.4
node(ax0, 1.6, yc, "1")
node(ax0, 5.0, yc, "2", color="#2ca02c")
node(ax0, 8.4, yc, "3")
# strong two-hop path 1-2-3 (green, the elected corridor when direct is weak)
for x1, x2 in ((2.02, 4.58), (5.42, 7.98)):
    ax0.plot([x1, x2], [yc, yc], color="#2ca02c", lw=3, zorder=2, solid_capstyle="round")
ax0.text(3.3, yc + 0.32, "strong", ha="center", fontsize=8.5, color="#2ca02c")
ax0.text(6.7, yc + 0.32, "strong", ha="center", fontsize=8.5, color="#2ca02c")
# weak direct 1-3 (dashed red arc curving below the nodes)
ax0.add_patch(FancyArrowPatch((1.9, yc - 0.4), (8.1, yc - 0.4),
                              connectionstyle="arc3,rad=0.28", arrowstyle="-",
                              color="#d62728", lw=1.6, ls=(0, (5, 3)), zorder=1))
ax0.text(5.0, yc - 1.75, "weak direct  1\u21943", ha="center", fontsize=8.5, color="#d62728")
ax0.text(0.2, 5.5,
         "strong 1\u21943:  direct delivery, node 2 stays silent  \u2014  1 tx\n"
         "weak 1\u21943:    node 2 elected pivot on the strong path  \u2014  ~2 tx",
         fontsize=8.6, color="#333", va="top")

# --- panel (b): 101-node star ---
ax1 = fig.add_subplot(gs[0, 1])
ax1.set_xlim(0, 10)
ax1.set_ylim(0, 10)
ax1.set_aspect("equal")
ax1.axis("off")
ax1.set_title("(b)  101-node star: centre = 1 tx, leaf \u2248 2 tx", loc="left", fontsize=10)

cx, cy, r = 5.0, 5.2, 3.55
n_leaves = 28
src_ang = 234                                   # one highlighted source leaf
leaves = []
for k in range(n_leaves):
    ang = 360 * k / n_leaves
    x = cx + r * math.cos(math.radians(ang))
    y = cy + r * math.sin(math.radians(ang))
    leaves.append((ang, x, y))

# hub -> every leaf: one broadcast reaches all (the second tx)
for ang, x, y in leaves:
    ax1.plot([cx, x], [cy, y], color="#bbb", lw=0.6, alpha=0.7, zorder=1)
# highlighted source leaf's report to the hub (the first tx)
sx = cx + r * math.cos(math.radians(src_ang))
sy = cy + r * math.sin(math.radians(src_ang))
ax1.add_patch(FancyArrowPatch((sx, sy), (cx, cy), arrowstyle="-|>",
                              color="#e8890c", lw=2.2, mutation_scale=14,
                              shrinkA=10, shrinkB=20, zorder=3))
# leaves
for ang, x, y in leaves:
    is_src = abs(ang - src_ang) < 1
    ax1.add_patch(Circle((x, y), 0.30 if is_src else 0.24,
                         fc="#e8890c" if is_src else "#aec7e8",
                         ec="#b5650a" if is_src else "#1f77b4", lw=1.0, zorder=4))
# hub
ax1.add_patch(Circle((cx, cy), 0.62, fc="#2ca02c", ec="#1a5c1a", lw=2, zorder=5))
ax1.text(cx, cy, "hub", ha="center", va="center", fontsize=9.5,
         color="white", fontweight="bold", zorder=6)
ax1.annotate("source leaf\n(1 tx to hub)", (sx, sy), fontsize=7.8, color="#b5650a",
             ha="center", va="top", xytext=(0, -12), textcoords="offset points")
ax1.text(cx, 0.5, "managed flood: 96 tx      |      PIVOT: 1 tx (centre) / 2 tx (leaf)",
         ha="center", fontsize=8.8, fontweight="bold")

# --- panel (c): six-network scorecard ---
ax2 = fig.add_subplot(gs[1, 0])
rows = list(csv.DictReader(open("pivot_multinet.csv")))
networks = ["norway", "bay-area", "florida", "socal", "meshtastic-pt", "italia"]
labels = ["Norway", "Bay Area", "Florida", "SoCal", "Meshtastic PT", "Italia"]
protos = ["managed flood", "relay pressure", "PIVOT 64-bit"]
colors = {"managed flood": "#888", "relay pressure": "#ff7f0e", "PIVOT 64-bit": "#2ca02c"}
x = range(len(networks))
w = 0.25
for i, proto in enumerate(protos):
    vals = []
    for net in networks:
        r = next(row for row in rows if row["network"] == net and row["proto"] == proto)
        vals.append(float(r["cover_reachable"]))
    ax2.bar([xi + (i - 1) * w for xi in x], vals, w, label=proto, color=colors[proto])
ax2.set_xticks(list(x))
ax2.set_xticklabels(labels, rotation=25, ha="right", fontsize=8)
ax2.set_ylabel("coverage of reachable nodes  %")
ax2.legend(fontsize=7.5, loc="upper left")
ax2.grid(alpha=0.25, axis="y")
ax2.set_title("(c)  six production networks", loc="left", fontsize=10)

# --- panel (d): capacity tradeoff ---
ax3 = fig.add_subplot(gs[1, 1])
cap = list(csv.DictReader(open("integrated_stack_capacity.csv")))
scale1 = [r for r in cap if float(r["scale"]) == 1.0]
names = [r["policy"] for r in scale1]
p95 = [float(r["p95_util"]) for r in scale1]
tx = [float(r["tx_per_offered"]) for r in scale1]
cols = ["#888", "#2ca02c", "#006d2c", "#d98200"]
ax3b = ax3.twinx()
bars = ax3.bar(range(len(names)), p95, color=cols, alpha=0.85)
ax3b.plot(range(len(names)), tx, "ko-", lw=1.5, ms=6)
ax3.set_xticks(range(len(names)))
ax3.set_xticklabels(["managed", "integ. fast", "fast+PIVOT", "integ. full"],
                    fontsize=8, rotation=15)
ax3.axhline(25, color="#d62728", ls="--", lw=1.2)
ax3.set_ylabel("p95 utilization  %")
ax3b.set_ylabel("tx per offered packet")
ax3.set_title("(d)  capacity @ 499 nodes (scale 1.0)", loc="left", fontsize=10)
ax3.text(2, p95[2] + 1.2, f"hotspot\n~634 nodes", ha="center", fontsize=8, color="#006d2c")
ax3.grid(alpha=0.25, axis="y")

fig.suptitle("PIVOT: self-organizing relay backbone \u2014 minimal pivots, load-balanced hubs",
             fontsize=12, fontweight="bold", y=0.98)
fig.text(0.01, 0.01,
         "PIVOT elects a load-balanced pivot set from local two-hop coverage; 64-bit digest mode "
         "throughout. Star/triangle are deterministic edge cases; panels (c\u2013d) from "
         "pivot_multinet.csv and integrated_stack_capacity.csv (3 seeds).",
         fontsize=7.5, color="#555")
fig.savefig("fig_pivot.png", dpi=150, bbox_inches="tight")
print("wrote fig_pivot.png")
