"""How each node builds its two numbers: plant, store, refresh."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle

GREEN = "#2ca02c"
GRAY = "#8a8a8a"
RED = "#d62728"
BLUE = "#1f77b4"
AMBER = "#c9861f"

fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.6),
                         gridspec_kw={"width_ratios": [1.15, 0.95, 1.15]})


def node(ax, x, y, r, face, edge, label, fs=8.5, lw=1.6, tcolor="#1a1a1a", z=5):
    ax.add_patch(Circle((x, y), r, fc=face, ec=edge, lw=lw, zorder=z))
    ax.text(x, y, label, ha="center", va="center", fontsize=fs, zorder=z + 1,
            color=tcolor, linespacing=1.2)


# ---------------- (a) planting ----------------
ax = axes[0]
ax.set_xlim(0, 10.6)
ax.set_ylim(-2.5, 9.4)
ax.set_aspect("equal")
ax.axis("off")
ax.set_title("(a)  planting: one flood outward from dst\nstamps every node with its hop distance",
             fontsize=10, fontweight="bold", loc="left")

D = (8.2, 4.6)
for r, lab in [(2.3, "hop 1"), (4.3, "hop 2"), (6.3, "hop 3")]:
    ax.add_patch(Circle(D, r, fill=False, ec=GRAY, ls=(0, (4, 4)), lw=1.1, alpha=0.7))
    ax.text(D[0], D[1] - r - 0.38, lab, fontsize=7.5, color=GRAY, ha="center")

node(ax, *D, 0.62, "#fbe0e0", RED, "dst\ng=0", fs=8, lw=2)
plant_nodes = {
    "A": ((6.35, 6.05), 1), "B": ((6.85, 2.55), 1),
    "C": ((4.35, 6.75), 2), "E": ((4.25, 3.55), 2), "Dn": ((5.15, 1.35), 2),
    "F": ((2.05, 5.55), 3), "G": ((2.45, 2.15), 3),
}
for name, ((x, y), g) in plant_nodes.items():
    node(ax, x, y, 0.55, "white", "#555", f"g={g}", fs=8)

def parr(ax, p, q, color=GREEN, ls="-", lw=1.9):
    a = FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=11,
                        shrinkA=14, shrinkB=14, color=color, lw=lw,
                        linestyle=ls, zorder=3)
    ax.add_patch(a)

parr(ax, D, plant_nodes["A"][0])
parr(ax, D, plant_nodes["B"][0])
parr(ax, plant_nodes["A"][0], plant_nodes["C"][0])
parr(ax, plant_nodes["A"][0], plant_nodes["E"][0])
parr(ax, plant_nodes["B"][0], plant_nodes["Dn"][0])
parr(ax, plant_nodes["C"][0], plant_nodes["F"][0])
parr(ax, plant_nodes["Dn"][0], plant_nodes["G"][0])
# duplicate copy, ignored
parr(ax, plant_nodes["B"][0], plant_nodes["E"][0], color=GRAY, ls=(0, (3, 3)), lw=1.3)
mid = ((plant_nodes["B"][0][0] + plant_nodes["E"][0][0]) / 2,
       (plant_nodes["B"][0][1] + plant_nodes["E"][0][1]) / 2)
ax.annotate("late copy: dedup \u2192\nignored, keeps first g", xy=mid,
            xytext=(9.3, 0.6), fontsize=7.2, color=GRAY, ha="center",
            linespacing=1.2,
            arrowprops=dict(arrowstyle="-", color=GRAY, lw=0.7, alpha=0.7))
ax.text(0.1, -2.4, "no requests, no ACKs \u2014 every node just listens\nand records the hop it first decoded",
        fontsize=8, color="#333", va="bottom")

# ---------------- (b) what one node stores ----------------
ax = axes[1]
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.axis("off")
ax.set_title("(b)  the result at node F:\nits entire routing state",
              fontsize=10, fontweight="bold", loc="left")

card = FancyBboxPatch((0.3, 1.7), 9.6, 6.9,
                      boxstyle="round,pad=0.02,rounding_size=0.25",
                      fc="#f8faf7", ec=GREEN, lw=1.5)
ax.add_patch(card)
ax.text(0.9, 7.9, "gradient table @ F", fontsize=9.5, fontweight="bold")
cols = [0.9, 2.7, 4.0, 5.9]
for cx, htxt in zip(cols, ["dst", "g", "age (v1)", ""]):
    ax.text(cx, 7.0, htxt, fontsize=9, fontweight="bold", color="#555")
rows = [
    ("D", "3", "0 h",  "fresh \u2192 strict corridor", GREEN),
    ("K", "5", "7 h",  "aged \u2192 wider corridor", AMBER),
    ("Q", "4", "26 h", "dead \u2192 replant on use", RED),
]
for i, (d, g, a, note, c) in enumerate(rows):
    y = 6.0 - i * 1.3
    ax.text(cols[0], y, d, fontsize=9.5, family="monospace")
    ax.text(cols[1], y, g, fontsize=9.5, family="monospace")
    ax.text(cols[2], y, a, fontsize=9.5, family="monospace")
    ax.text(cols[3], y, note, fontsize=7.5, color=c)
ax.text(0.9, 2.3, "rows exist only for destinations someone here\ntalks to \u00b7 final spec keeps only g (1 byte/row)",
        fontsize=8, color="#333", linespacing=1.3)
ax.text(0.4, 0.6, "no neighbour list, no link metrics, no map \u2014\nthe corridor rule turns these rows into forwarding",
        fontsize=8, style="italic", color="#333", va="top", linespacing=1.3)

# ---------------- (c) refresh on delivery ----------------
ax = axes[2]
ax.set_xlim(0, 10.6)
ax.set_ylim(0, 9.4)
ax.axis("off")
ax.set_title("(c)  refresh: a delivered packet re-stamps\nits own path \u2014 zero extra airtime",
             fontsize=10, fontweight="bold", loc="left")

chain_y = 5.6
xs = [0.9, 3.2, 5.5, 7.8, 10.0]
labels = ["src", "", "", "", "dst"]
news = ["g\u21904", "g\u21903", "g\u21902", "g\u21901", "g=0"]
olds = ["was g=6\nage 9 h", "was g=5\nage 9 h", "was g=4\nage 9 h", "was g=2\nage 9 h", ""]
for i, x in enumerate(xs):
    face = "#dcebfa" if i == 0 else ("#fbe0e0" if i == 4 else "white")
    edge = BLUE if i == 0 else (RED if i == 4 else "#555")
    node(ax, x, chain_y, 0.58, face, edge, labels[i] or "", fs=8,
         lw=1.9 if i in (0, 4) else 1.4)
    if i < 4:
        parr(ax, (x, chain_y), (xs[i + 1], chain_y))
    if olds[i]:
        ax.text(x, chain_y + 1.55, olds[i], fontsize=7.3, color="#999",
                ha="center", linespacing=1.2)
        ax.plot([x - 0.62, x + 0.62], [chain_y + 1.55, chain_y + 1.55],
                color="#bbb", lw=0.9)
    ax.text(x, chain_y - 1.45, news[i] + "\nage\u21900", fontsize=8, color=GREEN,
            ha="center", fontweight="bold", linespacing=1.25)
ax.text(10.0, chain_y + 1.35, "delivered \u2713", fontsize=9, color=GREEN,
        ha="center", fontweight="bold")
ax.text(0.25, 1.15, "each node on the working path learns its TRUE distance\nalong a path that demonstrably works, and its corridor\nsnaps tight again \u2014 active routes maintain themselves",
        fontsize=8, color="#333", va="top", linespacing=1.35)

fig.suptitle("How the two numbers are built: planted by one flood, kept per destination, re-stamped for free by every delivery",
             fontsize=12.5, fontweight="bold", y=1.02)
fig.tight_layout()
fig.savefig("fig_plant.png", dpi=150, bbox_inches="tight")
print("wrote fig_plant.png")
