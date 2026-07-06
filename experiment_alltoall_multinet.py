"""Is the all-to-all price curve (coverage ~ log airtime, family-invariant)
a Norway artifact or a general property? Reduced strategy grid on all six
networks, per-network calibration.
"""
import csv
import math
import random
from collections import deque

import sim_norway as S
from experiment_alltoall import bfs_cover, flood_gen

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
BACKBONE = ("ROUTER", "ROUTER_LATE", "REPEATER")


def load_cal():
    cal = {}
    with open("multinet_meta.csv") as f:
        for r in csv.DictReader(f):
            cal[r["network"]] = dict(
                x0=float(r["x0"]), pmax=float(r["pmax"]), pmin=float(r["pmin"]),
                kobs=float(r["kobs"]), rev_p=float(r["rev_p"]))
    return cal


def run_network(name, datadir, cal):
    S.DATA = datadir
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, HOURS)

    def role(n):
        return nodes.get(n, {}).get("role", "UNKNOWN")

    strategies = [
        ("all k=1", "blanket", lambda u: True, lambda u: 1, 1),
        ("all k=2", "blanket", lambda u: True, lambda u: 2, 1),
        ("all k=3", "blanket", lambda u: True, lambda u: 3, 1),
        ("backbone k=1", "meshcore", lambda u: role(u) in BACKBONE, lambda u: 1, 1),
        ("backbone k=2", "meshcore", lambda u: role(u) in BACKBONE, lambda u: 2, 1),
        ("bb+base k=2", "meshcore+", lambda u: role(u) in BACKBONE or role(u) == "CLIENT_BASE", lambda u: 2, 1),
        ("src x2", "src-repeat", lambda u: True, lambda u: 1, 2),
        ("router x2", "targeted", lambda u: True, lambda u: 2 if role(u) in BACKBONE else 1, 1),
    ]

    rng = random.Random(4242)
    cands = [t for t in trs if S.real(t["src"])]
    t0 = min(t["ts"] for t in trs)
    n = min(N_SAMPLES, len(cands))
    samples = [(t["src"], min(HOURS - 1, int((t["ts"] - t0) // 3600)))
               for t in rng.sample(cands, n)]

    rows = []
    for label, family, pred, k_for, s in strategies:
        covr = reach_tot = txs = nf = 0
        for seed in SEEDS:
            world = S.World(links, nodes, presence, HOURS, seed=seed, **cal)
            full_pred = lambda u: world.can_relay(u) and pred(u)
            for src, hour in samples:
                world.hour = hour
                if not world.on(src):
                    continue
                nf += 1
                reach = bfs_cover(world, src)
                reach_tot += len(reach)
                got = set()
                tx = 0
                for _ in range(s):
                    t_, received = flood_gen(world, src, full_pred, k_for, False)
                    tx += t_
                    got |= set(received)
                covr += len(got & reach)
                txs += tx
        rows.append(dict(network=name, strategy=label, family=family,
                         cover_reachable=round(100 * covr / max(1, reach_tot), 1),
                         tx_per_flood=round(txs / max(1, nf), 2)))
        print(f"[{name}] {label:14} {rows[-1]['cover_reachable']:>6.1f}%  "
              f"{rows[-1]['tx_per_flood']:>7.1f} tx")
    return rows


def fit_slope(rows):
    """Least-squares coverage ~ a + b*log2(tx); returns b and R^2."""
    pts = [(math.log2(r["tx_per_flood"]), r["cover_reachable"]) for r in rows
           if r["tx_per_flood"] > 0]
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    b = sxy / sxx if sxx else 0
    a = my - b * mx
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in pts)
    ss_tot = sum((y - my) ** 2 for _, y in pts)
    r2 = 1 - ss_res / ss_tot if ss_tot else 1
    return b, r2


if __name__ == "__main__":
    cal = load_cal()
    all_rows = []
    for name, datadir in NETWORKS:
        all_rows.extend(run_network(name, datadir, cal[name]))
        print()
    with open("alltoall_multinet.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    print("network         slope (pts/doubling)   R^2 of log-linear fit")
    for name, _ in NETWORKS:
        rows = [r for r in all_rows if r["network"] == name]
        b, r2 = fit_slope(rows)
        print(f"{name:14} {b:>12.1f} {r2:>22.2f}")
    print("\nwrote alltoall_multinet.csv")
