"""One-figure summary of GradCor: approach, node perspective, endless hops."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import matplotlib.colors as mcolors

GREEN = "#2ca02c"
GRAY = "#7f7f7f"
RED = "#d62728"
BLUE = "#1f77b4"

fig = plt.figure(figsize=(12.6, 10.6))
gs = fig.add_gridspec(3, 1, height_ratios=[0.72, 1.15, 1.0], hspace=0.40)


def band_title(ax, letter, text):
    ax.text(0.0, 1.04, f"({letter})  {text}", transform=ax.transAxes,
            fontsize=12.5, fontweight="bold", va="bottom")


def node(ax, x, y, ms, face, edge, label, fs=8.5, lw=1.6, tcolor="#1a1a1a"):
    ax.plot([x], [y], "o", ms=ms, mfc=face, mec=edge, mew=lw, zorder=5)
    ax.text(x, y, label, ha="center", va="center", fontsize=fs, zorder=6,
            color=tcolor, linespacing=1.25)


# ---------------- (a) the general approach: knowledge spectrum ----------------
ax = fig.add_subplot(gs[0])
ax.set_xlim(0, 10)
ax.set_ylim(0, 1)
ax.axis("off")
band_title(ax, "a", "The approach: uncertainty is a dial, not a failure mode")

cmap = mcolors.LinearSegmentedColormap.from_list("spec", ["#8c8c8c", GREEN, RED])
for i in range(300):
    x = 0.6 + (8.8 * i / 300)
    ax.plot([x, x + 8.8 / 300], [0.46, 0.46], color=cmap(i / 300), lw=8,
            solid_capstyle="butt")

ax.text(0.6, 0.62, "FLOOD", fontsize=11.5, fontweight="bold", color="#555", ha="left")
ax.text(0.6, 0.30, "routes with zero knowledge:\nrobust, works anywhere,\npays full airtime every packet",
        fontsize=8.5, color="#555", ha="left", va="top")
ax.text(9.4, 0.62, "SOURCE PATH", fontsize=11.5, fontweight="bold", color=RED, ha="right")
ax.text(9.4, 0.30, "routes with total assumed knowledge:\ncheapest per packet,\nbreaks when any assumption fails",
        fontsize=8.5, color=RED, ha="right", va="top")
ax.plot([7.75], [0.46], "D", ms=8, color=BLUE, zorder=5)
ax.text(7.62, 0.60, "NEXTHOP (2.6)", fontsize=8.5, color=BLUE, ha="right")

arr = FancyArrowPatch((3.05, 0.46), (6.15, 0.46), arrowstyle="<|-|>",
                      mutation_scale=16, color=GREEN, lw=2.6, zorder=6)
ax.add_patch(arr)
ax.plot([4.6], [0.46], "o", ms=13, mfc="white", mec=GREEN, mew=2.6, zorder=7)
ax.text(4.6, 0.66, "GRADCOR slides continuously on failure evidence",
        fontsize=10, fontweight="bold", color=GREEN, ha="center")
ax.text(3.05, 0.30, "broadcasts failing\n\u2192 widen toward flood", fontsize=8.5,
        color=GREEN, ha="center", va="top")
ax.text(6.15, 0.30, "descent succeeding\n\u2192 tight, near-unicast cost", fontsize=8.5,
        color=GREEN, ha="center", va="top")

# ---------------- (b) each node's perspective ----------------
ax = fig.add_subplot(gs[1])
ax.set_xlim(0, 10)
ax.set_ylim(-0.14, 1.0)
ax.axis("off")
band_title(ax, "b", "One node's whole world: one number, one local rule")

hx, hy = 1.25, 0.55
for ms, al in [(150, 0.14), (110, 0.22), (75, 0.32)]:
    ax.plot([hx], [hy], "o", ms=ms, mfc="none", mec=GRAY, mew=1.3, alpha=al, zorder=2)
node(ax, hx, hy, 46, "#ececec", "#444", "holder\ng\u2095=6", fs=8.5)
ax.text(hx, 0.08, "broadcasts ONCE\nheader: dst=D, g\u2095=6, corridor level",
        ha="center", fontsize=8.5, color="#555", va="top")

nx_, ny_ = 3.85, 0.55
node(ax, nx_, ny_, 58, "#dcebfa", BLUE, "node N\n\ng = 5", fs=8.5, lw=2.2, tcolor=BLUE)

node(ax, 3.25, 0.87, 30, "white", "#999", "g=6", fs=8)
ax.text(3.55, 0.87, "not closer \u2192 stays silent", fontsize=8, color="#888",
        ha="left", va="center")
node(ax, 3.35, 0.20, 30, "white", "#999", "g=7", fs=8)
ax.text(3.65, 0.20, "not closer \u2192 stays silent", fontsize=8, color="#888",
        ha="left", va="center")

arr = FancyArrowPatch((hx + 0.42, hy), (nx_ - 0.48, ny_), arrowstyle="-|>",
                      mutation_scale=15, color=GREEN, lw=2.4, zorder=4)
ax.add_patch(arr)

card = FancyBboxPatch((5.30, -0.12), 4.55, 1.07,
                      boxstyle="round,pad=0.02,rounding_size=0.03",
                      fc="#f8faf7", ec=GREEN, lw=1.4)
ax.add_patch(card)
ax.text(5.50, 0.90, "N's entire routing logic, run on every decoded frame:",
        fontsize=9, fontweight="bold", va="top")
lines = [
    ("1.", "am I the destination?  \u2192 deliver, refresh gradient on the path"),
    ("2.", "is my g inside the corridor?\n(levels 0\u20132: g < g\u2095;   level 3: g \u2264 g\u2095;   level 4: any receiver)"),
    ("3.", "eligible \u2192 start timer \u221d (my g, link SNR) \u2014 closest fires first"),
    ("4.", "overhear someone else forward first \u2192 mute"),
    ("5.", "seen this packet ID before \u2192 ignore (dedup)"),
]
y = 0.78
for n, t in lines:
    ax.text(5.55, y, n, fontsize=8.6, fontweight="bold", va="top", color=GREEN)
    ax.text(5.82, y, t, fontsize=8.6, va="top", linespacing=1.3)
    y -= 0.125 if "\n" not in t else 0.20
ax.text(5.55, y - 0.005,
        "no neighbour table, no route cache, no topology map, no clock \u2014\n"
        "one byte of state per active destination, every decision local",
        fontsize=8.4, style="italic", color="#333", va="top", linespacing=1.3)

# ---------------- (c) endless hops ----------------
ax = fig.add_subplot(gs[2])
ax.set_xlim(0, 10)
ax.set_ylim(-0.08, 1.0)
ax.axis("off")
band_title(ax, "c", "Why hops are unlimited: progress itself is the permit")

n_hops = 12
xs = [0.55 + i * (8.9 / n_hops) for i in range(n_hops + 1)]
y0 = 0.45
for i, x in enumerate(xs):
    g = n_hops - i
    if i == 0:
        node(ax, x, y0, 30, "#dcebfa", BLUE, str(g), fs=8.5, lw=1.8)
        ax.text(x, y0 - 0.22, "src", ha="center", fontsize=9, color=BLUE, fontweight="bold")
    elif i == n_hops:
        node(ax, x, y0, 30, "#fbe0e0", RED, str(g), fs=8.5, lw=1.8)
        ax.text(x, y0 - 0.22, "dst", ha="center", fontsize=9, color=RED, fontweight="bold")
    else:
        node(ax, x, y0, 26, "white", "#555", str(g), fs=8, lw=1.2)
    if i < n_hops:
        arr = FancyArrowPatch((x + 0.17, y0), (xs[i + 1] - 0.17, y0),
                              arrowstyle="-|>", mutation_scale=10,
                              color=GREEN, lw=1.8)
        ax.add_patch(arr)

wall_x = xs[7] + (8.9 / n_hops) / 2
ax.plot([wall_x, wall_x], [0.28, 0.72], ls="--", color=RED, lw=2)
ax.text(wall_x, 0.76, "hop_limit = 7:  flood is amputated here,\neven if it was still making progress",
        ha="center", fontsize=8.8, color=RED, va="bottom")
ax.text((xs[0] + wall_x) / 2 - 0.3, 0.68,
        "g strictly decreases at every hop:  12 \u2192 11 \u2192 \u2026",
        ha="center", fontsize=9, color=GREEN)
ax.text(9.98, 0.62,
        "\u2026 \u2192 1 \u2192 0.  GradCor continues:\na finite integer cannot decrease forever,\nso termination and loop freedom are\narithmetic facts \u2014 no counter needed",
        ha="right", fontsize=8.8, color=GREEN, va="bottom", linespacing=1.3)

ax.text(0.55, 0.10,
        "The packet travels exactly as far as justified progress exists \u2014 12, 20, 50 hops \u2014 and no further:  a node whose neighbourhood\n"
        "offers no eligible receiver at any corridor level is a certified local minimum \u2192 deterministic drop + route error, never a silent loop.",
        fontsize=9, va="top", color="#333", linespacing=1.4)

fig.suptitle("GradCor at a glance: route with whatever knowledge exists, locally, for as long as progress is real",
             fontsize=13.5, fontweight="bold", y=0.97)
fig.savefig("fig_summary.png", dpi=150, bbox_inches="tight")
print("wrote fig_summary.png")
