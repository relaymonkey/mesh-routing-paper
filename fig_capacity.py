"""Figure: current routing versus both integrated-stack operating modes."""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rows = list(csv.DictReader(open("integrated_stack_capacity.csv")))
baseline = [r for r in rows if r["policy"] == "managed current"]
fast = [r for r in rows if r["policy"] == "integrated fast"]
pivot = [r for r in rows if r["policy"] == "integrated fast+pivot"]
full = [r for r in rows if r["policy"] == "integrated full"]
nodes = [int(r["equiv_nodes"]) for r in baseline]


def crossing(xs, ys, target=25):
    for x1, x2, y1, y2 in zip(xs, xs[1:], ys, ys[1:]):
        if y1 <= target < y2:
            return x1 + (target - y1) * (x2 - x1) / (y2 - y1)
    return None


series = {}
for name, policy_rows in (("managed", baseline), ("fast", fast),
                          ("pivot", pivot), ("full", full)):
    p95 = [float(r["p95_util"]) for r in policy_rows]
    p99 = [float(r["p99_util"]) for r in policy_rows]
    series[name] = {
        "p95": p95,
        "p99": p99,
        "hotspot": crossing(nodes, p99),
        "broad": crossing(nodes, p95),
    }

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.8, 4.4),
                               gridspec_kw={"width_ratios": [1.35, 0.65]})

ax1.plot(nodes, series["managed"]["p95"], "o-", color="#777777", lw=2,
         label="managed current")
ax1.plot(nodes, series["fast"]["p95"], "o-", color="#2ca02c", lw=2.2,
         label="integrated fast")
ax1.plot(nodes, series["pivot"]["p95"], "o-", color="#006d2c", lw=2.2,
         label="integrated fast + PIVOT")
ax1.plot(nodes, series["full"]["p95"], "o-", color="#d98200", lw=2.2,
         label="integrated full (+ 24 h custody)")
ax1.axhline(25, color="#d62728", ls="--", lw=1.5,
            label="25% channel-health threshold")
ax1.axvline(499, color="#555", ls=":", lw=1.3)
ax1.text(515, 2.4, "today\n499 known\n~96 active/h", fontsize=8, color="#444")
ax1.set_xlabel("traffic-equivalent known nodes in the same RF footprint")
ax1.set_ylabel("modeled local channel utilization  %")
ax1.set_ylim(0, max(series["full"]["p95"]) * 1.08)
ax1.grid(alpha=0.25)
ax1.legend(fontsize=7.7, loc="upper left")
ax1.set_title("(a)  p95 local utilization: reliability has an airtime price",
              loc="left", fontsize=10)

labels = ["hotspot warning\n(p99 = 25%)", "broad pressure\n(p95 = 25%)"]
x = [0, 1]
width = 0.18
limits = {
    "managed": [series["managed"]["hotspot"], series["managed"]["broad"]],
    "fast": [series["fast"]["hotspot"], series["fast"]["broad"]],
    "pivot": [series["pivot"]["hotspot"], series["pivot"]["broad"]],
    "full": [series["full"]["hotspot"], series["full"]["broad"]],
}
styles = [
    ("managed", -1.5 * width, "#888888", "managed current"),
    ("fast", -0.5 * width, "#2ca02c", "integrated fast"),
    ("pivot", 0.5 * width, "#006d2c", "fast + PIVOT"),
    ("full", 1.5 * width, "#d98200", "integrated full"),
]
for key, offset, color, label in styles:
    positions = [value + offset for value in x]
    ax2.bar(positions, limits[key], width, color=color, label=label)
    for position, value in zip(positions, limits[key]):
        ax2.text(position, value + 20, f"{value:.0f}", ha="center",
                 fontsize=7.8, fontweight="bold", color=color)
ax2.set_xticks(x)
ax2.set_xticklabels(labels, fontsize=8.5)
ax2.set_ylabel("traffic-equivalent known nodes")
ax2.set_ylim(0, 1080)
ax2.grid(alpha=0.25, axis="y")
ax2.legend(fontsize=7.2, loc="upper left")
ax2.set_title("(b)  practical capacity threshold",
              loc="left", fontsize=10)

fig.suptitle("Integrated stack capacity: efficient by default, reliability on demand",
             fontsize=12, fontweight="bold", y=0.99)
fig.text(0.01, 0.005,
         "All mechanisms execute jointly: GradCor-R + fallback/rescue + retries; "
         "relay pressure or PIVOT backbone + BULK/STANDARD class caps + utilization setpoint; "
         "full mode adds 24 h custody. Production mix: 79.2% broadcast, 14.2% ACKed addressed, "
         "6.6% best-effort addressed; 387 packets/h p95; 3 seeds.",
         fontsize=7.4, color="#555")
fig.tight_layout(rect=(0, 0.04, 1, 0.94))
fig.savefig("fig_capacity.png", dpi=150, bbox_inches="tight")
print("wrote fig_capacity.png")
