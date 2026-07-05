"""Figure: the reliability ladder toward the network's delivery ceiling."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

GREEN = "#2ca02c"
GRAY = "#7f7f7f"
RED = "#d62728"
BLUE = "#1f77b4"

fig = plt.figure(figsize=(13.6, 4.6))
gs = fig.add_gridspec(1, 2, width_ratios=[2.1, 1.0], wspace=0.22)

# ---- (a) the ladder ----
ax = fig.add_subplot(gs[0])
labels = ["GradCor-R\n(published)", "+ cold-start\nfallback flood",
          "+ rescue flood\nat dead end", "+ retries\nk=1",
          "+ retries\nk=3", "+ retries\nk=5",
          "+ custody\nhold \u226424 h"]
dlv = [50.9, 55.1, 60.0, 75.3, 84.9, 88.0, 94.5]
txd = [21.5, 22.9, 26.3, 31.0, 37.7, 42.7, 79.7]
shades = ["#2ca02c", "#43ab43", "#5ab55a", "#71c071", "#88ca88", "#9fd49f", "#b6dfb6"]
x = range(len(labels))
bars = ax.bar(x, dlv, color=shades, edgecolor="#2ca02c", linewidth=0.8)
for xi, d in zip(x, dlv):
    ax.text(xi, d + 1.2, f"{d:.1f}%", ha="center", fontsize=9, fontweight="bold")

ax.axhline(93.2, color=RED, lw=1.8, ls="--")
ax.text(0.02, 89.0, "93.2%  instant-reachability ceiling\n(no algorithm passes this)",
        fontsize=8.3, color=RED, va="top",
        transform=ax.get_yaxis_transform())
ax.axhline(95.6, color=RED, lw=1.2, ls=":")
ax.text(0.02, 99.5, "95.6%  ceiling with 24 h patience (4.4% never see a path all week)",
        fontsize=8.3, color="#a04040", transform=ax.get_yaxis_transform())
ax.axhline(25.3, color=GRAY, lw=1.2, ls="--")
ax.text(0.985, 20.0, "managed flood: 25.3% @ 71 tx/dlv", fontsize=8.3,
        color=GRAY, ha="right", transform=ax.get_yaxis_transform())

ax.set_xticks(list(x))
ax.set_xticklabels(labels, fontsize=8)
ax.set_ylabel("delivery rate %")
ax.set_ylim(0, 108)
ax.set_title("(a)  each addition is one simple rule; the ceiling is the network's, not the protocol's",
             fontsize=10, loc="left")

ax2 = ax.twinx()
ax2.plot(x, txd, "kD--", ms=6)
ax2.set_ylabel("tx per delivered packet")
ax2.set_ylim(0, 115)
for xi, t in zip(x, txd):
    ax2.annotate(f"{t:.0f}", (xi, t), textcoords="offset points", xytext=(8, 5),
                 fontsize=8)

# ---- (b) what remains at k=5 ----
axb = fig.add_subplot(gs[1])
cats = ["unreachable", "mid-walk dead end", "cold start"]
notes = ["no forward path exists this hour \u2014 physics",
         "reachable, but the walk died \u2014 routing",
         "no gradient and the fallback flood failed"]
vals = [56.6, 23.9, 19.5]
colors = [RED, "#e8a13c", BLUE]
yb = list(range(len(cats)))[::-1]
axb.barh(yb, vals, color=colors, height=0.5)
for y, v, c, n in zip(yb, vals, cats, notes):
    axb.text(1.5, y + 0.36, c, va="bottom", fontsize=9, fontweight="bold")
    axb.text(v + 1.5, y, f"{v:.1f}%", va="center", fontsize=9, fontweight="bold")
    axb.text(1.5, y - 0.40, n, va="top", fontsize=7.6, color="#444")
axb.set_yticks([])
axb.set_xlabel("share of remaining failures (e2e retries k=5)")
axb.set_xlim(0, 70)
axb.set_ylim(-0.8, 2.8)
axb.set_title("(b)  failures remaining at k=5:\nmost are physics, not routing", fontsize=10, loc="left")
axb.grid(alpha=0.3, axis="x")

fig.suptitle("The road toward 99%: a reliability ladder on the Norway replay (10 seeds) \u2014 "
             "99% absolute is unreachable on this network; 98.9% of the temporal ceiling is not",
             fontsize=11.5, fontweight="bold", y=1.04)
fig.savefig("fig_target99.png", dpi=150, bbox_inches="tight")
print("wrote fig_target99.png")
