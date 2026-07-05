"""Cross-network validation figure from multinet_results.csv."""
import csv
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROTO_COLORS = {"FLOOD": "#7f7f7f", "PATH": "#d62728", "NEXTHOP": "#1f77b4",
                "GRADCOR": "#98df8a", "GRADCOR-R": "#2ca02c"}
ORDER = ["FLOOD", "PATH", "NEXTHOP", "GRADCOR", "GRADCOR-R"]
NETS = ["norway", "meshtastic-pt", "socal", "bay-area", "florida", "italia"]
NET_LABELS = ["Norway\n499 n / 1,423 lk", "Meshtastic PT\n1,208 n / 4,147 lk",
              "SoCal\n1,351 n / 3,461 lk", "Bay Area\n3,637 n / 6,895 lk",
              "Florida\n1,394 n / 3,994 lk", "Italia*\n2,207 n / 146 lk"]

res = defaultdict(dict)
for r in csv.DictReader(open("multinet_results.csv")):
    res[r["network"]][r["proto"]] = (float(r["delivery_pct"]), float(r["tx_per_delivered"]))

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15.2, 7.6), sharex=True,
                               gridspec_kw={"hspace": 0.10})
n_p = len(ORDER)
w = 0.15
xs = range(len(NETS))

for j, p in enumerate(ORDER):
    off = (j - (n_p - 1) / 2) * w
    dl = [res[n][p][0] for n in NETS]
    bars = ax1.bar([x + off for x in xs], dl, width=w, color=PROTO_COLORS[p], label=p)
    ax1.bar_label(bars, fmt="%.0f", fontsize=8, padding=1)
    td = [res[n][p][1] for n in NETS]
    ax2.bar([x + off for x in xs], td, width=w, color=PROTO_COLORS[p])

# ratio annotations: GradCor-R vs FLOOD
for x, n in zip(xs, NETS):
    r = res[n]["GRADCOR-R"][0] / max(0.01, res[n]["FLOOD"][0])
    a = res[n]["FLOOD"][1] / max(0.01, res[n]["GRADCOR-R"][1])
    ax1.text(x, max(res[n][p][0] for p in ORDER) + 6,
             f"R vs flood:\n{r:.1f}\u00d7 dlv \u00b7 {a:.1f}\u00d7 cheaper",
             ha="center", fontsize=8.5, color="#1a6b1a" if r > 1 else "#b03030",
             fontweight="bold", linespacing=1.25)

ax1.set_ylabel("delivery rate %")
ax1.set_ylim(0, 66)
ax1.legend(fontsize=8.5, ncol=5, loc="upper right")
ax1.grid(axis="y", alpha=0.3)
ax1.set_title("Cross-network validation: five protocols on six production networks, "
              "each with its own per-network calibration (5 seeds, 168 real hours)",
              fontsize=11.5, fontweight="bold", loc="left")

ax2.set_yscale("log")
ax2.set_ylabel("tx per delivered packet (log)")
ax2.grid(axis="y", alpha=0.3)
ax2.set_xticks(list(xs))
ax2.set_xticklabels(NET_LABELS, fontsize=9.5)
ax2.text(0.005, 0.96,
         "*Italia fails the evidence-eligibility bar: 2,492 traceroutes yield only 146 usable links\n"
         "for 2,207 nodes, so gradients have almost nothing to descend on",
         transform=ax2.transAxes, ha="left", va="top", fontsize=8, style="italic", color="#444")

fig.savefig("fig_multinet.png", dpi=150, bbox_inches="tight")
print("wrote fig_multinet.png")
