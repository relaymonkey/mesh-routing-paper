"""Figure: relay pressure vs static policies on all six production networks."""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rows = list(csv.DictReader(open("pressure_multinet.csv")))
for r in rows:
    r["cov"] = float(r["cover_reachable"])
    r["tx"] = float(r["tx_per_flood"])

NETS = ["norway", "meshtastic-pt", "socal", "bay-area", "florida", "italia"]
LABELS = ["Norway", "Meshtastic PT", "SoCal", "Bay Area", "Florida", "Italia"]
PROTOS = [
    ("plain flood", "#7f7f7f"),
    ("cancel@1", "#1f77b4"),
    ("persist R=3", "#9467bd"),
    ("pressure", "#2ca02c"),
]

fig, ax = plt.subplots(figsize=(12.6, 5.0))
width = 0.2
for pi, (proto, color) in enumerate(PROTOS):
    xs, ys, txs = [], [], []
    for ni, net in enumerate(NETS):
        r = next(r for r in rows if r["network"] == net and r["proto"] == proto)
        xs.append(ni + (pi - 1.5) * width)
        ys.append(r["cov"])
        txs.append(r["tx"])
    label = {"plain flood": "plain flood", "cancel@1": "cancel@1 (shipped-style)",
             "persist R=3": "blanket persist R=3",
             "pressure": "PRESSURE (no config)"}[proto]
    ax.bar(xs, ys, width * 0.9, color=color, edgecolor="white", lw=0.5,
           label=label)
    for x, y, t in zip(xs, ys, txs):
        ax.text(x, y + 0.7, f"{y:.0f}", ha="center", fontsize=7.6,
                fontweight="bold")
        ax.text(x, y / 2 if y > 7 else y + 3.2, f"{t:.0f}tx", ha="center",
                fontsize=6.6, color="white" if y > 7 else "#555",
                rotation=90 if y <= 7 else 0)

ax.set_xticks(range(len(NETS)))
ax.set_xticklabels(LABELS, fontsize=9)
ax.set_ylabel("coverage of reachable online nodes  %")
ax.set_ylim(0, 62)
ax.grid(alpha=0.25, axis="y")
ax.legend(fontsize=8.6, loc="upper right")
ax.set_title("Relay pressure on all six production networks (per-network calibration; bars: coverage, inset: tx per flood)\n"
             "Every real network is a sparse persistence regime: pressure self-calibrates to match the best static policy on each,\n"
             "spending less airtime where redundancy exists (Florida \u221219%, Italia \u221232%) \u2014 the suppression regime of Fig. 17 is urban density",
             fontsize=9.8, loc="left")

fig.tight_layout()
fig.savefig("fig_pressure_multinet.png", dpi=150, bbox_inches="tight")
print("wrote fig_pressure_multinet.png")
