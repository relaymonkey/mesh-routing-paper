"""Figure 17: PIVOT self-organizing relay backbone."""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

# --- panel (a): three-node rule ---
fig = plt.figure(figsize=(14, 9.5))
gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.1], hspace=0.34, wspace=0.22)

ax0 = fig.add_subplot(gs[0, 0])
ax0.set_xlim(0, 10)
ax0.set_ylim(0, 6)
ax0.axis("off")
ax0.set_title("(a)  three-node rule: direct beats pivot when cheaper", loc="left", fontsize=10)

def node(ax, x, y, label, color="#1f77b4"):
    ax.add_patch(Circle((x, y), 0.45, fc="white", ec=color, lw=2))
    ax.text(x, y, label, ha="center", va="center", fontsize=11, fontweight="bold")

node(ax0, 1.5, 3, "1")
node(ax0, 5, 3, "2")
node(ax0, 8.5, 3, "3")
for x1, x2, lbl, col in ((1.95, 4.55, "strong", "#2ca02c"), (5.45, 8.05, "strong", "#2ca02c")):
    ax0.add_patch(FancyArrowPatch((x1, 3), (x2, 3), arrowstyle="-|>", color=col, lw=2))
    ax0.text((x1+x2)/2, 3.45, lbl, ha="center", fontsize=8, color=col)
ax0.add_patch(FancyArrowPatch((2.0, 2.55), (7.9, 2.55), arrowstyle="-|>",
                              color="#d62728", lw=1.5, ls="--"))
ax0.text(5, 2.15, "weak direct 1\u21923", ha="center", fontsize=8, color="#d62728")
ax0.text(0.3, 5.2, "strong 1\u21943: node 2 silent, 1 tx\n"
         "weak 1\u21943: node 2 elected pivot, ~2 tx", fontsize=8.5, color="#333")

# --- panel (b): 101-node star ---
ax1 = fig.add_subplot(gs[0, 1])
ax1.set_xlim(0, 10)
ax1.set_ylim(0, 10)
ax1.axis("off")
ax1.set_title("(b)  101-node star: centre=1 tx, leaf\u22482 tx", loc="left", fontsize=10)
ax1.add_patch(Circle((5, 5), 0.55, fc="#2ca02c", ec="#1a5c1a", lw=2))
ax1.text(5, 5, "hub", ha="center", va="center", fontsize=9, color="white", fontweight="bold")
for ang in range(0, 360, 18):
    import math
    r = 3.8
    x = 5 + r * math.cos(math.radians(ang))
    y = 5 + r * math.sin(math.radians(ang))
    ax1.add_patch(Circle((x, y), 0.22, fc="#aec7e8", ec="#1f77b4", lw=0.8))
    ax1.plot([5, x], [5, y], color="#aaa", lw=0.5, alpha=0.5)
ax1.text(5, 0.6, "managed flood: 96 tx   |   PIVOT: 1 tx (centre) / 2 tx (leaf)",
         ha="center", fontsize=8.5)

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
