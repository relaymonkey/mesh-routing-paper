"""Figure: the coverage / capacity / load tension.

(a) Coverage and capacity are the SAME axis: every broadcast policy is a
    point on one airtime->coverage price curve (Norway). PIVOT buys a cheaper
    point (less airtime, hence more node capacity) at less coverage; relay
    pressure buys the opposite. No scheme escapes the curve.
(b) The integrated stack makes the trade explicit: fast+PIVOT raises node
    capacity but lowers broadcast reach; full mode raises reliability but
    cuts capacity. Three knobs, one frontier.
(c) Aggregation is a DIFFERENT axis -- it cuts offered load, not per-packet
    cost -- but its gain is bounded by payload/preamble ratio and by density:
    big in dense/star with small reports, ~nothing on sparse Norway.
"""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(path):
    return list(csv.DictReader(open(path)))


def crossing(xs, ys, target=25.0):
    for x1, x2, y1, y2 in zip(xs, xs[1:], ys, ys[1:]):
        if y1 <= target < y2:
            return x1 + (target - y1) * (x2 - x1) / (y2 - y1)
    return None


fig, (axa, axb, axc) = plt.subplots(1, 3, figsize=(15.5, 4.9))

# ---- (a) one price curve ----
piv = [r for r in load("pivot_multinet.csv") if r["network"] == "norway"]
pts = {
    "role backbone": ("#9467bd", "o", (-6, 10), "left"),
    "meshcore repeaters": ("#8c564b", "s", (0, 11), "center"),
    "managed flood": ("#777777", "D", (34, 2), "left"),
    "PIVOT 64-bit": ("#2ca02c", "*", (0, -20), "center"),
    "relay pressure": ("#ff7f0e", "^", (0, -22), "center"),
}
for r in piv:
    if r["proto"] not in pts:
        continue
    c, m, off, ha = pts[r["proto"]]
    x, y = float(r["tx_per_flood"]), float(r["cover_reachable"])
    axa.scatter(x, y, c=c, marker=m, s=150, zorder=3, edgecolor="k", lw=0.5)
    axa.annotate(r["proto"].replace(" ", "\n"), (x, y), fontsize=7.4,
                 ha=ha, va="center", xytext=off, textcoords="offset points")
axa.set_xscale("log")
axa.set_ylim(5, 62)
axa.set_xlabel("transmissions per flood  (log)  \u2192 less capacity")
axa.set_ylabel("coverage of reachable nodes  %")
axa.set_title("(a)  coverage and capacity are one axis", loc="left", fontsize=10)
axa.grid(alpha=0.25, which="both")
axa.text(0.03, 0.03, "one price curve (\u00a76.4):\nPIVOT = cheaper point,\nnot a better curve",
         transform=axa.transAxes, fontsize=7.8, va="bottom", color="#333")

# ---- (b) integrated stack trade ----
cap = load("integrated_stack_capacity.csv")
policies = [("managed current", "#888888"), ("integrated fast", "#2ca02c"),
            ("integrated fast+pivot", "#006d2c"), ("integrated full", "#d98200")]
for name, color in policies:
    prows = [r for r in cap if r["policy"] == name]
    nodes = [int(r["equiv_nodes"]) for r in prows]
    p99 = [float(r["p99_util"]) for r in prows]
    hot = crossing(nodes, p99)
    rxb = float(next(r for r in prows if float(r["scale"]) == 1.0)["receivers_per_broadcast"])
    off = (0, -16) if rxb > 6.0 else (0, 10)
    if hot:
        axb.scatter(hot, rxb, c=color, s=170, zorder=3, edgecolor="k", lw=0.5)
        axb.annotate(name.replace("integrated ", "").replace(" ", "\n"),
                     (hot, rxb), fontsize=7.4, ha="center",
                     xytext=off, textcoords="offset points")
axb.set_xlabel("node capacity  (hotspot @ p99=25%)  \u2192")
axb.set_ylabel("broadcast reach  (receivers / packet)")
axb.set_title("(b)  the stack's explicit trade", loc="left", fontsize=10)
axb.set_ylim(5.0, 6.7)
axb.set_xlim(280, 700)
axb.grid(alpha=0.25)
axb.annotate("", xy=(0.92, 0.10), xytext=(0.5, 0.62), xycoords="axes fraction",
             arrowprops=dict(arrowstyle="->", color="#c00", lw=1.4))
axb.text(0.30, 0.40, "more capacity\ncosts reach", transform=axb.transAxes,
         fontsize=7.8, color="#c00", va="top")

# ---- (c) aggregation: a different axis ----
agg = load("aggregate_results.csv")
worlds = {
    "STAR (1 hub + 100 leaves, 4B delta reports)": ("#1f77b4", "star, 4B delta"),
    "STAR (1 hub + 100 leaves, 20B reports)": ("#2ca02c", "star, 20B"),
    "DENSE (3x20 cliques + bridges)": ("#9467bd", "dense"),
    "NORWAY replay (sparse organic)": ("#777777", "Norway (sparse)"),
}
for world, (color, label) in worlds.items():
    wr = [r for r in agg if r["world"] == world]
    if not wr:
        continue
    G = [int(r["G"]) for r in wr]
    hd = [float(r["hotspot_drop"]) for r in wr]
    axc.plot(G, hd, "o-", color=color, lw=2, label=label)
axc.axhline(1.0, color="#aaa", ls=":", lw=1)
axc.set_xlabel("aggregation batch  G  (reports per packet)")
axc.set_ylabel("hotspot airtime reduction  \u00d7")
axc.set_title("(c)  aggregation attacks a different axis", loc="left", fontsize=10)
axc.legend(fontsize=7.6, loc="upper left")
axc.grid(alpha=0.25)
axc.text(0.97, 0.05, "bounded by payload/preamble ratio\nand density; +window latency",
         transform=axc.transAxes, fontsize=7.4, ha="right", va="bottom", color="#333")

fig.suptitle("Why node count grows by constant factors, not orders of magnitude: "
             "coverage \u2194 capacity is one curve; load is the other lever",
             fontsize=12, fontweight="bold", y=1.00)
fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig("fig_tension.png", dpi=150, bbox_inches="tight")
print("wrote fig_tension.png")
