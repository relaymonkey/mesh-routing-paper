"""Method-section figures: link probability model + GradCor corridor mechanics."""
import math
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

import sim_norway as S

# ---------- fig: link delivery model ----------
X0, PMAX, PMIN, KOBS = 8, 0.8, 0.25, 10

def p_link(snr_db, obs):
    w = obs / (obs + KOBS)
    return w * (PMIN + (PMAX - PMIN) / (1 + math.exp(-(snr_db - X0) / 4.0)))

trs = S.load_traceroutes()
links = S.links_from_traceroutes(trs)
snr_means = [st.mean(s) / 4 for _, s, _ in links.values() if s]
obs_counts = [o for o, _, _ in links.values()]

fig, (ax, axh) = plt.subplots(
    2, 1, figsize=(7.2, 5.0), sharex=True,
    gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})
xs = [x / 2 for x in range(-60, 71)]
for obs, style in [(1, ":"), (5, "--"), (20, "-."), (200, "-")]:
    ax.plot(xs, [p_link(x, obs) for x in xs], style, lw=2,
            label=f"observed {obs}\u00d7 in window (w={obs/(obs+KOBS):.2f})")
ax.axvline(X0, color="#999", lw=0.8)
ax.annotate("x\u2080 = 8 dB", (X0, 0.82), fontsize=9, color="#555",
            xytext=(10, 0.82))
ax.set_ylabel("per-transmission delivery probability")
ax.set_ylim(0, 1)
ax.legend(fontsize=9, title="evidence weight", title_fontsize=9)
ax.grid(alpha=0.3)

axh.hist(snr_means, bins=60, range=(-30, 35), color="#1f77b4", alpha=0.8)
axh.set_xlabel("link mean SNR (dB, raw snr_towards / 4)")
axh.set_ylabel("links")
axh.grid(alpha=0.3)
fig.savefig("fig_linkmodel.png", dpi=150, bbox_inches="tight")

# ---------- fig: GradCor corridor mechanics ----------
# small illustrative graph: columns = gradient value (hops to dst)
pos = {
    "dst": (3.0, 1.0),
    "a1": (2.0, 1.6), "a2": (2.0, 0.4),
    "b1": (1.0, 1.8), "b2": (1.0, 1.0), "b3": (1.0, 0.2),
    "src": (0.0, 1.0), "c1": (0.0, 1.9),
    "d1": (-0.05, 0.1),
}
grad = {"dst": 0, "a1": 1, "a2": 1, "b1": 2, "b2": 2, "b3": 2,
        "src": 3, "c1": 3, "d1": 4}
edges = [("src", "b1"), ("src", "b2"), ("src", "b3"), ("src", "c1"),
         ("src", "d1"),
         ("b1", "a1"), ("b2", "a1"), ("b2", "a2"), ("b3", "a2"),
         ("b1", "b2"), ("b2", "b3"),
         ("a1", "dst"), ("a2", "dst"), ("a1", "a2"), ("c1", "b1")]

panels = [
    ("(a) STRICT: strictly lower gradient only\nR: escalation levels 0\u20132 \u00b7 v1: fresh gradient",
     lambda u, v: grad[v] < grad[u]),
    ("(b) EQUAL admitted: lateral moves possible\nR: level 3, after strict fails \u00b7 v1: aged gradient",
     lambda u, v: grad[v] <= grad[u]),
    ("(c) ANY receiver \u2248 flood, last resort\nR: level 4 \u00b7 v1: stale gradient / local minimum",
     lambda u, v: True),
]

fig = plt.figure(figsize=(12.6, 7.0))
gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 0.78], hspace=0.34)
axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
for ax, (title, eligible) in zip(axes, panels):
    ax.set_title(title, fontsize=9.5)
    ax.set_xlim(-0.5, 3.5)
    ax.set_ylim(-0.35, 2.35)
    ax.axis("off")
    # broadcast circle around holder (src)
    holder = "src"
    circ = plt.Circle(pos[holder], 1.25, color="#2ca02c", alpha=0.07, zorder=0)
    ax.add_patch(circ)
    for u, v in edges:
        for a, b in ((u, v), (v, u)):
            if a != holder:
                continue
            ok = eligible(a, b)
            arr = FancyArrowPatch(
                pos[a], pos[b], arrowstyle="-|>", mutation_scale=13,
                shrinkA=13, shrinkB=13,
                color="#2ca02c" if ok else "#bbbbbb",
                lw=2.2 if ok else 1.0,
                linestyle="-" if ok else (0, (3, 3)), zorder=2)
            ax.add_patch(arr)
    # other edges faint
    for u, v in edges:
        if holder in (u, v):
            continue
        ax.plot([pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]],
                color="#dddddd", lw=0.9, zorder=1)
    for n, (x, y) in pos.items():
        is_ep = n in ("src", "dst")
        color = {"src": "#1f77b4", "dst": "#d62728"}.get(n, "white")
        ax.scatter([x], [y], s=560, c=color, edgecolors="#333",
                   linewidths=1.2, zorder=3)
        label = {"src": "src\ng=3", "dst": "dst\ng=0"}.get(n, f"g={grad[n]}")
        ax.text(x, y, label, ha="center", va="center", fontsize=8,
                color="white" if is_ep else "#222", zorder=4,
                fontweight="bold" if is_ep else "normal")
# ---------- panel (d): the contention race among panel (a)'s three eligible receivers ----------
GREEN, GRAY, RED = "#2ca02c", "#7f7f7f", "#d62728"
axr = fig.add_subplot(gs[1, :])
axr.set_title("(d) the race among (a)'s three eligible g=2 receivers \u2014 one-shot ms-scale backoff, "
              "armed by reception; same machinery as today's managed-flood contention window, re-keyed on (g, SNR)",
              fontsize=9.5, loc="left")
axr.set_xlim(0, 100)
axr.set_ylim(-0.7, 4.0)
axr.axis("off")

lanes = {"holder (g=3)": 3.2, "B  (g=2, best SNR)": 2.2,
         "A  (g=2)": 1.2, "C  (g=2, worst SNR)": 0.2}
for lab, y in lanes.items():
    axr.text(-1.5, y, lab, ha="right", va="center", fontsize=8.5)
    axr.plot([0, 100], [y, y], color="#eeeeee", lw=0.8, zorder=0)

def tx_block(x0, x1, y, color, label=None, ls="-"):
    axr.fill_betweenx([y - 0.13, y + 0.13], x0, x1, color=color, alpha=0.85, zorder=3)
    if label:
        axr.text((x0 + x1) / 2, y + 0.24, label, ha="center", fontsize=7.8, color=color)

def timer_bar(x0, x1, y):
    axr.fill_betweenx([y - 0.09, y + 0.09], x0, x1, facecolor="none",
                      edgecolor=GRAY, hatch="////", lw=0.9, zorder=2)

# holder broadcasts
tx_block(2, 14, lanes["holder (g=3)"], "#555555", "broadcast  (dst, g\u2095=3, STRICT)")
for lab in ("B  (g=2, best SNR)", "A  (g=2)", "C  (g=2, worst SNR)"):
    axr.plot([14], [lanes[lab]], "o", ms=5, color="#555555", zorder=4)
axr.text(14, -0.55, "all three decode \u2192 each arms a one-shot delay \u221d (own g, tie: SNR)",
         fontsize=7.8, color="#555", ha="left")

# timers: B shortest (best SNR wins the g-tie); A and C are cancelled at t=42,
# their scheduled expiry shown dotted
timer_bar(14, 30, lanes["B  (g=2, best SNR)"])
timer_bar(14, 42, lanes["A  (g=2)"])
timer_bar(14, 42, lanes["C  (g=2, worst SNR)"])
for lab, sched in (("A  (g=2)", 46), ("C  (g=2, worst SNR)", 60)):
    y = lanes[lab]
    axr.plot([42, sched], [y, y], ls=":", color=GRAY, lw=1.2, zorder=2)
    axr.plot([sched], [y], "|", ms=10, color=GRAY, zorder=2)

# B fires first: forwards, stamping its own g
tx_block(30, 42, lanes["B  (g=2, best SNR)"], GREEN, "timer fires first \u2192 forwards, stamps its own g=2")

# A and C decode B's forward and cancel
for lab in ("A  (g=2)", "C  (g=2, worst SNR)"):
    axr.plot([42], [lanes[lab]], "x", ms=9, color=RED, mew=2.2, zorder=5)
axr.text(63, lanes["A  (g=2)"] + 0.26, "overhears B at t=42 \u2192 cancels pending forward (never transmits)",
         fontsize=7.8, color=RED, va="center")
axr.text(63, lanes["C  (g=2, worst SNR)"] + 0.26,
         "cancels too \u2014 unless out of B's range: then a duplicate, absorbed by packet-ID dedup",
         fontsize=7.8, color=RED, va="center")

# holder hears the forward = implicit ack
axr.plot([42], [lanes["holder (g=3)"]], "o", ms=6, mfc="white", mec=GREEN, mew=1.8, zorder=5)
axr.text(43.5, lanes["holder (g=3)"] + 0.26,
         "overhears the forward = per-hop ack \u2192 done; silence here would arm retry, then a wider corridor",
         fontsize=7.8, color=GREEN, va="center")

axr.annotate("", xy=(97, -0.35), xytext=(2, -0.35),
             arrowprops=dict(arrowstyle="-|>", color="#999", lw=1.0))
axr.text(97, -0.28, "time (ms)", fontsize=7.5, color="#777", ha="right")

fig.suptitle("GradCor forwarding: one anycast broadcast from the holder; the eligibility corridor (green) widens\n"
             "\u2014 in the final spec (R) by per-hop failure escalation, in v1 additionally by gradient age", fontsize=11, y=1.02)
fig.savefig("fig_gradcor.png", dpi=150, bbox_inches="tight")
print("wrote fig_linkmodel.png, fig_gradcor.png")
