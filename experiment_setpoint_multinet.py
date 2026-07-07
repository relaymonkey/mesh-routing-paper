"""Setpoint (cap-filling) controller on all six production networks.

Same utilization-tracked harness as experiment_headroom.py (hourly EWMA of
heard-transmissions, utilization-coupled interference), per-network
calibration, offered load 20 broadcasts/hour for 24 hours. On sparse
networks utilization never approaches the cap, so the expectation is that
the controller self-climbs to the top of its rung ladder and takes the
best coverage the (abundant) headroom buys; the validation is that it
matches or beats every static everywhere while never breaching the cap.
Writes setpoint_multinet.csv.
"""
import csv
import random
from collections import defaultdict

import sim_norway as S
from experiment_alltoall import bfs_cover
from experiment_headroom import (HeadroomFlood, SetpointFlood, StaticFlood,
                                 T_TX, HOUR, U_CAP)

NETWORKS = [
    ("norway", "data"),
    ("bay-area", "data_networks/bay-area"),
    ("florida", "data_networks/florida"),
    ("socal", "data_networks/socal"),
    ("meshtastic-pt", "data_networks/meshtastic-pt"),
    ("italia", "data_networks/italia"),
]
LAM = 20
HOURS = 24


def load_cal():
    cal = {}
    with open("multinet_meta.csv") as f:
        for r in csv.DictReader(f):
            cal[r["network"]] = dict(
                x0=float(r["x0"]), pmax=float(r["pmax"]), pmin=float(r["pmin"]),
                kobs=float(r["kobs"]), rev_p=float(r["rev_p"]))
    return cal


def run_network(name, datadir, cal, policy_factory, label, seed=1):
    S.DATA = datadir
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, 168)
    world = S.World(links, nodes, presence, 168, seed=seed, **cal)
    proto = policy_factory()

    util = defaultdict(float)
    base_rx = world.rx

    def rx(u_, v):
        if not base_rx(u_, v):
            return False
        return world.rng.random() >= min(0.6, 0.8 * util[v])

    world.rx = rx
    rng = random.Random(seed + 77)

    covr = reach_tot = txs = nf = 0
    for h in range(HOURS):
        world.hour = h % 168
        online = [n for n in world.presence if world.on(n)]
        heard = defaultdict(int)
        for _ in range(LAM):
            src = rng.choice(online)
            reach = bfs_cover(world, src)
            if len(reach) < 2:
                continue
            nf += 1
            reach_tot += len(reach)
            t, received = proto.flood(world, src,
                                      relay_ok=lambda m: world.on(m))
            covr += len(set(received) & reach)
            txs += t
            for n in received:
                for v in world.out.get(n, ()):
                    heard[v] += 1
        for n in online:
            u_now = heard[n] * T_TX / HOUR
            util[n] = util[n] + 0.4 * (u_now - util[n])
        if hasattr(proto, "util"):
            proto.util = dict(util)

    us = [util[n] for n in util] or [0.0]
    mean_u = sum(us) / len(us)
    over = sum(1 for x in us if x > U_CAP) / len(us)
    row = dict(network=name, proto=label,
               cover_reachable=round(100 * covr / max(1, reach_tot), 1),
               tx_per_flood=round(txs / max(1, nf), 1),
               mean_util=round(100 * mean_u, 1),
               over_cap=round(100 * over, 1))
    print(f"[{name}] {label:24} {row['cover_reachable']:>6.1f}%  "
          f"{row['tx_per_flood']:>7.1f} tx  util {row['mean_util']:>4.1f}%  "
          f">cap {row['over_cap']:>4.1f}%")
    return row


if __name__ == "__main__":
    cal = load_cal()
    rows = []
    for name, datadir in NETWORKS:
        rows.append(run_network(name, datadir, cal[name],
                                lambda: StaticFlood(1, None, 1), "plain flood"))
        rows.append(run_network(name, datadir, cal[name],
                                lambda: StaticFlood(1, None, 3), "persist R=3"))
        rows.append(run_network(name, datadir, cal[name],
                                SetpointFlood, "SETPOINT"))
        print()
    with open("setpoint_multinet.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote setpoint_multinet.csv")
