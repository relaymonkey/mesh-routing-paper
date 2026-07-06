"""Deliver one message to ALL reachable nodes: strategy-space sweep.

Start from the objective (not from "broadcast"): maximize coverage of
BFS-reachable online nodes per transmission. Decompose every known scheme
into three orthogonal variables and sweep the grid:

  WHO relays      all relay-capable nodes (Meshtastic)
                  backbone only: ROUTER/ROUTER_LATE/REPEATER (MeshCore)
                  backbone + CLIENT_BASE (fixed stations as infrastructure)
  PERSISTENCE k   each relay transmits its rebroadcast k times
  SRC REPEATS s   the source re-floods s times (new packet ID each time,
                  re-rolling every link)
  GATING          k=2 only for nodes that decoded exactly ONE copy (local
                  sparsity signal), else k=1

Writes alltoall_results.csv for fig_alltoall.py (Pareto view).
"""
import csv
import random
from collections import defaultdict, deque

import sim_norway as S

PARAMS = dict(x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
HOURS = 168
N_SAMPLES = 300
SEEDS = (1, 2, 3)

BACKBONE = ("ROUTER", "ROUTER_LATE", "REPEATER")


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


def flood_gen(world, src, relay_pred, k_for, gate_single=False,
              hop_limit=S.HOP_LIMIT):
    """Generalized flood. relay_pred(u): may u relay at all;
    k_for(u): transmissions per relay; gate_single: nodes that decoded
    exactly one copy transmit twice regardless of k_for."""
    tx = 0
    received = {src: 0}
    copies = {src: 99}                     # decode-count at first reception
    frontier = [src]
    for hop in range(hop_limit):
        arrivals = defaultdict(list)
        for u in frontier:
            if hop > 0 and not relay_pred(u):
                continue
            k = k_for(u)
            if gate_single and copies.get(u, 99) == 1:
                k = max(k, 2)
            for _ in range(k):
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
            copies[v] = len(frames)
            nxt.append(v)
        frontier = nxt
        if not frontier:
            break
    return tx, received


def main():
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, HOURS)

    def role(n):
        return nodes.get(n, {}).get("role", "UNKNOWN")

    def relay_all(u):
        return True                        # can_relay handled by world links below

    def relay_backbone(u):
        return role(u) in BACKBONE

    def relay_backbone_base(u):
        return role(u) in BACKBONE or role(u) == "CLIENT_BASE"

    # (label, family, relay_pred, k_for, gate, src_repeats)
    strategies = []
    for k in (1, 2, 3, 4):
        strategies.append((f"all k={k}", "blanket", relay_all, lambda u, k=k: k, False, 1))
    for k in (1, 2, 3):
        strategies.append((f"backbone k={k}", "meshcore", relay_backbone, lambda u, k=k: k, False, 1))
        strategies.append((f"backbone+base k={k}", "meshcore+", relay_backbone_base, lambda u, k=k: k, False, 1))
    for s in (2, 3):
        strategies.append((f"src x{s}", "src-repeat", relay_all, lambda u: 1, False, s))
    strategies.append(("router x2", "targeted", relay_all,
                       lambda u: 2 if role(u) in BACKBONE else 1, False, 1))
    strategies.append(("gated (1-copy -> x2)", "targeted", relay_all, lambda u: 1, True, 1))
    strategies.append(("router x2 + src x2", "combo", relay_all,
                       lambda u: 2 if role(u) in BACKBONE else 1, False, 2))
    strategies.append(("gated + src x2", "combo", relay_all, lambda u: 1, True, 2))

    rng = random.Random(4242)
    cands = [t for t in trs if S.real(t["src"])]
    t0 = min(t["ts"] for t in trs)
    samples = [(t["src"], min(HOURS - 1, int((t["ts"] - t0) // 3600)))
               for t in rng.sample(cands, N_SAMPLES)]

    rows = []
    print(f"{'strategy':26} {'family':10} {'cover reachable':>16} {'tx/flood':>9}")
    for label, family, pred, k_for, gate, s in strategies:
        covr = reach_tot = txs = nf = 0
        for seed in SEEDS:
            world = S.World(links, nodes, presence, HOURS, seed=seed, **PARAMS)
            # world.can_relay covers CLIENT_MUTE; strategy pred layers on top
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
                    t_, received = flood_gen(world, src, full_pred, k_for, gate)
                    tx += t_
                    got |= set(received)
                covr += len(got & reach)
                txs += tx
        cov_pct = 100 * covr / max(1, reach_tot)
        tpf = txs / max(1, nf)
        rows.append(dict(strategy=label, family=family,
                         cover_reachable=round(cov_pct, 1), tx_per_flood=round(tpf, 1)))
        print(f"{label:26} {family:10} {cov_pct:>15.1f}% {tpf:>9.1f}")

    with open("alltoall_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\nwrote alltoall_results.csv")


if __name__ == "__main__":
    main()
