"""PIVOT validation across six production networks + role/MeshCore comparators.

Compares managed flood, relay pressure, configured-role backbone,
MeshCore-style repeaters, PIVOT-exact and PIVOT-64-bit.
Writes pivot_multinet.csv and pivot_regime.csv (from experiment_pivot main).
"""
import csv
import random

import sim_norway as S
from experiment_alltoall import BACKBONE, bfs_cover, flood_gen
from experiment_pivot import ExactDigest, PivotFlood, bloom_factory
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


def run_network(name, datadir, cal, nodes_meta):
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

    def role(n):
        return nodes.get(n, {}).get("role", "UNKNOWN")

    factories = [
        (lambda: StaticFlood(1, 1, 1), "managed flood"),
        (PressureFlood, "relay pressure"),
        (lambda: flood_gen_wrapper(nodes, "backbone k=1"), "role backbone"),
        (lambda: flood_gen_wrapper(nodes, "meshcore k=2"), "meshcore repeaters"),
        (lambda: PivotFlood(ExactDigest), "PIVOT exact"),
        (lambda: PivotFlood(bloom_factory(64, 2)), "PIVOT 64-bit"),
        (lambda: PivotFlood(bloom_factory(256, 3)), "PIVOT 256-bit"),
    ]

    rows = []
    for factory, label in factories:
        covr = reach_tot = txs = nf = 0.0
        pivot_num = pivot_den = 0.0
        for seed in SEEDS:
            world = S.World(links, nodes, presence, HOURS, seed=seed, **cal)
            proto = factory()
            seed_pivot = seed_tx = 0.0
            for i, (src, hour) in enumerate(samples):
                world.hour = hour
                if not world.on(src):
                    continue
                relay = lambda m, w=world: w.on(m)
                if label.startswith("role") or label.startswith("meshcore"):
                    if i < WARMUP:
                        proto(world, src, hour)
                        continue
                elif i < WARMUP:
                    if hasattr(proto, "flood"):
                        proto.flood(world, src, relay_ok=relay)
                    continue
                nf += 1
                reach = bfs_cover(world, src)
                reach_tot += len(reach)
                if hasattr(proto, "flood"):
                    before = (proto.stats["pivot_tx"], proto.stats["tx"]) if isinstance(
                        proto, PivotFlood) else (0, 0)
                    result = proto.flood(world, src, relay_ok=relay)
                    t, received = result[0], result[1]
                    if isinstance(proto, PivotFlood):
                        seed_pivot += proto.stats["pivot_tx"] - before[0]
                        seed_tx += proto.stats["tx"] - before[1]
                else:
                    t, received = proto(world, src, hour)
                covr += len(set(received) & reach)
                txs += t
            pivot_num += seed_pivot
            pivot_den += seed_tx
        row = dict(
            network=name,
            proto=label,
            cover_reachable=round(100 * covr / max(1, reach_tot), 1),
            tx_per_flood=round(txs / max(1, nf), 1),
            pivot_tx_frac=round(100 * pivot_num / max(1, pivot_den), 1),
        )
        rows.append(row)
        print(f"[{name}] {label:20} {row['cover_reachable']:>6.1f}%  "
              f"{row['tx_per_flood']:>7.1f} tx  pivot {row['pivot_tx_frac']:>4.1f}%")
    return rows


class FloodGenRunner:
    """Stateful wrapper around flood_gen for role/MeshCore strategies."""

    def __init__(self, nodes, strategy):
        self.nodes = nodes
        self.strategy = strategy

    def __call__(self, world, src, hour):
        role = lambda n: self.nodes.get(n, {}).get("role", "UNKNOWN")
        if self.strategy == "backbone k=1":
            pred = lambda u: role(u) in BACKBONE
            k = lambda u: 1
        else:
            pred = lambda u: role(u) in BACKBONE
            k = lambda u: 2
        full = lambda u: world.can_relay(u) and pred(u)
        return flood_gen(world, src, full, k, hop_limit=S.HOP_LIMIT)


def flood_gen_wrapper(nodes, strategy):
    return FloodGenRunner(nodes, strategy)


def main():
    cal = load_cal()
    all_rows = []
    for name, datadir in NETWORKS:
        all_rows.extend(run_network(name, datadir, cal[name], {}))
        print()
    with open("pivot_multinet.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    print("wrote pivot_multinet.csv")


if __name__ == "__main__":
    main()
