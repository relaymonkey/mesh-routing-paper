"""Traffic-equivalent node limit on the Norway production topology.

This is intentionally a linear scaling question, not a synthetic graph-growth
claim. The Norway topology and per-packet propagation stay fixed while offered
traffic is multiplied. A scale of 2 means twice today's statistically identical
nodes, each producing the same traffic, in the same RF footprint.

Production anchor, study week 2026-06-27 11:00 UTC to 2026-07-04 11:00 UTC:
  499 known nodes; 96.1 mean active sources/hour
  51,892 canonical (source_node_id, packet_id) packets
  309 packets/hour mean; 387 packets/hour p95; 79.2% broadcast

The replay uses the p95 hour and conservatively sends every packet as a
hop-limit-7 managed flood. Each transmission costs 0.5 s, matching the
headroom experiments. Local utilization is the airtime a node transmits or can
hear on observed links. Reception suffers the same utilization-coupled loss as
experiment_headroom.py. Results are therefore a capacity warning, not a
universal Meshtastic node limit.
"""
import csv
import random
import statistics
from collections import defaultdict

import sim_norway as S
from experiment_alltoall import bfs_cover

KNOWN_NODES = 499
MEAN_ACTIVE_SOURCES = 96.1
P95_PACKETS_PER_HOUR = 387
BROADCAST_SHARE = 0.792

T_TX = 0.5
HOUR_SECONDS = 3600.0
U_CAP = 0.25
EWMA_ALPHA = 0.4
HOURS = 24
WARMUP_HOURS = 6
SEEDS = (1, 2, 3)
SCALES = (0.5, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0)
PARAMS = dict(x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)


def percentile(values, q):
    ordered = sorted(values)
    return ordered[int(q * (len(ordered) - 1))]


def transmitting_nodes(world, received):
    """Nodes that emitted in sim_norway.flood for this received map."""
    for node, depth in received.items():
        if depth >= S.HOP_LIMIT:
            continue
        if depth == 0 or world.can_relay(node):
            yield node


def run_scale(links, nodes, presence, scale, seed):
    world = S.World(links, nodes, presence, 168, seed=seed, **PARAMS)
    rng = random.Random(seed + 77)
    util = defaultdict(float)
    base_rx = world.rx

    def rx(u, v):
        if not base_rx(u, v):
            return False
        return world.rng.random() >= min(0.6, 0.8 * util[v])

    world.rx = rx
    node_hours = []
    covered = reachable = transmissions = floods = 0
    offered = round(P95_PACKETS_PER_HOUR * scale)
    hour_offset = (seed - 1) * 56

    for step in range(HOURS):
        world.hour = (hour_offset + step) % 168
        online = [n for n in presence if world.on(n)]
        heard = defaultdict(int)
        measure = step >= WARMUP_HOURS

        for _ in range(offered):
            src = rng.choice(online)
            reach = bfs_cover(world, src)
            if len(reach) < 2:
                continue
            _, tx, _, received = S.flood(world, src, "\x00none")

            for u in transmitting_nodes(world, received):
                heard[u] += 1
                for v in world.out.get(u, ()):
                    if world.on(v):
                        heard[v] += 1

            if measure:
                floods += 1
                transmissions += tx
                covered += len(set(received) & reach)
                reachable += len(reach)

        for n in online:
            current = heard[n] * T_TX / HOUR_SECONDS
            util[n] += EWMA_ALPHA * (current - util[n])
        if measure:
            node_hours.extend(util[n] for n in online)

    return {
        "mean_util": 100 * statistics.mean(node_hours),
        "p95_util": 100 * percentile(node_hours, 0.95),
        "p99_util": 100 * percentile(node_hours, 0.99),
        "coverage": 100 * covered / max(1, reachable),
        "tx_per_flood": transmissions / max(1, floods),
    }


def crossing(rows, key, target=25.0):
    for left, right in zip(rows, rows[1:]):
        a, b = left[key], right[key]
        if a <= target < b:
            fraction = (target - a) / (b - a)
            return left["scale"] + fraction * (right["scale"] - left["scale"])
    return None


def main():
    nodes = S.load_nodes()
    traceroutes = S.load_traceroutes()
    links = S.links_from_traceroutes(traceroutes)
    presence, _ = S.load_presence(traceroutes, 168)
    rows = []

    print(f"{'scale':>5} {'equiv nodes':>11} {'active/h':>8} {'packets/h':>9} "
          f"{'mean u':>7} {'p95 u':>7} {'p99 u':>7} {'coverage':>9}")
    for scale in SCALES:
        runs = [run_scale(links, nodes, presence, scale, seed) for seed in SEEDS]
        row = {
            "scale": scale,
            "equiv_nodes": round(KNOWN_NODES * scale),
            "equiv_active_per_hour": round(MEAN_ACTIVE_SOURCES * scale),
            "packets_per_hour": round(P95_PACKETS_PER_HOUR * scale),
        }
        for key in runs[0]:
            row[key] = round(statistics.mean(run[key] for run in runs), 2)
        rows.append(row)
        print(f"{scale:5.2f} {row['equiv_nodes']:11d} "
              f"{row['equiv_active_per_hour']:8d} {row['packets_per_hour']:9d} "
              f"{row['mean_util']:6.1f}% {row['p95_util']:6.1f}% "
              f"{row['p99_util']:6.1f}% {row['coverage']:8.1f}%")

    with open("capacity_scale.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    hotspot_scale = crossing(rows, "p99_util")
    broad_scale = crossing(rows, "p95_util")
    print("\n25% utilization crossings (interpolated):")
    print(f"  hotspot warning (p99 node-hour): {hotspot_scale:.2f}x = "
          f"~{KNOWN_NODES * hotspot_scale:.0f} known / "
          f"{MEAN_ACTIVE_SOURCES * hotspot_scale:.0f} active per hour")
    print(f"  broad pressure (p95 node-hour):  {broad_scale:.2f}x = "
          f"~{KNOWN_NODES * broad_scale:.0f} known / "
          f"{MEAN_ACTIVE_SOURCES * broad_scale:.0f} active per hour")
    print("wrote capacity_scale.csv")


if __name__ == "__main__":
    main()
