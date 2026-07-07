"""Capstone figure: the complete self-calibrating stack + gains vs flood."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

GREEN = "#2ca02c"
DGREEN = "#1a5c1a"
BLUE = "#1f77b4"
ORANGE = "#e8890c"
PURPLE = "#9467bd"
RED = "#d62728"
GRAY = "#555555"

fig = plt.figure(figsize=(14.6, 9.2))
gs = fig.add_gridspec(1, 2, width_ratios=[1.72, 1.0], wspace=0.04)

# ================= (a) the stack, as a mind map =================
ax = fig.add_subplot(gs[0])
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.axis("off")


def box(x, y, w, h, title, lines, color, title_fs=9.6, fs=7.9, lh=0.315):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.06,rounding_size=0.10",
                                fc="white", ec=color, lw=1.8, zorder=3))
    ax.text(x + 0.14, y + h - 0.13, title, fontsize=title_fs, fontweight="bold",
            color=color, va="top", zorder=4)
    yy = y + h - 0.52
    for ln in lines:
        ax.text(x + 0.16, yy, ln, fontsize=fs, va="top", color="#222",
                zorder=4, linespacing=1.15)
        yy -= lh * (1 + ln.count("\n"))


def link(x1, y1, x2, y2, color):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-",
                                 color=color, lw=1.6, alpha=0.65, zorder=1,
                                 connectionstyle="arc3,rad=0.08"))


# central hub
hub = FancyBboxPatch((3.55, 4.05), 2.9, 1.62,
                     boxstyle="round,pad=0.08,rounding_size=0.14",
                     fc="#eef7ee", ec=DGREEN, lw=2.6, zorder=3)
ax.add_patch(hub)
ax.text(5.0, 5.56, "ONE SELF-CALIBRATING\nSTACK", ha="center", va="top",
        fontsize=10.6, fontweight="bold", color=DGREEN, zorder=4)
ax.text(5.0, 4.92, "measurement replaces configuration:\nno roles, no clocks, no hop\ncounters, no user knobs",
        ha="center", va="top", fontsize=7.6, color="#333", zorder=4)

# UNICAST (top left)
box(0.08, 6.6, 4.1, 3.3, "UNICAST \u2014 GradCor-R  (\u00a73)", [
    "\u2022 one byte per active destination (hops to it)",
    "\u2022 broadcast once \u2192 closer receivers race,",
    "   winner's forward = implicit ack",
    "\u2022 corridor widens per hop on failure:",
    "   strict \u2192 equal \u2192 any (graceful \u2192 flood)",
    "\u2022 NO HOP LIMIT: strict descent terminates",
    "\u2022 refresh rides delivery \u2014 traffic is upkeep",
    "\u2022 cold start = today's flood; no announce,",
    "   no beaconing (relays never need NodeDB)",
], GREEN)
link(3.6, 6.6, 4.5, 5.6, GREEN)

# RELIABILITY (top right)
box(5.75, 6.6, 4.15, 3.3, "RELIABILITY ENVELOPE  (\u00a76.2)", [
    "\u2022 end-to-end retries (already in firmware)",
    "\u2022 rescue flood from the stuck node",
    "\u2022 custody: hold \u2264 24 h, retry hourly",
    "\u2192 94.5% delivered = 98.9% of what the",
    "   network physically allows",
    "",
    "DEPTH  (\u00a76.6): walk survives 200 hops",
    "(97\u2013100%, linear cost); floods decay to 0%;",
    "echo-persist rescues alert broadcasts",
], DGREEN)
link(6.4, 6.6, 5.6, 5.6, DGREEN)

# BROADCAST (left)
box(0.08, 2.55, 3.2, 3.5, "BROADCAST \u2014 flood kept\n(\u00a76.3\u20136.4)", [
    "",
    "\u2022 with dst = everyone, GradCor",
    "   reduces to managed flood:",
    "   already the optimal form",
    "\u2022 hop limit: raise default 3 \u2192 7",
    "   (removal safe but marginal)",
    "\u2022 coverage prices linearly in",
    "   log-airtime \u2014 one curve,",
    "   no scheme escapes it",
], BLUE, title_fs=8.8)
link(3.28, 4.6, 3.57, 4.9, BLUE)

# PRESSURE (bottom left)
box(0.35, 0.1, 4.1, 2.15, "WHO RELAYS \u2014 relay pressure  (\u00a76.7)", [
    "\u2022 crowding: duplicates heard (EWMA)",
    "\u2022 novelty: do my relays still reach anyone new?",
    "\u2022 interiors fade to silence, bridges self-promote",
    "\u2022 replaces the role enum \u2014 zero config",
], ORANGE)
link(2.6, 2.25, 4.2, 4.35, ORANGE)

# GOVERNORS (bottom right)
box(5.0, 0.1, 4.75, 2.15, "HOW MUCH / HOW FAST \u2014 governors  (\u00a76.5, \u00a76.8)", [
    "\u2022 message class caps persistence: BULK / STANDARD /",
    "   ASSURED (2 header bits, shared with corridor level)",
    "\u2022 setpoint controller fills the utilization cap:",
    "   spend surplus when idle, retreat at saturation",
], PURPLE, title_fs=8.8)
link(7.2, 2.25, 5.8, 4.35, PURPLE)

# FLOOR (right)
box(6.85, 2.55, 3.05, 3.2, "THE CONSTANT \u2014 physics\n(\u00a76.1)", [
    "",
    "\u2022 placement & evidence density",
    "   set every ceiling: 93% of real",
    "   pairs reachable, ~35% of",
    "   nodes floodable, price-curve",
    "   slope per network",
    "\u2022 the last points are bought",
    "   with routers, not protocols",
], RED, title_fs=8.9)
link(6.85, 4.6, 6.45, 4.9, RED)

ax.set_title("(a)  every mechanism reads a signal the radio already provides \u2014 and nothing else",
             fontsize=10.5, loc="left")

# ================= (b) gains vs managed flood =================
axb = fig.add_subplot(gs[1])
axb.set_xlim(0, 10)
axb.set_ylim(0, 10)
axb.axis("off")
axb.set_title("(b)  gains over managed flood (replay-calibrated)",
              fontsize=10.5, loc="left")

GAINS = [
    ("UNICAST DELIVERY", GREEN,
     "25.3%  \u2192  50.7%", "2.0\u00d7, at 3.3\u00d7 less airtime per delivered packet"),
    ("WITH RELIABILITY ENVELOPE", DGREEN,
     "25.3%  \u2192  94.5%", "3.7\u00d7 \u2014 98.9% of the network's physical ceiling"),
    ("DELIVERY AT 200 HOPS", GREEN,
     "0%  \u2192  97%", "no hop limit + per-hop persistence, linear cost"),
    ("DENSE BROADCAST (synthetic)", ORANGE,
     "78% @ 47tx  \u2192  84% @ 18tx", "+5 pts coverage at 60% less airtime (pressure)"),
    ("SPARSE BROADCAST (Norway)", PURPLE,
     "20%  \u2192  46%", "setpoint spends allowed headroom; priced, not free"),
    ("CONFIGURATION BURDEN", BLUE,
     "roles + hop settings  \u2192  none", "two EWMAs + one utilization target, all self-set"),
    ("ROUTING STATE", GRAY,
     "n/a  \u2192  1 byte / active dest.", "relays need no NodeDB, no paths, no neighbours"),
]

y = 9.35
for title, color, delta, note in GAINS:
    axb.add_patch(FancyBboxPatch((0.25, y - 1.08), 9.5, 1.14,
                                 boxstyle="round,pad=0.05,rounding_size=0.10",
                                 fc="white", ec=color, lw=1.6))
    axb.text(0.5, y - 0.08, title, fontsize=7.9, fontweight="bold", color=color,
             va="top")
    axb.text(0.5, y - 0.40, delta, fontsize=10.4, fontweight="bold",
             color="#111", va="top")
    axb.text(0.5, y - 0.82, note, fontsize=7.4, color="#444", va="top")
    y -= 1.30

axb.text(0.30, 0.02,
         "All numbers from the calibrated replay and synthetic stress worlds of \u00a75\u2013\u00a76;\n"
         "absolute values are model outputs \u2014 rankings and ratios are the findings (\u00a78).",
         fontsize=7.4, color="#666", va="bottom")

fig.suptitle("The complete picture: gradient-corridor unicast + self-calibrating flood \u2014 "
             "one stack, measured end to end",
             fontsize=12.5, fontweight="bold", y=0.985)
fig.savefig("fig_stack.png", dpi=150, bbox_inches="tight")
print("wrote fig_stack.png")
