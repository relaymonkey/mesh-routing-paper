"""Does the broadcast hop limit cost anything, on all six networks?

For each network (own calibration from multinet_meta.csv), floods from real
traceroute sources at real hours, at hop limit 3 / 7 / unlimited:
  coverage of online nodes, coverage of BFS-reachable online nodes,
  tx per flood, and how often the limit BINDS (frontier still alive when
  the hop limit cut it -- only those floods could benefit from removal).
"""
import csv
import random
from collections import defaultdict, deque

import sim_norway as S

NETWORKS = [
    ("norway", "data"),
    ("bay-area", "data_networks/bay-area"),
    ("florida", "data_networks/florida"),
    ("socal", "data_networks/socal"),
    ("meshtastic-pt", "data_networks/meshtastic-pt"),
    ("italia", "data_networks/italia"),
]
HOURS = 168
N_SAMPLES = 250
SEEDS = (1, 2)


def load_cal():
    cal = {}
    with open("multinet_meta.csv") as f:
        for r in csv.DictReader(f):
            cal[r["network"]] = dict(
                x0=float(r["x0"]), pmax=float(r["pmax"]), pmin=float(r["pmin"]),
                kobs=float(r["kobs"]), rev_p=float(r["rev_p"]))
    return cal


def bfs_cover(world, src):
    seen = {src}
    dq = deque([src])
    while dq:
        u = dq.popleft()
        for v in world.out.get(u, ()):
            if v in seen or not world.on(v):
                continue
            seen.add(v)
            if world.can_relay(v):
                dq.append(v)
    return seen


def flood_meas(world, src, hop_limit):
    """Flood that also reports whether the hop limit bound it."""
    tx = 0
    received = {src: 0}
    frontier = [src]
    hops_run = 0
    for hop in range(hop_limit):
        arrivals = defaultdict(list)
        for u in frontier:
            if hop > 0 and not world.can_relay(u):
                continue
            tx += 1
            for v in world.out.get(u, ()):
                if v in received:
                    continue
                if world.rx(u, v):
                    arrivals[v].append((world.snr_db[(u, v)], u))
        nxt = []
        for v, frames in arrivals.items():
            if len(frames) > 1 and world.rng.random() >= S.CAPTURE_P:
                continue
            received[v] = hop + 1
            nxt.append(v)
        frontier = nxt
        hops_run = hop + 1
        if not frontier:
            break
    bound = bool(frontier) and hops_run == hop_limit
    return tx, received, bound


def main():
    cal = load_cal()
    print(f"{'network':14} {'hl':>9} {'cover online':>13} {'cover reachable':>16} "
          f"{'tx/flood':>9} {'limit bound':>12}")
    for name, datadir in NETWORKS:
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
        for hl in (3, 7, 10**6):
            cov = [0, 0, 0]          # covered, online, reachable_covered
            reach_tot = 0
            txs = 0
            bind = 0
            nf = 0
            for seed in SEEDS:
                world = S.World(links, nodes, presence, HOURS, seed=seed, **cal[name])
                for src, hour in samples:
                    world.hour = hour
                    if not world.on(src):
                        continue
                    nf += 1
                    online = sum(1 for m in world.presence if world.on(m))
                    reach = bfs_cover(world, src)
                    reach_tot += len(reach)
                    tx, received, bound = flood_meas(world, src, hl)
                    cov[0] += len(received)
                    cov[1] += online
                    cov[2] += len(set(received) & reach)
                    txs += tx
                    bind += bound
            label = "unlim" if hl > 100 else str(hl)
            print(f"{name:14} {label:>9} {100*cov[0]/max(1,cov[1]):>12.1f}% "
                  f"{100*cov[2]/max(1,reach_tot):>15.1f}% {txs/max(1,nf):>9.1f} "
                  f"{100*bind/max(1,nf):>11.1f}%")
        print()


if __name__ == "__main__":
    main()
