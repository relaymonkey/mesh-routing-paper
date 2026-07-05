"""Render report figures for the Norway-mesh routing simulation."""
import csv
import math
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import sim_norway as S

ROLE_COLORS = {
    "ROUTER": "#d62728", "ROUTER_LATE": "#ff7f0e", "CLIENT_BASE": "#1f77b4",
    "CLIENT": "#7f7f7f", "CLIENT_MUTE": "#bcbd22", "TRACKER": "#9467bd",
    "UNKNOWN": "#c7c7c7",
}
PROTO_COLORS = {"FLOOD": "#7f7f7f", "PATH": "#d62728", "NEXTHOP": "#1f77b4",
                "GRADCOR": "#98df8a", "GRADCOR-R": "#2ca02c"}

nodes = S.load_nodes()
trs = S.load_traceroutes()
links = S.links_from_traceroutes(trs)

summary = {r["proto"]: r for r in csv.DictReader(open("results_summary.csv"))}
hourly = defaultdict(dict)
for r in csv.DictReader(open("results_hourly.csv")):
    hourly[r["proto"]][int(r["hour"])] = (int(r["delivered"]), int(r["sent"]))

fig = plt.figure(figsize=(16, 12))
gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.22)

# --- (1) topology map ---
ax = fig.add_subplot(gs[0, 0])
# Norway bounding box; drops (0,0) placeholders and bad GPS fixes
pos = {n: (d["lon"], d["lat"]) for n, d in nodes.items()
       if d["hasPos"] and 57 <= d["lat"] <= 72 and 3 <= d["lon"] <= 32}
drawn = 0
for (u, v), (obs, _s, _t) in links.items():
    if u in pos and v in pos:
        x1, y1 = pos[u]; x2, y2 = pos[v]
        ax.plot([x1, x2], [y1, y2], lw=0.3, color="#999", alpha=0.25, zorder=1)
        drawn += 1
for role in ROLE_COLORS:
    xs = [pos[n][0] for n, d in nodes.items() if n in pos and d["role"] == role]
    ys = [pos[n][1] for n, d in nodes.items() if n in pos and d["role"] == role]
    if xs:
        big = role.startswith("ROUTER")
        ax.scatter(xs, ys, s=28 if big else 9, c=ROLE_COLORS[role],
                   label=f"{role} ({len(xs)})", zorder=3 if big else 2,
                   edgecolors="white" if big else "none", linewidths=0.5)
ax.set_title(f"Norway mesh — real 7d topology from production Memgraph\n"
             f"{len(nodes)} nodes, {len(links)} directed links "
             f"({len(pos)} nodes with GPS shown, {drawn} links)")
ax.set_xlabel("lon"); ax.set_ylabel("lat")
ax.legend(fontsize=7, loc="lower right")

# --- (2) calibration ---
ax = fig.add_subplot(gs[0, 1])
target = S.real_hop_hist(trs)
# re-simulate hop hist with final params for the figure
import random
presence, t0 = S.load_presence(trs, 168)
world = S.World(links, nodes, presence, 168, x0=8, pmax=0.8, pmin=0.25,
                kobs=10, rev_p=0.0, seed=7)
rng = random.Random(42)
cands = [t for t in trs if S.real(t["dst"]) and t["src"] != t["dst"]]
samples = [(t["src"], t["dst"], min(167, int((t["ts"] - t0) // 3600)))
           for t in rng.sample(cands, 400)]
simh, rt = S.sim_hop_hist(world, samples, rng)
ks = sorted(set(target) | set(simh))
w = 0.4
ax.bar([k - w / 2 for k in ks], [target.get(k, 0) for k in ks], width=w,
       label="real traceroutes (18,919 pkts)", color="#1f77b4")
ax.bar([k + w / 2 for k in ks], [simh.get(k, 0) for k in ks], width=w,
       label="simulated floods (calibrated)", color="#ff7f0e")
ax.set_title("Calibration check: hop-count distribution, real vs simulated\n"
             f"link PER from SNR+evidence; round-trip rate real 0.23 / sim {rt:.2f}")
ax.set_xlabel("hops travelled"); ax.set_ylabel("fraction of delivered packets")
ax.legend(fontsize=9)

# --- (3) headline result ---
ax = fig.add_subplot(gs[1, 0])
order = ["FLOOD", "PATH", "NEXTHOP", "GRADCOR", "GRADCOR-R"]
x = range(len(order))
dr = [float(summary[p]["delivery_pct"]) for p in order]
tpd = [float(summary[p]["tx_per_delivered"]) for p in order]
b = ax.bar(x, dr, color=[PROTO_COLORS[p] for p in order])
ax.bar_label(b, fmt="%.1f%%", fontsize=10)
ax.set_xticks(list(x)); ax.set_xticklabels(order)
ax.set_ylabel("delivery rate %"); ax.set_ylim(0, 100)
ax.set_title("Delivery rate — 30 real traceroute pairs, 168 real hours, 3 seeds")
ax2 = ax.twinx()
ax2.plot(x, tpd, "kD--", ms=8, label="tx per delivered pkt")
for xi, v in zip(x, tpd):
    ax2.annotate(f"{v:.0f} tx", (xi, v), textcoords="offset points",
                 xytext=(10, 6), fontsize=9)
ax2.set_ylabel("transmissions per delivered packet (airtime cost)")
ax2.set_yscale("log")
ax2.legend(loc="upper left", fontsize=9)

# --- (4) hourly delivery ---
ax = fig.add_subplot(gs[1, 1])
for p in order:
    hs = sorted(hourly[p])
    # 6h rolling window to de-noise
    xs, ys = [], []
    for i in range(0, 168, 6):
        dlv = sum(hourly[p].get(h, (0, 0))[0] for h in range(i, i + 6))
        snt = sum(hourly[p].get(h, (0, 0))[1] for h in range(i, i + 6))
        if snt:
            xs.append(i); ys.append(100 * dlv / snt)
    ax.plot(xs, ys, color=PROTO_COLORS[p], label=p, lw=1.8)
ax.set_title("Delivery rate over the real week (6 h buckets)\n"
             "traffic only when both endpoints were actually online")
ax.set_xlabel("hour of window (2026-06-27 → 07-04)")
ax.set_ylabel("delivery rate %")
ax.set_ylim(0, 100)
ax.legend(fontsize=9)
ax.grid(alpha=0.3)

fig.suptitle("Routing strategies replayed on the real Norway mesh "
             "(production data, last 7 days)", fontsize=15, y=0.98)
fig.savefig("results.png", dpi=110, bbox_inches="tight")
print("wrote results.png")
