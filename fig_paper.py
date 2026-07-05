"""Render the four report panels as separate figures for the PDF paper."""
import csv
import random
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
ORDER = ["FLOOD", "PATH", "NEXTHOP", "GRADCOR", "GRADCOR-R"]

nodes = S.load_nodes()
trs = S.load_traceroutes()
links = S.links_from_traceroutes(trs)
summary = {r["proto"]: r for r in csv.DictReader(open("results_summary.csv"))}
hourly = defaultdict(dict)
for r in csv.DictReader(open("results_hourly.csv")):
    hourly[r["proto"]][int(r["hour"])] = (int(r["delivered"]), int(r["sent"]))

# fig1: topology
fig, ax = plt.subplots(figsize=(7.2, 5.2))
pos = {n: (d["lon"], d["lat"]) for n, d in nodes.items()
       if d["hasPos"] and 57 <= d["lat"] <= 72 and 3 <= d["lon"] <= 32}
drawn = 0
for (u, v), (obs, _s, _t) in links.items():
    if u in pos and v in pos:
        ax.plot([pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]],
                lw=0.3, color="#999", alpha=0.25, zorder=1)
        drawn += 1
for role in ROLE_COLORS:
    xs = [pos[n][0] for n, d in nodes.items() if n in pos and d["role"] == role]
    ys = [pos[n][1] for n, d in nodes.items() if n in pos and d["role"] == role]
    if xs:
        big = role.startswith("ROUTER")
        ax.scatter(xs, ys, s=30 if big else 10, c=ROLE_COLORS[role],
                   label=f"{role} ({len(xs)})", zorder=3 if big else 2,
                   edgecolors="white" if big else "none", linewidths=0.5)
ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
ax.legend(fontsize=8, loc="upper right")
fig.tight_layout()
fig.savefig("fig1_topology.png", dpi=150)

# fig2: calibration
fig, ax = plt.subplots(figsize=(7.2, 4.2))
target = S.real_hop_hist(trs)
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
       label="real traceroutes (5,917 arrival-confirmed)", color="#1f77b4")
ax.bar([k + w / 2 for k in ks], [simh.get(k, 0) for k in ks], width=w,
       label="simulated floods (calibrated model)", color="#ff7f0e")
ax.set_xlabel("hops travelled"); ax.set_ylabel("fraction of delivered packets")
ax.legend(fontsize=9)
fig.tight_layout()
fig.savefig("fig2_calibration.png", dpi=150)
print(f"round-trip sim rate: {rt:.2f}")

# fig3: headline
fig, ax = plt.subplots(figsize=(8.0, 4.4))
x = range(len(ORDER))
dr = [float(summary[p]["delivery_pct"]) for p in ORDER]
tpd = [float(summary[p]["tx_per_delivered"]) for p in ORDER]
b = ax.bar(x, dr, color=[PROTO_COLORS[p] for p in ORDER])
ax.bar_label(b, fmt="%.1f%%", fontsize=10)
ax.set_xticks(list(x))
ax.set_xticklabels(["FLOOD", "PATH", "NEXTHOP", "GRADCOR\n(v1, aged)", "GRADCOR-R\n(final, no clock)"], fontsize=9)
ax.set_ylabel("delivery rate %"); ax.set_ylim(0, 100)
ax2 = ax.twinx()
ax2.plot(x, tpd, "kD--", ms=8, label="tx per delivered pkt")
for xi, v in zip(x, tpd):
    ax2.annotate(f"{v:.0f} tx", (xi, v), textcoords="offset points",
                 xytext=(10, 6), fontsize=9)
ax2.set_ylabel("transmissions per delivered packet (log)")
ax2.set_yscale("log")
ax2.legend(loc="upper left", fontsize=9)
fig.tight_layout()
fig.savefig("fig3_headline.png", dpi=150)

# fig4: hourly
fig, ax = plt.subplots(figsize=(7.2, 4.0))
for p in ORDER:
    xs, ys = [], []
    for i in range(0, 168, 6):
        dlv = sum(hourly[p].get(h, (0, 0))[0] for h in range(i, i + 6))
        snt = sum(hourly[p].get(h, (0, 0))[1] for h in range(i, i + 6))
        if snt:
            xs.append(i); ys.append(100 * dlv / snt)
    ax.plot(xs, ys, color=PROTO_COLORS[p], label=p, lw=1.8)
ax.set_xlabel("hour of window (2026-06-27 \u2192 07-04)")
ax.set_ylabel("delivery rate %")
ax.set_ylim(0, 100)
ax.legend(fontsize=9)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("fig4_hourly.png", dpi=150)
print("wrote fig1..fig4")
