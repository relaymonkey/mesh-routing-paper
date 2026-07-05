"""Does holding a failed packet and retrying in later hours close the gap
to 99%?

Part 1: TEMPORAL REACHABILITY -- for attempts with no forward path this
hour, how soon does a path exist? (Both endpoints must be online again,
since delivery to an offline node is meaningless.)

Part 2: CUSTODY REPLAY -- RescueGrad + k in-hour retries, and on failure
the packet stays queued and is retried each subsequent hour (when both
endpoints are online) up to H hours. Delivery is credited to the original
packet; all transmissions are charged.
"""
import random
from collections import deque

import sim_norway as S
from experiment_target99 import RescueGrad, Retry, reachable, PARAMS

SEEDS = tuple(range(1, 11))
HOURS = 168


def temporal_reachability():
    horizon = 24
    buckets = {0: 0}
    never = 0
    total_unreach = 0
    for seed in SEEDS:
        world = S.World(*_DATA, HOURS, seed=seed, **PARAMS)
        rng = random.Random(seed + 999)
        pairs = S.pick_pairs(_TRS, _PRESENCE, HOURS, rng, S.PAIRS)
        for hour in range(HOURS):
            world.hour = hour
            for (s, d) in pairs:
                if not (world.on(s) and world.on(d)):
                    continue
                if reachable(world, s, d):
                    buckets[0] += 1
                    continue
                total_unreach += 1
                for dh in range(1, horizon + 1):
                    if hour + dh >= HOURS:
                        never += 1
                        break
                    world.hour = hour + dh
                    ok = (world.on(s) and world.on(d) and reachable(world, s, d))
                    world.hour = hour
                    if ok:
                        buckets[dh] = buckets.get(dh, 0) + 1
                        break
                else:
                    never += 1
    tot = sum(buckets.values()) + never
    print(f"reachable immediately: {buckets[0]}/{tot} ({100*buckets[0]/tot:.1f}%)")
    cum = buckets[0]
    for dh in sorted(k for k in buckets if k > 0):
        cum += buckets[dh]
        print(f"  becomes reachable after {dh:>2} h: +{buckets[dh]:>4}  (cumulative {100*cum/tot:.1f}%)")
    print(f"  never within {24} h / window end: {never} ({100*never/tot:.1f}%)")


def custody(k_inhour, max_hold_h):
    agg = [0, 0, 0]                # delivered, sent(originals), tx
    for seed in SEEDS:
        world = S.World(*_DATA, HOURS, seed=seed, **PARAMS)
        rng = random.Random(seed + 999)
        pairs = S.pick_pairs(_TRS, _PRESENCE, HOURS, rng, S.PAIRS)
        proto = Retry(RescueGrad(), k_inhour)
        pending = deque()          # (src, dst, born_hour)
        for hour in range(HOURS):
            world.hour = hour
            # retry held packets first
            for _ in range(len(pending)):
                s, d, born = pending.popleft()
                if hour - born > max_hold_h:
                    continue                        # expired -> failure
                if not (world.on(s) and world.on(d)):
                    pending.append((s, d, born))
                    continue
                ok, tx = proto.send(world, s, d)
                agg[2] += tx
                if ok:
                    agg[0] += 1
                else:
                    pending.append((s, d, born))
            # new traffic
            for (s, d) in pairs:
                if not (world.on(s) and world.on(d)):
                    continue
                agg[1] += 1
                ok, tx = proto.send(world, s, d)
                agg[2] += tx
                if ok:
                    agg[0] += 1
                else:
                    pending.append((s, d, hour))
    dlv, snt, tx = agg
    print(f"custody: k={k_inhour} in-hour, hold {max_hold_h:>2} h   "
          f"delivery {100*dlv/snt:6.1f}%   tx/pkt {tx/snt:6.1f}   tx/dlv {tx/max(1,dlv):6.1f}")


if __name__ == "__main__":
    nodes = S.load_nodes()
    _TRS = S.load_traceroutes()
    links = S.links_from_traceroutes(_TRS)
    _PRESENCE, _ = S.load_presence(_TRS, HOURS)
    _DATA = (links, nodes, _PRESENCE)
    # share module data with experiment_target99 helpers
    import experiment_target99 as T
    T._DATA, T._TRS, T._PRESENCE = _DATA, _TRS, _PRESENCE

    print("== 1. temporal reachability of this-hour-unreachable attempts ==")
    temporal_reachability()

    print("\n== 2. custody replay (store-and-forward on failure) ==")
    for k, hold in ((2, 3), (2, 6), (3, 12), (3, 24)):
        custody(k, hold)
