"""Does temporal repetition (periodic beacons) substitute for per-flood
redundancy?

Union coverage of m successive baseline floods from the same source (its
first m online hours), Norway replay. If the growth follows the same
log-linear price curve as the within-hour strategies of
experiment_alltoall.py, then periodic traffic already climbs the curve by
repeating -- and per-flood redundancy for it would pay twice.
"""
import random

import sim_norway as S
from experiment_alltoall import bfs_cover, flood_gen

PARAMS = dict(x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
HOURS = 168
SEEDS = (1, 2, 3)


def main():
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, HOURS)

    rng = random.Random(4242)
    srcs = list({t["src"] for t in trs if S.real(t["src"])})
    rng.shuffle(srcs)
    srcs = [s for s in srcs if len(presence.get(s, ())) >= 12][:120]

    print(f"{'repeats m':>9} {'union coverage of union-reachable':>34} {'tx total':>9}")
    for m in (1, 2, 3, 6, 12):
        covr = reach_tot = txs = n = 0
        for seed in SEEDS:
            world = S.World(links, nodes, presence, HOURS, seed=seed, **PARAMS)
            for src in srcs:
                hours = sorted(presence[src])[:m]
                got, reach = set(), set()
                tx = 0
                for h in hours:
                    world.hour = h
                    reach |= bfs_cover(world, src)
                    t_, received = flood_gen(world, src, world.can_relay,
                                             lambda u: 1, False)
                    tx += t_
                    got |= set(received)
                covr += len(got & reach)
                reach_tot += len(reach)
                txs += tx
                n += 1
        print(f"{m:>9} {100*covr/reach_tot:>33.1f}% {txs/n:>9.1f}")


if __name__ == "__main__":
    main()
