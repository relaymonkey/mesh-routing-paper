"""Figure: what relay pressure does to the flood operating point, per world.

Arrow from the plain-flood point to the pressure point in
(airtime, coverage) space: on sparse networks it climbs the price curve
(pay more, reach more), in density it moves up-LEFT (more coverage, less
airtime). Lean (mute-only) pressure sits on the flood point on sparse
networks -- suppression has nothing to harvest there.
"""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

GREEN = "#2ca02c"
GRAY = "#555555"
RED = "#d62728"

rows = list(csv.DictReader(open("pressure_multinet.csv")))
def get(net, proto):
    r = next(r for r in rows if r["network"] == net and r["proto"] == proto)
    return float(r["tx_per_flood"]), float(r["cover_reachable"])

NETS = [("norway", "Norway"), ("meshtastic-pt", "PT"), ("socal", "SoCal"),
        ("bay-area", "Bay Area"), ("florida", "Florida"), ("italia", "Italia")]

# lean (mute-only) pressure, from the iso-coverage run
LEAN = {"norway": (18.3, 32.8), "meshtastic-pt": (20.8, 14.1),
        "socal": (23.1, 13.3), "bay-area": (12.0, 4.2),
        "florida": (6.7, 1.9), "italia": (1.2, 33.2)}

DENSE_FLOOD = (47.1, 78.5)
DENSE_PRESS = (18.4, 83.7)

fig, ax = plt.subplots(figsize=(11.6, 6.0))

for net, label in NETS:
    fx, fy = get(net, "plain flood")
    px, py = get(net, "pressure")
    ax.plot([fx], [fy], "o", ms=8, color=GRAY, zorder=4)
    ax.plot([px], [py], "o", ms=8, color=GREEN, zorder=4)
    lx, ly = LEAN[net]
    ax.plot([lx], [ly], "o", ms=11, mfc="none", mec=GREEN, mew=1.6, zorder=5)
    rad = {"bay-area": -0.12, "florida": -0.12}.get(net, 0.12)
    arr = FancyArrowPatch((fx, fy), (px, py), arrowstyle="-|>",
                          mutation_scale=13, color=GREEN, lw=1.6,
                          alpha=0.75, zorder=3,
                          connectionstyle=f"arc3,rad={rad}")
    ax.add_patch(arr)
    dx = {"norway": (4, 6), "meshtastic-pt": (4, -12), "socal": (4, 6),
          "bay-area": (4, -13), "florida": (4, 6), "italia": (5, -13)}[net]
    ax.annotate(label, (fx, fy), textcoords="offset points", xytext=dx,
                fontsize=8.6, color="#333")

# dense world
ax.plot([DENSE_FLOOD[0]], [DENSE_FLOOD[1]], "s", ms=9, color=GRAY, zorder=4)
ax.plot([DENSE_PRESS[0]], [DENSE_PRESS[1]], "*", ms=17, color=GREEN, zorder=5)
arr = FancyArrowPatch(DENSE_FLOOD, DENSE_PRESS, arrowstyle="-|>",
                      mutation_scale=15, color=RED, lw=2.4, zorder=4,
                      connectionstyle="arc3,rad=-0.15")
ax.add_patch(arr)
ax.annotate("DENSE world (synthetic: cliques + bridges)", DENSE_FLOOD,
            textcoords="offset points", xytext=(8, -2), fontsize=9,
            color="#333", fontweight="bold")
ax.text(20, 90.5, "in density the arrow turns: +5 pts coverage at 60% less airtime\n"
        "(suppression harvests redundancy; only density has redundancy to harvest)",
        fontsize=8.8, color=RED)

ax.text(72, 44, "on sparse networks the arrow climbs the price curve:\n"
        "coverage is bought with airtime (persistence), never free",
        fontsize=8.8, color=GREEN, ha="center")
ax.text(8.3, 51, "open circles: mute-only pressure lands exactly on the flood\n"
        "point \u2014 sparse floods are already near-efficient, there is\n"
        "no redundancy for suppression to harvest",
        fontsize=8.3, color="#3a7a3a", ha="center")

ax.set_xscale("log", base=2)
ax.set_xticks([2, 4, 8, 16, 32, 64])
ax.set_xticklabels(["2", "4", "8", "16", "32", "64"])
ax.set_xlabel("transmissions per flood (log scale)")
ax.set_ylabel("coverage of reachable online nodes  %")
ax.set_ylim(0, 100)
ax.set_xlim(1.0, 110)
ax.grid(alpha=0.3)

ax.plot([], [], "o", color=GRAY, label="plain flood (today)")
ax.plot([], [], "o", color=GREEN, label="pressure (self-calibrating)")
ax.plot([], [], "o", mfc="none", mec=GREEN, mew=1.6, ms=10,
        label="pressure, persistence off (mute-only)")
ax.legend(fontsize=8.8, loc="lower right")
ax.set_title("What the pressure rule does to the flood's operating point, per world \u2014 "
             "the arrow's direction reveals the regime", fontsize=11, loc="left")

fig.tight_layout()
fig.savefig("fig_pressure_tradeoff.png", dpi=150, bbox_inches="tight")
print("wrote fig_pressure_tradeoff.png")
