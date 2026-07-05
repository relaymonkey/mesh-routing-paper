"""Ablation figure: gradient hazard curve + threshold (in)sensitivity."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

GREEN = "#2ca02c"
GRAY = "#7f7f7f"
RED = "#d62728"
BLUE = "#1f77b4"

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.6, 4.2))

# ---- (a) hazard: outcome vs gradient age at source (baseline 3/24, 10 seeds) ----
labels = ["0\n(just\nrefreshed)", "1-2 h", "3-6 h", "7-12 h", "13-23 h", "dead\n(replant)"]
dlv = [35.4, 69.6, 41.4, 28.0, 17.0, 3.1]
txd = [48.5, 14.8, 32.5, 51.4, 90.6, 249.3]
sent = [752, 18141, 3496, 1246, 816, 5739]
x = range(len(labels))
bars = ax1.bar(x, dlv, color=[GRAY, GREEN, "#7bbf7b", "#a8d0a8", "#cfe3cf", RED])
for xi, (d, s) in enumerate(zip(dlv, sent)):
    ax1.text(xi, d + 1.5, f"{d:.0f}%", ha="center", fontsize=9, fontweight="bold")
    ax1.text(xi, 2.0, f"n={s}", ha="center", fontsize=7.5, color="#333")
ax1.set_xticks(list(x))
ax1.set_xticklabels(labels, fontsize=8.5)
ax1.set_ylabel("delivery rate %")
ax1.set_ylim(0, 80)
ax1.set_title("(a)  gradients do rot: outcome vs gradient age at source\n"
              "(smooth decay, no cliff at any particular hour)", fontsize=10, loc="left")
ax12 = ax1.twinx()
ax12.plot(x, txd, "kD--", ms=6)
ax12.set_yscale("log")
ax12.set_ylabel("tx per delivered (log)")

# ---- (b) ...but the wall-clock threshold barely matters ----
widen = [0, 1, 3, 6, 12, 24]
widen_lbl = ["0", "1", "3\n(baseline)", "6", "12", "never"]
w_dlv = [47.2, 48.6, 49.7, 50.6, 49.7, 49.3]
ax2.plot(range(len(widen)), w_dlv, "o-", color=BLUE, lw=2, ms=7,
         label="age-based widening, AGE_WIDEN swept")
ax2.axhline(50.9, color=GREEN, lw=2.2, ls="--")
ax2.text(0.05, 54.3, "reactive-only: no wall clock in eligibility at all\n"
         "(50.9%, 10 seeds)", fontsize=9, color=GREEN, fontweight="bold")
ax2.axhline(49.7, color=GRAY, lw=1.4, ls=":")
ax2.text(0.05, 44.6, "baseline 3 h / 24 h (49.7%, 10 seeds)", fontsize=8.5, color="#555")
ax2.set_xticks(range(len(widen)))
ax2.set_xticklabels(widen_lbl, fontsize=8.5)
ax2.set_xlabel("AGE_WIDEN threshold (hours)")
ax2.set_ylabel("delivery rate %")
ax2.set_ylim(42, 56)
ax2.set_title("(b)  ...but the clock is redundant: sweep is flat and the\n"
              "clock-free reactive variant matches or beats every setting",
              fontsize=10, loc="left")
ax2.legend(fontsize=8.5, loc="lower right")
ax2.grid(alpha=0.3)

fig.suptitle("Ablation: staleness is real, but a failed broadcast already measures it \u2014 "
             "the per-hop escalation makes the wall-clock thresholds unnecessary",
             fontsize=12, fontweight="bold", y=1.03)
fig.tight_layout()
fig.savefig("fig_ablation.png", dpi=150, bbox_inches="tight")
print("wrote fig_ablation.png")
