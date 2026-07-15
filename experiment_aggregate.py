"""Payload aggregation: attack offered LOAD, not per-packet relay cost.

PIVOT, relay pressure and the price curve all reduce transmissions *per
flooded packet*. None reduces the *number* of packets. But 79% of Norway's
traffic is periodic BULK broadcast -- position, telemetry, NodeInfo -- which
is aggregatable: a hub can collect its neighbours' reports over a short
window and flood ONE packet carrying G reports instead of G separate floods.

Two capacity metrics diverge, and that divergence is the point:

  * TOTAL airtime (duty-cycle / whole-channel limit): the aggregate is
    larger, so only the fixed preamble/header amortizes -- a modest win.
  * HOTSPOT load (the p99 node that actually caps node count, per
    experiment_capacity.py): a hub relaying G separate floods instead
    floods once, so the busiest node's transmit count drops sharply. This
    is the star case -- one node, a hundred neighbours -- made quantitative.

LATENCY is the price: the aggregation window W is added to every report.

We model LoRa time-on-air (Semtech ToA), account airtime PER NODE so the
hotspot is visible, sweep batch size G, and confirm information coverage is
preserved. Flood cost reuses sim_norway.flood; synthetic star/dense worlds
come from experiment_pivot.
"""
import csv
import math
import random
import statistics as st
from collections import defaultdict

import sim_norway as S
from experiment_alltoall import bfs_cover
from experiment_capacity import transmitting_nodes
from experiment_pivot import DenseWorld, StarWorld

PARAMS = dict(x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
HOURS = 24
SEEDS = (1, 2, 3)
REPORT_BYTES = 20
AGG_HEADER_BYTES = 8
HUB_LINK_MIN = 0.35
GRID = (1, 5, 10, 20, 40)


def toa_seconds(payload_bytes, sf=11, bw=250000, n_pre=16, cr=1, de=1):
    """Semtech LoRa time-on-air. Meshtastic LongFast-like defaults."""
    ts = (2 ** sf) / bw
    t_preamble = (n_pre + 4.25) * ts
    num = 8 * payload_bytes - 4 * sf + 28 + 16
    den = 4 * (sf - 2 * de)
    payload_sym = 8 + max(math.ceil(num / den) * (cr + 4), 0)
    return t_preamble + payload_sym * ts


T_REPORT = toa_seconds(REPORT_BYTES)


def agg_toa(batch):
    return toa_seconds(AGG_HEADER_BYTES + batch * REPORT_BYTES)


def best_hub(world, node, online_set):
    """Highest-degree online neighbour over a reliable link, or self."""
    best, best_deg = node, len(world.out.get(node, ()))
    for v in world.out.get(node, ()):
        if v not in online_set or world.p.get((node, v), 0) < HUB_LINK_MIN:
            continue
        deg = len(world.out.get(v, ()))
        if deg > best_deg:
            best, best_deg = v, deg
    return best


def window(world, online, G, air):
    """One report-window. Charges per-node airtime into dict `air`.
    Returns (cov_num, cov_den) for information coverage."""
    online_set = set(online)
    cache = {}

    def flood_of(src):
        if src not in cache:
            reach = bfs_cover(world, src)
            _, _, _, received = S.flood(world, src, "\x00none")
            txers = list(transmitting_nodes(world, received))
            cache[src] = (txers, set(received) & reach, reach)
        return cache[src]

    cov_num = cov_den = 0.0

    if G == 1:
        for src in online:
            txers, recv, reach = flood_of(src)
            for t in txers:
                air[t] += T_REPORT
            cov_num += len(recv)
            cov_den += len(reach)
        return cov_num, cov_den

    hub_reports = defaultdict(list)
    for src in online:
        hub = best_hub(world, src, online_set)
        if hub == src or world.rx(src, hub):
            hub_reports[hub].append(src)
            if hub != src:
                air[src] += T_REPORT           # one local send to the hub
        else:
            txers, recv, reach = flood_of(src)  # no hub -> flood itself
            for t in txers:
                air[t] += T_REPORT
            cov_num += len(recv)
            cov_den += len(reach)

    for hub, srcs in hub_reports.items():
        txers, recv, reach = flood_of(hub)
        for i in range(0, len(srcs), G):
            batch = srcs[i:i + G]
            for t in txers:
                air[t] += agg_toa(len(batch))
            for _ in batch:
                cov_num += len(recv)
                cov_den += len(reach)
    return cov_num, cov_den


def run_norway(links, nodes, presence, G, seed):
    world = S.World(links, nodes, presence, 168, seed=seed, **PARAMS)
    air = defaultdict(float)
    cov_num = cov_den = 0.0
    for step in range(HOURS):
        world.hour = ((seed - 1) * 56 + step) % 168
        online = [n for n in presence if world.on(n)]
        if len(online) < 2:
            continue
        cn, cd = window(world, online, G, air)
        cov_num += cn
        cov_den += cd
    return summarize(air, cov_num, cov_den)


def run_world(world, G, seed):
    world.rng = random.Random(seed)
    air = defaultdict(float)
    cn, cd = window(world, list(world.nodes), G, air)
    return summarize(air, cn, cd)


def summarize(air, cov_num, cov_den):
    vals = list(air.values()) or [0.0]
    return dict(
        total_airtime=sum(vals),
        hotspot_airtime=max(vals),
        coverage=100 * cov_num / max(1, cov_den),
    )


def sweep(label, runner, seeds):
    print(f"\n== {label} ==")
    print(f"{'G':>3} {'total air':>11} {'hotspot air':>12} {'cover%':>8} "
          f"{'total drop':>11} {'hotspot drop':>13}")
    base = None
    rows = []
    for G in GRID:
        runs = [runner(G, s) for s in seeds]
        agg = {k: st.mean(r[k] for r in runs) for k in runs[0]}
        if base is None:
            base = agg
        td = base["total_airtime"] / max(1e-9, agg["total_airtime"])
        hd = base["hotspot_airtime"] / max(1e-9, agg["hotspot_airtime"])
        tag = "  (baseline)" if G == 1 else ""
        print(f"{G:>3} {agg['total_airtime']:>10.0f}s {agg['hotspot_airtime']:>11.1f}s "
              f"{agg['coverage']:>7.1f}% {td:>10.2f}x {hd:>12.2f}x{tag}")
        rows.append(dict(world=label, G=G,
                         total_airtime=round(agg["total_airtime"], 1),
                         hotspot_airtime=round(agg["hotspot_airtime"], 2),
                         coverage=round(agg["coverage"], 1),
                         total_drop=round(td, 2), hotspot_drop=round(hd, 2)))
    return rows


def main():
    global REPORT_BYTES, T_REPORT
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, 168)

    print(f"LoRa ToA: {REPORT_BYTES}B = {1000*T_REPORT:.0f} ms; "
          f"aggregate(10) = {1000*agg_toa(10):.0f} ms; "
          f"aggregate(40) = {1000*agg_toa(40):.0f} ms")

    rows = []
    rows += sweep("STAR (1 hub + 100 leaves, 20B reports)",
                  lambda G, s: run_world(StarWorld(100, seed=s), G, s), SEEDS)

    # ceiling depends on payload/preamble ratio: shrink the report (delta /
    # compressed encoding) and the same aggregation buys far more.
    REPORT_BYTES, T_REPORT = 4, toa_seconds(4)
    rows += sweep("STAR (1 hub + 100 leaves, 4B delta reports)",
                  lambda G, s: run_world(StarWorld(100, seed=s), G, s), SEEDS)
    REPORT_BYTES, T_REPORT = 20, toa_seconds(20)

    rows += sweep("DENSE (3x20 cliques + bridges)",
                  lambda G, s: run_world(DenseWorld(0.9, 0.8, s), G, s), SEEDS)
    rows += sweep("NORWAY replay (sparse organic)",
                  lambda G, s: run_norway(links, nodes, presence, G, s), SEEDS)

    with open("aggregate_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\nwrote aggregate_results.csv")
    print("Coverage is of INFORMATION (a receiver of the aggregate gets every "
          "report in it). Hotspot = busiest node's airtime; it caps node count.")


if __name__ == "__main__":
    main()
