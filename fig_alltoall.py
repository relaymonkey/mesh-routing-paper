"""Pareto view of the all-to-all delivery strategy space (+ six-network slopes)."""
import csv
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FAM = {
    "blanket":    ("#7f7f7f", "o", "blanket: every relay k times"),
    "meshcore":   ("#d62728", "s", "backbone-only relays (MeshCore), k times"),
    "meshcore+":  ("#e8a13c", "s", "backbone + base stations, k times"),
    "src-repeat": ("#1f77b4", "^", "source re-floods (no fw change)"),
    "targeted":   ("#9467bd", "D", "targeted (router x2 / sparse-gated)"),
    "combo":      ("#2ca02c", "*", "combos"),
}

rows = list(csv.DictReader(open("alltoall_results.csv")))
for r in rows:
    r["x"] = float(r["tx_per_flood"])
    r["y"] = float(r["cover_reachable"])

fig = plt.figure(figsize=(13.8, 6.2))
gs = fig.add_gridspec(1, 2, width_ratios=[1.55, 1.0], wspace=0.18)
ax = fig.add_subplot(gs[0])

# Pareto frontier (min tx for max coverage)
pts = sorted(rows, key=lambda r: r["x"])
front = []
best = -1
for r in pts:
    if r["y"] > best:
        front.append(r)
        best = r["y"]
ax.plot([r["x"] for r in front], [r["y"] for r in front],
        "k--", lw=1.4, alpha=0.55, zorder=1, label="Pareto frontier")

for fam, (color, marker, label) in FAM.items():
    fr = sorted([r for r in rows if r["family"] == fam], key=lambda r: r["x"])
    if not fr:
        continue
    ms = 16 if marker == "*" else 9
    ax.plot([r["x"] for r in fr], [r["y"] for r in fr], marker, color=color,
            ms=ms, ls="-" if len(fr) > 1 and fam not in ("targeted", "combo") else "none",
            lw=1.3, alpha=0.9, label=label, zorder=3)

OFFSETS = {
    "all k=1": (8, -13), "all k=2": (10, -3), "all k=3": (8, -4), "all k=4": (-14, 8),
    "backbone k=1": (7, -4), "backbone k=2": (7, 3), "backbone k=3": (-88, 5),
    "backbone+base k=1": (-58, -17), "backbone+base k=2": (-104, -4),
    "backbone+base k=3": (8, -13),
    "src x2": (-42, 7), "src x3": (-44, 5),
    "router x2": (6, -15), "gated (1-copy -> x2)": (9, -5),
    "router x2 + src x2": (-46, 15), "gated + src x2": (8, -4),
}
for r in rows:
    dx, dy = OFFSETS.get(r["strategy"], (7, -4))
    ax.annotate(r["strategy"], (r["x"], r["y"]), textcoords="offset points",
                xytext=(dx, dy), fontsize=8.2, color="#333")

ax.axhline(100, color="#d62728", lw=1.2, ls=":")
ax.text(178, 101.5, "100% of reachable nodes", fontsize=8.5, color="#a04040", ha="right")
ax.text(178, 97.2, "connectivity itself caps reach at ~35% of online",
        fontsize=8.5, color="#a04040", ha="right", va="top")

ax.set_xscale("log", base=2)
ax.set_xticks([4, 8, 16, 32, 64, 128])
ax.set_xticklabels(["4", "8", "16\n(~1 baseline flood)", "32", "64", "128"])
ax.set_xlabel("transmissions per message (log scale)")
ax.set_ylabel("coverage of reachable online nodes  %")
ax.set_ylim(0, 108)
ax.set_xlim(2.2, 190)
ax.grid(alpha=0.3)
ax.legend(fontsize=8.4, loc="upper left")
ax.set_title("(a)  Norway: every strategy family trades along one frontier \u2014\n"
             "placement (backbone) picks the point, persistence (k) climbs it",
             fontsize=10, loc="left")

# ---- (b) same shape on all six networks, network-specific slope ----
axb = fig.add_subplot(gs[1])
mrows = list(csv.DictReader(open("alltoall_multinet.csv")))
for r in mrows:
    r["x"] = float(r["tx_per_flood"])
    r["y"] = float(r["cover_reachable"])

NET = {
    "norway":        ("#2ca02c", "Norway"),
    "meshtastic-pt": ("#1f77b4", "Meshtastic PT"),
    "socal":         ("#9467bd", "SoCal"),
    "italia":        ("#7f7f7f", "Italia"),
    "bay-area":      ("#e8a13c", "Bay Area"),
    "florida":       ("#d62728", "Florida"),
}


def fit(rows_):
    pts = [(math.log2(r["x"]), r["y"]) for r in rows_]
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx
    return my - b * mx, b


for net, (color, label) in NET.items():
    nr = [r for r in mrows if r["network"] == net]
    a_, b_ = fit(nr)
    xs = [r["x"] for r in nr]
    lx = [min(xs), max(xs)]
    axb.plot([2 ** 0, 0], [0, 0], alpha=0)          # keep autoscale sane
    axb.plot(lx, [a_ + b_ * math.log2(x) for x in lx], "-", color=color,
             lw=2.0, alpha=0.85)
    axb.plot(xs, [r["y"] for r in nr], "o", color=color, ms=4.5, alpha=0.8)
    dy = {"socal": 9, "meshtastic-pt": -13, "bay-area": -2}.get(net, -3)
    axb.annotate(f"{label}: {b_:.1f} pts/doubling", (lx[1], a_ + b_ * math.log2(lx[1])),
                 textcoords="offset points", xytext=(6, dy), fontsize=8.2, color=color)

axb.set_xscale("log", base=2)
axb.set_xticks([2, 8, 32, 128])
axb.set_xticklabels(["2", "8", "32", "128"])
axb.set_xlim(0.9, 1400)
axb.set_ylim(0, 78)
axb.set_xlabel("transmissions per message (log scale)")
axb.set_ylabel("coverage of reachable online nodes  %")
axb.grid(alpha=0.3)
axb.set_title("(b)  all six networks: same log-linear shape\n"
              "(R\u00b2 0.87\u20130.98), network-specific price",
              fontsize=10, loc="left")

fig.suptitle("Objective: deliver one message to every reachable node \u2014 "
             "one price curve per network; no strategy escapes it, evidence density sets its slope",
             fontsize=11.5, fontweight="bold", y=1.01)
fig.savefig("fig_alltoall.png", dpi=150, bbox_inches="tight")
print("wrote fig_alltoall.png")
