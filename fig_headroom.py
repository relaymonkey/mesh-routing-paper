"""Figure: headroom controller under rising offered load (dense world)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

LOADS = [10, 40, 90, 160]
POLICIES = {
    "static plain flood":  ("#7f7f7f", "o",
                            [(80.1, 1.9), (78.0, 8.0), (74.0, 17.7), (68.4, 28.9)]),
    "static persist R=3":  ("#9467bd", "D",
                            [(85.0, 2.1), (83.6, 8.8), (78.7, 18.8), (73.7, 31.0)]),
    "HEADROOM (frontier ladder)": ("#7bbf7b", "*",
                            [(85.0, 2.1), (83.6, 8.8), (74.1, 17.6), (55.9, 23.1)]),
    "HEADROOM strict":     ("#1a5c1a", "^",
                            [(85.0, 2.1), (83.6, 8.8), (65.2, 14.9), (52.3, 21.1)]),
    "SETPOINT (fill the cap)": ("#2ca02c", "*",
                            [(86.1, 2.3), (83.5, 8.8), (79.0, 18.2), (58.2, 23.3)]),
}

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10.8, 7.2), sharex=True,
                               gridspec_kw={"hspace": 0.30})

for label, (color, marker, vals) in POLICIES.items():
    lw = 2.8 if label.startswith("SETPOINT") else 1.6
    ls = "--" if label.startswith("HEADROOM") else "-"
    ms = 13 if marker == "*" else 7
    ax1.plot(LOADS, [v[0] for v in vals], marker + ls, color=color, lw=lw,
             ms=ms, label=label)
    ax2.plot(LOADS, [v[1] for v in vals], marker + ls, color=color, lw=lw,
             ms=ms)

ax1.set_ylabel("coverage of all nodes  %")
ax1.set_ylim(45, 95)
ax1.grid(alpha=0.3)
ax1.legend(fontsize=8.8, loc="lower left")
ax1.set_title("(a)  coverage: the setpoint controller fills the allowed airtime and takes the best\n"
              "compliant coverage at every load; threshold ladders defend the cap instead",
              fontsize=10, loc="left")
ax1.annotate("climbs past R=3 on its own:\nbest coverage wherever headroom exists", (10, 86.1),
             textcoords="offset points", xytext=(16, 6), fontsize=8.4,
             color="#2ca02c",
             arrowprops=dict(arrowstyle="->", color="#2ca02c", lw=1.1))
ax1.annotate("beats full persistence,\nstill compliant", (90, 79.0),
             textcoords="offset points", xytext=(14, 8), fontsize=8.4,
             color="#2ca02c",
             arrowprops=dict(arrowstyle="->", color="#2ca02c", lw=1.1))

ax2.axhline(25, color="#d62728", lw=1.6, ls="--")
ax2.text(11, 26.0, "25% channel-utilization health cap", fontsize=8.6,
         color="#d62728")
ax2.set_ylabel("mean node channel utilization  %")
ax2.set_xlabel("offered load (broadcasts per hour, dense world)")
ax2.set_ylim(0, 34)
ax2.set_xticks(LOADS)
ax2.grid(alpha=0.3)
ax2.set_title("(b)  channel state: statics cross the health cap at saturating load; the controllers stay under\n"
              "(strict: 98.3% of nodes compliant; frontier ladder trades some compliance for coverage)",
              fontsize=10, loc="left")
ax2.annotate("statics breach the cap:\n100% of nodes over", (160, 31.0),
             textcoords="offset points", xytext=(-125, -6), fontsize=8.4,
             color="#d62728")
ax2.annotate("controllers hold the mean under cap", (145, 19.8),
             textcoords="offset points", xytext=(-60, -46), fontsize=8.4,
             color="#2ca02c",
             arrowprops=dict(arrowstyle="->", color="#2ca02c", lw=1.0))

fig.suptitle("Headroom control on the dense world: slide along the price curve by measured channel utilization \u2014\n"
             "as fast as the network's current state allows, never faster",
             fontsize=11, fontweight="bold", y=0.99)
fig.savefig("fig_headroom.png", dpi=150, bbox_inches="tight")
print("wrote fig_headroom.png")
