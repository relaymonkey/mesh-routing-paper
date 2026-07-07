"""Figure: setpoint controller vs statics on all six production networks."""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rows = list(csv.DictReader(open("setpoint_multinet.csv")))
for r in rows:
    r["cov"] = float(r["cover_reachable"])
    r["tx"] = float(r["tx_per_flood"])

NETS = ["norway", "meshtastic-pt", "socal", "bay-area", "florida", "italia"]
LABELS = ["Norway", "Meshtastic PT", "SoCal", "Bay Area", "Florida", "Italia"]
PROTOS = [
    ("plain flood", "#7f7f7f", "plain flood (today)"),
    ("persist R=3", "#9467bd", "blanket persist R=3"),
    ("SETPOINT", "#2ca02c", "SETPOINT (fill the cap)"),
]

fig, ax = plt.subplots(figsize=(12.4, 4.9))
width = 0.26
for pi, (proto, color, label) in enumerate(PROTOS):
    xs, ys, txs = [], [], []
    for ni, net in enumerate(NETS):
        r = next(r for r in rows if r["network"] == net and r["proto"] == proto)
        xs.append(ni + (pi - 1) * width)
        ys.append(r["cov"])
        txs.append(r["tx"])
    ax.bar(xs, ys, width * 0.9, color=color, edgecolor="white", lw=0.5,
           label=label)
    for x, y, t in zip(xs, ys, txs):
        ax.text(x, y + 0.6, f"{y:.0f}", ha="center", fontsize=7.8,
                fontweight="bold")
        ax.text(x, y / 2 if y > 6 else y + 2.8, f"{t:.0f}tx", ha="center",
                fontsize=6.8, color="white" if y > 6 else "#555",
                rotation=90 if y <= 6 else 0)

ax.set_xticks(range(len(NETS)))
ax.set_xticklabels(LABELS, fontsize=9)
ax.set_ylabel("coverage of reachable online nodes  %")
ax.set_ylim(0, 52)
ax.grid(alpha=0.25, axis="y")
ax.legend(fontsize=8.8, loc="upper right")
ax.set_title("Setpoint controller on all six production networks (20 broadcasts/h, utilization-tracked; bars: coverage, inset: tx per flood)\n"
             "Sparse meshes never approach the cap, so the controller self-climbs to its top rung and takes the best coverage on every network \u2014\n"
             "channel utilization stays under 0.2% everywhere: the cap constrains nothing here, and dense-regime retreat (Fig. 21) never triggers",
             fontsize=9.6, loc="left")

fig.tight_layout()
fig.savefig("fig_setpoint_multinet.png", dpi=150, bbox_inches="tight")
print("wrote fig_setpoint_multinet.png")
