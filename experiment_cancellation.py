"""Does Managed Flood Routing's overhear-cancellation change the picture?

The replay's baseline flood lets every relay-capable node rebroadcast once.
Real Meshtastic nodes wait in an SNR-weighted contention window and CANCEL
their queued rebroadcast if they overhear another node relay the packet first
(ROUTER/REPEATER relay regardless; ROUTER_LATE defers but still relays).

This experiment swaps in a cancellation-aware flood — same link samples,
same collision/capture rule, same everything else — and re-runs the
five-protocol head-to-head, so the only delta is cancellation. It measures
the bias disclosed in the paper's threat #4: how much cheaper does flooding
get, and does delivery move?
"""
import random
from collections import defaultdict

import sim_norway as S


def flood_cancel(world, src, dst, hop_limit=S.HOP_LIMIT, collect_parents=False):
    """Round-based flood with Managed Flood Routing overhear-cancellation.

    Within a round, transmitters fire in contention order: ROUTER first
    (priority window), then others worst-SNR-first (distant nodes fire
    early), ROUTER_LATE last. A non-router transmitter cancels if an earlier
    transmitter this round already delivered the packet to it.
    """
    tx = 0
    received = {src: 0}
    parents = {src: None}
    frontier = [(src, 0.0)]              # (node, rx snr_db it first heard at)
    for hop in range(hop_limit):
        def role(n):
            return world.nodes.get(n, {}).get("role", "UNKNOWN")

        routers, lates, others = [], [], []
        for f in frontier:
            r = role(f[0])
            (routers if r == "ROUTER" else lates if r == "ROUTER_LATE" else others).append(f)
        world.rng.shuffle(routers)
        world.rng.shuffle(lates)
        # worse SNR -> smaller contention window -> fires earlier (+ jitter)
        others.sort(key=lambda f: f[1] + world.rng.uniform(-2.0, 2.0))
        order = routers + others + lates

        frontier_set = {f[0] for f in frontier}
        overheard = set()
        arrivals = defaultdict(list)     # v -> [(snr, u)]
        for u, _ in order:
            if hop > 0 and not world.can_relay(u):
                continue
            if u in overheard and role(u) not in ("ROUTER", "ROUTER_LATE"):
                continue                 # cancelled: someone we hear relayed first
            tx += 1
            for v in world.out.get(u, ()):
                if world.rx(u, v):
                    if v in frontier_set:
                        overheard.add(v)
                    if v not in received:
                        arrivals[v].append((world.snr_db[(u, v)], u))
        nxt = []
        for v, frames in arrivals.items():
            if len(frames) > 1 and world.rng.random() >= S.CAPTURE_P:
                continue
            snr, u = max(frames)
            received[v] = hop + 1
            parents[v] = u
            nxt.append((v, snr))
        frontier = nxt
        if not frontier:
            break
    return (dst in received), tx, (parents if collect_parents else None), received


def head_to_head(use_cancel):
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, 168)
    saved = S.flood
    if use_cancel:
        S.flood = flood_cancel
    try:
        agg = defaultdict(lambda: [0, 0, 0])
        for seed in range(1, 11):
            world = S.World(links, nodes, presence, 168, 8, 0.8, 0.25, 10, 0.0, seed)
            rng = random.Random(seed + 999)
            pairs = S.pick_pairs(trs, presence, 168, rng, S.PAIRS)
            protos = {"FLOOD": None, "PATH": S.PathProto(),
                      "NEXTHOP": S.NextHopProto(),
                      "GRADCOR": S.GradProto(), "GRADCOR-R": S.ReactiveGradProto()}
            for hour in range(168):
                world.hour = hour
                protos["GRADCOR"].age_all()
                protos["GRADCOR-R"].age_all()
                for (s, d) in pairs:
                    if not (world.on(s) and world.on(d)):
                        continue
                    for name, proto in protos.items():
                        if name == "FLOOD":
                            ok, tx, _, _ = S.flood(world, s, d)
                        else:
                            ok, tx = proto.send(world, s, d)
                        a = agg[name]
                        a[0] += ok
                        a[1] += 1
                        a[2] += tx
        return agg
    finally:
        S.flood = saved


if __name__ == "__main__":
    for label, cancel in (("baseline (no cancellation)", False),
                          ("with overhear-cancellation", True)):
        agg = head_to_head(cancel)
        print(f"\n== {label} ==")
        for name, (dlv, snt, tx) in agg.items():
            print(f"  {name:10} {100*dlv/snt:6.1f}%  tx/pkt {tx/snt:6.1f}  "
                  f"tx/dlv {tx/max(1,dlv):7.1f}")
