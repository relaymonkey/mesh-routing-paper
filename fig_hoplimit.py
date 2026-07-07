"""Figure: broadcast flood coverage and cost at hop limit 3 / 7 / unlimited,
all six networks (numbers from experiment_hoplimit_multinet.py)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

NETS = ["Norway", "Meshtastic PT", "SoCal", "Bay Area", "Florida", "Italia"]
# (coverage of reachable %, tx/flood) per hop limit
DATA = {
    3:        [(20.8, 6.5), (6.3, 5.6), (4.3, 4.3), (2.2, 3.9), (1.1, 2.9), (30.3, 1.2)],
    7:        [(32.2, 16.3), (15.2, 22.4), (12.8, 21.0), (4.8, 12.9), (1.9, 6.1), (30.3, 1.2)],
    "unlim":  [(34.4, 18.1), (15.8, 25.3), (14.2, 26.3), (4.9, 14.3), (2.0, 6.8), (30.3, 1.2)],
}
COLORS = {3: "#d62728", 7: "#1f77b4", "unlim": "#2ca02c"}
LABELS = {3: "hop limit 3 (shipped default)", 7: "hop limit 7 (protocol ceiling)",
          "unlim": "unlimited (dedup-bounded)"}

fig, ax = plt.subplots(figsize=(12.4, 4.9))
width = 0.26
for i, hl in enumerate((3, 7, "unlim")):
    xs = [ni + (i - 1) * width for ni in range(len(NETS))]
    ys = [v[0] for v in DATA[hl]]
    txs = [v[1] for v in DATA[hl]]
    ax.bar(xs, ys, width * 0.92, color=COLORS[hl], edgecolor="white", lw=0.5,
           label=LABELS[hl])
    for x, y, t in zip(xs, ys, txs):
        ax.text(x, y + 0.5, f"{y:.0f}", ha="center", fontsize=7.8,
                fontweight="bold")
        ax.text(x, y / 2 if y > 5 else y + 2.6, f"{t:.0f}tx", ha="center",
                fontsize=6.8, color="white" if y > 5 else "#555",
                rotation=90 if y <= 5 else 0)

ax.set_xticks(range(len(NETS)))
ax.set_xticklabels(NETS, fontsize=9)
ax.set_ylabel("flood coverage of reachable online nodes  %")
ax.set_ylim(0, 40)
ax.grid(alpha=0.25, axis="y")
ax.legend(fontsize=8.8, loc="upper right")
ax.set_title("Broadcast flood at hop limit 3 / 7 / unlimited, six networks (bars: coverage; inset: tx per flood)\n"
             "The 3 \u2192 7 step is large wherever the graph has depth; the 7 \u2192 unlimited step is marginal everywhere \u2014 "
             "floods die of link loss, not of the counter",
             fontsize=10, loc="left")

fig.tight_layout()
fig.savefig("fig_hoplimit.png", dpi=150, bbox_inches="tight")
print("wrote fig_hoplimit.png")
