"""Can delivery of broadcasts (!ffffffff) be improved simply?

Bottleneck decomposition first, then cheap interventions.

CEILING: BFS coverage -- what fraction of online nodes have ANY path from
the source this hour? (graph connectivity: physics, no protocol reaches
further)
BASELINE: single managed flood, hop limit 7, one tx per relay.

Interventions (all one-rule, firmware-plausible):
  SRC x2      source sends the broadcast twice (new packet ID, seconds
              apart): second flood re-rolls every link, union coverage.
  RELAY x2    every relay transmits its rebroadcast twice (two chances per
              edge per round, more same-round collisions included).
  ROUTER x2   only ROUTER/REPEATER/ROUTER_LATE relays transmit twice --
              targets the backbone where fan-out is largest.
Metrics: coverage of online nodes, coverage of REACHABLE online nodes
(distance to ceiling), tx per broadcast.
"""
import random
from collections import defaultdict, deque

import sim_norway as S

PARAMS = dict(x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
HOURS = 168
N_SAMPLES = 300
SEEDS = (1, 2, 3)


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


def flood_k(world, src, k_for, hop_limit=S.HOP_LIMIT):
    """Managed flood where each relay u transmits k_for(u) times."""
    tx = 0
    received = {src: 0}
    frontier = [src]
    for hop in range(hop_limit):
        arrivals = defaultdict(list)
        for u in frontier:
            if hop > 0 and not world.can_relay(u):
                continue
            for _ in range(k_for(u)):
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
        if not frontier:
            break
    return tx, received


def flood_echo(world, src, hop_limit=S.HOP_LIMIT):
    """Flood with GradCor-style silence-armed retransmit: a relay that hears
    no onward echo of its rebroadcast (none of the nodes that decoded its
    frame relays) transmits once more -- redundancy only at frontiers."""
    tx = 0
    received = {src: 0}
    frontier = [src]
    for hop in range(hop_limit):
        arrivals = defaultdict(list)          # v -> [(snr, u)]
        decoded_by = defaultdict(set)         # u -> {v that decoded u}
        def transmit(u):
            nonlocal tx
            tx += 1
            for v in world.out.get(u, ()):
                if v in received:
                    continue
                if world.rx(u, v):
                    arrivals[v].append((world.snr_db[(u, v)], u))
                    decoded_by[u].add(v)
        txers = [u for u in frontier if hop == 0 or world.can_relay(u)]
        for u in txers:
            transmit(u)
        nxt = []
        for v, frames in arrivals.items():
            if len(frames) > 1 and world.rng.random() >= S.CAPTURE_P:
                continue
            received[v] = hop + 1
            nxt.append(v)
        # echo check: retransmit once if nothing I reached went on to relay
        relayers = {v for v in nxt if world.can_relay(v)}
        for u in txers:
            if not (decoded_by[u] & relayers):
                transmit(u)
        for v, frames in arrivals.items():
            if v in received:
                continue
            if len(frames) > 1 and world.rng.random() >= S.CAPTURE_P:
                continue
            received[v] = hop + 1
            nxt.append(v)
        frontier = nxt
        if not frontier:
            break
    return tx, received


def role(nodes, n):
    return nodes.get(n, {}).get("role", "UNKNOWN")


def main():
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, HOURS)

    rng = random.Random(4242)
    cands = [t for t in trs if S.real(t["src"])]
    t0 = min(t["ts"] for t in trs)
    samples = [(t["src"], min(HOURS - 1, int((t["ts"] - t0) // 3600)))
               for t in rng.sample(cands, N_SAMPLES)]

    configs = {
        "baseline (1 tx per relay)": lambda u: 1,
        "SRC x2 (send broadcast twice)": None,          # special-cased below
        "RELAY x2 (every relay twice)": lambda u: 2,
        "ROUTER x2 (backbone relays twice)": None,      # built per-world below
        "ECHO (retransmit on silence only)": None,      # special-cased below
    }

    stats = {k: [0, 0, 0, 0] for k in configs}   # covered, online, reachable_covered, tx
    ceiling = [0, 0]
    n_floods = 0
    for seed in SEEDS:
        world = S.World(links, nodes, presence, HOURS, seed=seed, **PARAMS)
        router2 = lambda u: 2 if role(nodes, u).startswith(("ROUTER", "REPEATER")) else 1
        for src, hour in samples:
            world.hour = hour
            if not world.on(src):
                continue
            n_floods += 1
            online = sum(1 for m in world.presence if world.on(m))
            reach = bfs_cover(world, src)
            ceiling[0] += len(reach)
            ceiling[1] += online
            for name in configs:
                if name.startswith("SRC x2"):
                    tx1, r1 = flood_k(world, src, lambda u: 1)
                    tx2, r2 = flood_k(world, src, lambda u: 1)
                    tx, received = tx1 + tx2, {**r2, **r1}
                elif name.startswith("ROUTER x2"):
                    tx, received = flood_k(world, src, router2)
                elif name.startswith("ECHO"):
                    tx, received = flood_echo(world, src)
                else:
                    tx, received = flood_k(world, src, configs[name])
                st = stats[name]
                st[0] += len(received)
                st[1] += online
                st[2] += len(set(received) & reach)
                st[3] += tx
        # ceiling counted once per world/sample; stats too -- same loop

    print(f"floods simulated: {n_floods} (3 seeds x {N_SAMPLES} real sources/hours)")
    print(f"\nCEILING: BFS-reachable online nodes: {100*ceiling[0]/ceiling[1]:.1f}% "
          f"of online nodes  <- connectivity bound, per hour")
    print(f"\n{'config':36} {'cover online':>13} {'cover reachable':>16} {'tx/flood':>9}")
    for name, (cov, onl, covr, tx) in stats.items():
        print(f"{name:36} {100*cov/onl:>12.1f}% {100*covr/ceiling[0]:>15.1f}% "
              f"{tx/n_floods:>9.1f}")


if __name__ == "__main__":
    main()
