"""Relay pressure on all six production networks, per-network calibration.

Same protocols as experiment_pressure.py (plain flood / shipped-style
cancel@1 / blanket persist R=3 / pressure), same slotted machinery, run on
each network's real topology, presence and fitted link model. Coverage of
BFS-reachable online nodes and tx per flood; every node may relay (roles
not consulted -- pressure is the role system under test).
Writes pressure_multinet.csv.
"""
import csv
import random

import sim_norway as S
from experiment_alltoall import bfs_cover
from experiment_pressure import PressureFlood, StaticFlood

NETWORKS = [
    ("norway", "data"),
    ("bay-area", "data_networks/bay-area"),
    ("florida", "data_networks/florida"),
    ("socal", "data_networks/socal"),
    ("meshtastic-pt", "data_networks/meshtastic-pt"),
    ("italia", "data_networks/italia"),
]
HOURS = 168
N_SAMPLES = 200
SEEDS = (1, 2)
WARMUP = 30


def load_cal():
    cal = {}
    with open("multinet_meta.csv") as f:
        for r in csv.DictReader(f):
            cal[r["network"]] = dict(
                x0=float(r["x0"]), pmax=float(r["pmax"]), pmin=float(r["pmin"]),
                kobs=float(r["kobs"]), rev_p=float(r["rev_p"]))
    return cal


FACTORIES = [
    (lambda: StaticFlood(1, None, 1), "plain flood"),
    (lambda: StaticFlood(1, 1, 1), "cancel@1"),
    (lambda: StaticFlood(1, None, 3), "persist R=3"),
    (PressureFlood, "pressure"),
]


def run_network(name, datadir, cal):
    S.DATA = datadir
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, HOURS)
    rng = random.Random(4242)
    cands = [t for t in trs if S.real(t["src"])]
    t0 = min(t["ts"] for t in trs)
    n = min(N_SAMPLES, len(cands))
    samples = [(t["src"], min(HOURS - 1, int((t["ts"] - t0) // 3600)))
               for t in rng.sample(cands, n)]

    rows = []
    for factory, label in FACTORIES:
        covr = reach_tot = txs = nf = 0
        for seed in SEEDS:
            world = S.World(links, nodes, presence, HOURS, seed=seed, **cal)
            proto = factory()
            for i, (src, hour) in enumerate(samples):
                world.hour = hour
                if not world.on(src):
                    continue
                relay = lambda m: world.on(m)
                if i < WARMUP:
                    proto.flood(world, src, relay_ok=relay)
                    continue
                nf += 1
                reach = bfs_cover(world, src)
                reach_tot += len(reach)
                t, received = proto.flood(world, src, relay_ok=relay)
                covr += len(set(received) & reach)
                txs += t
        cov = 100 * covr / max(1, reach_tot)
        tpf = txs / max(1, nf)
        rows.append(dict(network=name, proto=label,
                         cover_reachable=round(cov, 1), tx_per_flood=round(tpf, 1)))
        print(f"[{name}] {label:14} {cov:>6.1f}%  {tpf:>7.1f} tx")
    return rows


if __name__ == "__main__":
    cal = load_cal()
    all_rows = []
    for name, datadir in NETWORKS:
        all_rows.extend(run_network(name, datadir, cal[name]))
        print()
    with open("pressure_multinet.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    print("wrote pressure_multinet.csv")
