"""Figure: GradCor vs flood at depth (synthetic braid stress test)."""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rows = list(csv.DictReader(open("depth_results.csv")))
for r in rows:
    for k in ("depth", "width"):
        r[k] = int(r[k])
    for k in ("p", "warm_dlv", "warm_tx", "flood_dlv", "flood_tx"):
        r[k] = float(r[k])

fig = plt.figure(figsize=(12.8, 4.9))
gs = fig.add_gridspec(1, 2, width_ratios=[1.25, 1.0], wspace=0.22)

# ---- (a) delivery vs depth, w=2 braid ----
ax = fig.add_subplot(gs[0])
COLORS = {0.5: "#d62728", 0.7: "#e8a13c", 0.9: "#2ca02c"}
for p in (0.5, 0.7, 0.9):
    sub = sorted([r for r in rows if r["width"] == 2 and r["p"] == p],
                 key=lambda r: r["depth"])
    ds = [r["depth"] for r in sub]
    ax.plot(ds, [r["warm_dlv"] for r in sub], "o-", color=COLORS[p], lw=2.2,
            ms=6, label=f"GradCor corridor, link p={p}")
    ax.plot(ds, [r["flood_dlv"] for r in sub], "s--", color=COLORS[p], lw=1.3,
            ms=5, alpha=0.55, label=f"flood transport, link p={p}")
ax.set_xscale("log")
ax.set_xticks([7, 20, 50, 100, 200])
ax.set_xticklabels(["7\n(wire ceiling\ntoday)", "20", "50", "100", "200"])
ax.set_xlabel("true path length (hops)")
ax.set_ylabel("delivery %")
ax.set_ylim(-3, 106)
ax.grid(alpha=0.3)
ax.legend(fontsize=8.2, loc="center left")
ax.set_title("(a)  two-lane braid: per-hop persistence survives depth,\n"
             "front-survival flooding decays geometrically", fontsize=10, loc="left")
ax.text(7, 8, "corridor cost stays linear:\n~1.4 tx per hop at p=0.7",
        fontsize=8.4, color="#333")

# ---- (b) cold-start ramp ----
axb = fig.add_subplot(gs[1])
ramps = {
    ("d=20, fallback flood unlimited", "#2ca02c", "-"):
        [46.7, 73.3, 85.3, 94.7, 94.7, 94.7, 98.0, 99.3, 98.0, 98.7],
    ("d=50, fallback flood unlimited", "#1f77b4", "-"):
        [20.0, 34.0, 48.7, 58.7, 64.7, 64.7, 70.0, 77.3, 76.0, 80.7],
    ("d=20 or 50, fallback at today's hop-7 wire", "#d62728", "-"):
        [0.0] * 10,
}
for (label, color, ls), ys in ramps.items():
    axb.plot(range(1, 11), ys, "o" + ls, color=color, lw=2, ms=5, label=label)
axb.set_xticks(range(1, 11))
axb.set_xlabel("packet number (fresh mesh, no prior state)")
axb.set_ylabel("delivery %")
axb.set_ylim(-3, 106)
axb.grid(alpha=0.3)
axb.legend(fontsize=8.2, loc="center right")
axb.set_title("(b)  cold start at depth: the refresh climbs to steady state\n"
              "in a few packets \u2014 if the discovery flood can reach at all",
              fontsize=10, loc="left")

fig.suptitle("Depth stress test (synthetic braid, all nodes on): the no-hop-limit walk is not the bottleneck at 200 hops \u2014 "
             "the 3-bit wire hop field is", fontsize=11, fontweight="bold", y=1.03)
fig.savefig("fig_depth.png", dpi=150, bbox_inches="tight")
print("wrote fig_depth.png")
