"""Does the FLOOD hop limit matter (for broadcasts and for GradCor's
internal floods)?

1. BROADCAST SIDE: coverage (fraction of online nodes reached) and tx cost
   of a single flood at hop limit 3 / 7 / unlimited, from real traffic
   sources at real hours. Dedup bounds any flood (each node relays once),
   so "unlimited" is finite -- the question is how much reach the limit
   actually costs on a real topology.
2. UNICAST SIDE: GradCor-R delivery when its planting/fallback floods run
   at hop limit 3 / 7 / unlimited (does deeper planting help descent?).
"""
import random

import sim_norway as S

PARAMS = dict(x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
SEEDS = tuple(range(1, 11))
HOURS = 168


def broadcast_sweep(nodes, trs, links, presence):
    rng = random.Random(4242)
    cands = [t for t in trs if S.real(t["src"])]
    t0 = min(t["ts"] for t in trs)
    samples = [(t["src"], min(HOURS - 1, int((t["ts"] - t0) // 3600)))
               for t in rng.sample(cands, 300)]
    print(f"{'hop limit':>10} {'coverage of online nodes':>26} {'tx per flood':>14}")
    for hl in (3, 7, 10**6):
        cov = [0, 0]
        txs = 0
        n = 0
        for seed in SEEDS[:3]:
            world = S.World(links, nodes, presence, HOURS, seed=seed, **PARAMS)
            for src, hour in samples:
                world.hour = hour
                if not world.on(src):
                    continue
                online = sum(1 for m in world.presence if world.on(m))
                _, tx, _, received = S.flood(world, src, "\x00none", hop_limit=hl)
                cov[0] += len(received)
                cov[1] += online
                txs += tx
                n += 1
        label = "unlimited" if hl > 100 else str(hl)
        print(f"{label:>10} {100*cov[0]/cov[1]:>25.1f}% {txs/n:>14.1f}")


def gradcor_plant_depth(nodes, trs, links, presence):
    print(f"\n{'plant/fallback hop limit':>26} {'delivery':>9} {'tx/dlv':>8}")
    orig_flood = S.flood
    for hl in (3, 7, 10**6):
        # flood()'s hop_limit default binds at def time; patch the module
        # reference so plant()'s internal call sees the override too
        S.flood = (lambda hl: lambda world, src, dst, hop_limit=None, collect_parents=False:
                   orig_flood(world, src, dst, hl, collect_parents))(hl)
        try:
            agg = [0, 0, 0]
            for seed in SEEDS:
                world = S.World(links, nodes, presence, HOURS, seed=seed, **PARAMS)
                rng = random.Random(seed + 999)
                pairs = S.pick_pairs(trs, presence, HOURS, rng, S.PAIRS)
                proto = S.ReactiveGradProto()
                for hour in range(HOURS):
                    world.hour = hour
                    for (s, d) in pairs:
                        if not (world.on(s) and world.on(d)):
                            continue
                        ok, tx = proto.send(world, s, d)
                        agg[0] += ok
                        agg[1] += 1
                        agg[2] += tx
        finally:
            S.flood = orig_flood
        label = "unlimited" if hl > 100 else str(hl)
        print(f"{label:>26} {100*agg[0]/agg[1]:>8.1f}% {agg[2]/max(1,agg[0]):>8.1f}")


if __name__ == "__main__":
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, HOURS)
    print("== 1. broadcast flood: hop limit vs coverage and cost ==")
    broadcast_sweep(nodes, trs, links, presence)
    print("\n== 2. GradCor-R: does deeper planting/fallback flooding help? ==")
    gradcor_plant_depth(nodes, trs, links, presence)
