"""PIVOT: self-organizing relay backbone (local two-hop MPR heuristic).

Each node learns one-hop neighbours from traffic. On each broadcast hop,
candidates compute residual two-hop coverage not yet in the packet digest,
elect a minimal pivot set (mandatory relays first, then greedy completion),
and tie-break by bidirectional ETX, uptime, novelty and channel headroom.
Short leases plus utilization penalty load-balance recurring winners.
Non-pivots wait for a pivot echo; they relay only if residual stays uncovered.

Two digest modes:
  exact  ceiling: full neighbour-set in header (sim oracle)
  digest 64-bit bloom sketch (+ DIGEST_TX_OVERHEAD charged per tx)

Edge-case worlds: 101-node star, three-node triangle, overlapping clusters,
unique-leaf fanout, dense cliques/bridges, braid depth, Norway replay.
"""
import random
import statistics as st
import struct
import zlib
from collections import defaultdict

import sim_norway as S
from experiment_alltoall import BACKBONE, bfs_cover, flood_gen
from experiment_depth import BraidWorld
from experiment_pressure import DenseWorld, PressureFlood, StaticFlood

SLOTS = 3
BACKUP_SLOT = 3
CAPTURE_P = S.CAPTURE_P
LEASE_TTL = 40          # floods before lease expires
LEASE_BONUS = 0.35
UTIL_PENALTY = 2.5
PIVOT_PERSIST = 2       # pivot retransmits until onward echo
DIGEST_TX_OVERHEAD = 0.12   # fractional tx per hop for 8-byte sketch


# ---------------- digest ----------------
class ExactDigest:
    """Oracle ceiling: exact covered-node set."""

    def __init__(self):
        self.nodes = set()

    def add(self, node):
        self.nodes.add(node)

    def contains(self, node):
        return node in self.nodes

    def merge(self, other):
        if isinstance(other, ExactDigest):
            self.nodes |= other.nodes

    def copy(self):
        d = ExactDigest()
        d.nodes = set(self.nodes)
        return d

    @property
    def overhead(self):
        return 0.0


class BloomDigest:
    """Firmware-plausible coverage sketch: m bits, k hash functions.

    A single-hash 64-bit filter saturates once the covered set approaches a
    few dozen nodes (m/n < 1), so its false-positive rate explodes in dense
    or star neighbourhoods -- a covered-bit collision makes a pivot believe a
    still-uncovered node is already reached, and it under-relays. k=2 hashing
    lowers the FP rate at small n; the honest fix at large n is more bits,
    which we sweep (64 -> 256) to separate algorithmic gain from sketch cost.
    """

    SEEDS = (0x5049564F, 0x424C4F4D, 0x48415348, 0xC0FFEE01)

    def __init__(self, nbits=64, k=2):
        self.bits = 0
        self.nbits = nbits
        self.k = k

    def _idx(self, node):
        b = node.encode()
        for i in range(self.k):
            yield zlib.crc32(b, self.SEEDS[i]) % self.nbits

    def add(self, node):
        for i in self._idx(node):
            self.bits |= 1 << i

    def contains(self, node):
        return all(self.bits & (1 << i) for i in self._idx(node))

    def merge(self, other):
        if isinstance(other, BloomDigest):
            self.bits |= other.bits

    def copy(self):
        d = BloomDigest(self.nbits, self.k)
        d.bits = self.bits
        return d

    @property
    def overhead(self):
        # header cost scales with sketch size (8 B at 64 bits)
        return DIGEST_TX_OVERHEAD * (self.nbits / 64.0)


def bloom_factory(nbits=64, k=2):
    return lambda: BloomDigest(nbits, k)


# ---------------- per-node persistent state ----------------
class PivotState:
    def __init__(self):
        self.etx = {}           # (u,v) -> expected tx count (1/p)
        self.seen = {}          # (u,v) -> hear count
        self.uptime = defaultdict(float)
        self.novelty = defaultdict(lambda: 0.5)
        self.util = defaultdict(float)
        self.leases = {}        # (src, pivot) -> remaining floods
        self.churn = 0

    def observe_link(self, u, v, ok):
        key = (u, v)
        self.seen[key] = self.seen.get(key, 0) + 1
        old = self.etx.get(key, 2.0)
        est = 1.0 if ok else 3.0
        self.etx[key] = old + 0.2 * (est - old)

    def observe_uptime(self, node, on):
        self.uptime[node] = 0.95 * self.uptime[node] + 0.05 * (1.0 if on else 0.0)

    def observe_novelty(self, node, novel):
        old = self.novelty[node]
        self.novelty[node] = old + 0.2 * ((1.0 if novel else 0.0) - old)

    def set_util(self, node, u):
        self.util[node] = u

    def grant_lease(self, src, pivot):
        self.leases[(src, pivot)] = LEASE_TTL

    def lease_active(self, src, pivot):
        return self.leases.get((src, pivot), 0) > 0

    def decay_leases(self):
        dead = []
        for k, v in self.leases.items():
            if v <= 1:
                dead.append(k)
            else:
                self.leases[k] = v - 1
        for k in dead:
            del self.leases[k]


def bidir_etx(state, u, v):
    a = state.etx.get((u, v), 2.0)
    b = state.etx.get((v, u), 2.0)
    return 0.5 * (a + b)


def link_ok(state, world, u, v):
    p = getattr(world, "p", {}).get((u, v))
    if p is None:
        return world.rx(u, v)
    return p >= 0.35


def residual_two_hop(world, u, covered, relay_ok, holders=None):
    """Nodes newly coverable if u relays: 1-hop plus 2-hop via u."""
    holders = holders or {u}
    new = set()
    for v in world.out.get(u, ()):
        if not relay_ok(v) or not world.on(v):
            continue
        if not covered.contains(v):
            new.add(v)
        if v not in holders:
            continue
        for w in world.out.get(v, ()):
            if relay_ok(w) and world.on(w) and not covered.contains(w):
                new.add(w)
    return new


def pivot_score(world, state, u, src, residual, lease_active):
    if not residual:
        return -1e9
    etx = 1.0
    for v in world.out.get(u, ()):
        if v in residual or any(w in residual for w in world.out.get(v, ())):
            etx = min(etx, bidir_etx(state, u, v))
    etx = max(etx, 0.5)
    score = (len(residual) / etx
             + LEASE_BONUS * (1 if lease_active else 0)
             + 0.15 * state.uptime.get(u, 0.5)
             + 0.10 * state.novelty.get(u, 0.5)
             - UTIL_PENALTY * state.util.get(u, 0.0))
    return score


def elect_pivots(world, state, src, holders, covered, relay_ok):
    """Greedy pivot set among holders for uncovered two-hop nodes."""
    mandatory = set()
    all_residual = set()
    per = {}
    for u in holders:
        if not relay_ok(u):
            continue
        res = residual_two_hop(world, u, covered, relay_ok, holders)
        per[u] = res
        all_residual |= res

    uncovered = {w for w in all_residual if not covered.contains(w)}
    if not uncovered:
        return set(), per

    for w in uncovered:
        carriers = [u for u in holders
                    if w in per.get(u, set()) and relay_ok(u)]
        if len(carriers) == 1:
            mandatory.add(carriers[0])

    selected = set(mandatory)
    still = set(uncovered)
    for u in selected:
        still -= per.get(u, set())

    while still:
        best = None
        best_score = -1e9
        for u in holders:
            if u in selected or not relay_ok(u):
                continue
            gain = {w for w in per.get(u, set()) if w in still}
            if not gain:
                continue
            sc = pivot_score(world, state, u, src,
                             gain,
                             state.lease_active(src, u))
            if sc > best_score:
                best_score = sc
                best = u
        if best is None:
            break
        selected.add(best)
        still -= per.get(best, set())

    return selected, per


# ---------------- PIVOT flood ----------------
class PivotFlood:
    def __init__(self, digest_cls=BloomDigest, backup=True):
        self.digest_cls = digest_cls
        self.backup = backup
        self.state = PivotState()
        self.stats = defaultdict(float)

    def _relay_ok(self, world, relay_ok):
        return relay_ok or (lambda n: world.can_relay(n) and world.on(n))

    def flood(self, world, src, hop_limit=S.HOP_LIMIT, relay_ok=None):
        relay_ok = self._relay_ok(world, relay_ok)
        tx = 0.0
        txers = []
        received = {src: 0}
        digest = self.digest_cls()
        digest.add(src)
        frontier = [src]

        for hop in range(hop_limit):
            holders = [u for u in frontier if hop == 0 or relay_ok(u)]
            if not holders:
                break

            pivots, residual_map = elect_pivots(
                world, self.state, src, holders, digest, relay_ok)
            if hop == 0:
                pivots.add(src)
            else:
                pivots &= set(holders)

            # lease winners
            for u in pivots:
                self.state.grant_lease(src, u)

            copies = defaultdict(int)
            heard_relays = defaultdict(int)
            arrivals = defaultdict(list)
            decoded_by = defaultdict(set)
            pivot_echo = set()

            def transmit(u, slot, is_pivot):
                nonlocal tx
                tx += 1.0 + digest.overhead
                txers.append(u)
                if is_pivot:
                    self.stats["pivot_tx"] += 1
                else:
                    self.stats["backup_tx"] += 1
                for v in world.out.get(u, ()):
                    ok = world.rx(u, v)
                    self.state.observe_link(u, v, ok)
                    if not ok:
                        continue
                    copies[v] += 1
                    if v in holders:
                        heard_relays[v] += 1
                    if v not in received:
                        arrivals[v].append((slot, u))
                        decoded_by[u].add(v)

            fired = []
            for slot in range(SLOTS):
                if slot > 0:
                    break
                for u in holders:
                    if u not in pivots or u in fired:
                        continue
                    transmit(u, slot, True)
                    fired.append(u)

            # resolve collisions
            nxt = []
            for v, frames in arrivals.items():
                by_slot = defaultdict(list)
                for slot, u in frames:
                    by_slot[slot].append(u)
                first = min(by_slot)
                if (len(by_slot[first]) > 1
                        and world.rng.random() >= CAPTURE_P
                        and not any(s > first for s in by_slot)):
                    continue
                received[v] = hop + 1
                digest.add(v)
                nxt.append(v)
                for u in by_slot[first]:
                    if u in pivots:
                        pivot_echo.add(v)

            # pivot persistence: repeat until an onward relay is heard
            relayers = set(nxt)
            for u in list(fired):
                if u not in pivots:
                    continue
                tries = 1
                while tries < PIVOT_PERSIST and not (decoded_by[u] & relayers):
                    transmit(u, BACKUP_SLOT, True)
                    tries += 1
                    for v, frames in list(arrivals.items()):
                        if v not in received:
                            received[v] = hop + 1
                            digest.add(v)
                            nxt.append(v)
                            relayers.add(v)
                            pivot_echo.add(v)

            # backup: non-pivots if residual still uncovered
            if self.backup:
                for u in holders:
                    if u in pivots or u in fired or not relay_ok(u):
                        continue
                    res = residual_map.get(u, set())
                    need = [w for w in res
                            if w not in received and not digest.contains(w)]
                    if not need:
                        continue
                    if pivot_echo & set(res):
                        continue
                    transmit(u, BACKUP_SLOT, False)
                    if u not in fired:
                        fired.append(u)
                for v in list(arrivals):
                    if v not in received and v in arrivals:
                        received[v] = hop + 1
                        digest.add(v)
                        nxt.append(v)

            for n, k in copies.items():
                pass  # crowding observable from copies if needed
            for u in fired:
                novel = bool(decoded_by[u])
                self.state.observe_novelty(u, novel)
                if novel:
                    self.stats["novel_relays"] += 1

            self.stats["relay_rounds"] += 1
            self.stats["pivot_count"] += len(pivots)
            frontier = nxt
            if not frontier:
                break

        self.state.decay_leases()
        self.stats["floods"] += 1
        self.stats["tx"] += tx
        return tx, received, txers


# ---------------- synthetic worlds ----------------
class StarWorld:
    """Hub + N leaves; leaves only hear hub."""

    def __init__(self, n_leaves=100, seed=1):
        self.rng = random.Random(seed)
        self.center = "!00000001"
        self.leaves = [f"!{i+2:08x}" for i in range(n_leaves)]
        self.nodes = [self.center] + self.leaves
        self.out = defaultdict(list)
        self.p = {}
        self.snr_db = {}
        for leaf in self.leaves:
            for u, v in ((self.center, leaf), (leaf, self.center)):
                self.out[u].append(v)
                self.p[(u, v)] = 0.95
                self.snr_db[(u, v)] = 10.0

    def on(self, n):
        return True

    def can_relay(self, n):
        return True

    def rx(self, u, v):
        return self.rng.random() < self.p.get((u, v), 0)


class TriangleWorld:
    """Three-node triangle with tunable link qualities."""

    def __init__(self, p_ab, p_bc, p_ac, seed=1):
        self.rng = random.Random(seed)
        self.nodes = ["!a", "!b", "!c"]
        self.out = defaultdict(list)
        self.p = {}
        self.snr_db = {}
        for u, v, p in (("!a", "!b", p_ab), ("!b", "!a", p_ab),
                        ("!b", "!c", p_bc), ("!c", "!b", p_bc),
                        ("!a", "!c", p_ac), ("!c", "!a", p_ac)):
            self.out[u].append(v)
            self.p[(u, v)] = p
            self.snr_db[(u, v)] = 8.0
        self.src = "!a"

    def on(self, n):
        return True

    def can_relay(self, n):
        return True

    def rx(self, u, v):
        return self.rng.random() < self.p.get((u, v), 0)


class OverlapClusters:
    """Two 5-node cliques sharing two bridge nodes."""

    def __init__(self, seed=1):
        self.rng = random.Random(seed)
        self.out = defaultdict(list)
        self.p = {}
        self.snr_db = {}
        c1 = [f"!1{i:06x}" for i in range(5)]
        c2 = [f"!2{i:06x}" for i in range(5)]
        shared = c1[3], c1[4]
        c2[0], c2[1] = shared
        self.nodes = list(dict.fromkeys(c1 + c2))
        for group in (c1, c2):
            for a in group:
                for b in group:
                    if a != b:
                        self.out[a].append(b)
                        self.p[(a, b)] = 0.9
                        self.snr_db[(a, b)] = 8.0
        self.src = c1[0]

    def on(self, n):
        return True

    def can_relay(self, n):
        return True

    def rx(self, u, v):
        return self.rng.random() < self.p.get((u, v), 0)


class UniqueLeafFanout:
    """Source with N leaves each reachable only via a dedicated relay."""

    def __init__(self, n=8, seed=1):
        self.rng = random.Random(seed)
        self.src = "!00000001"
        self.relays = [f"!r{i:06x}" for i in range(n)]
        self.leaves = [f"!l{i:06x}" for i in range(n)]
        self.nodes = [self.src] + self.relays + self.leaves
        self.out = defaultdict(list)
        self.p = {}
        self.snr_db = {}
        for r in self.relays:
            self._link(self.src, r, 0.9)
        for r, leaf in zip(self.relays, self.leaves):
            self._link(r, leaf, 0.9)

    def _link(self, u, v, p):
        for a, b in ((u, v), (v, u)):
            self.out[a].append(b)
            self.p[(a, b)] = p
            self.snr_db[(a, b)] = 8.0

    def on(self, n):
        return True

    def can_relay(self, n):
        return True

    def rx(self, u, v):
        return self.rng.random() < self.p.get((u, v), 0)


# ---------------- runners ----------------
def _flood(proto, world, src, **kw):
    """Normalize 2-tuple (Static/Pressure) and 3-tuple (Pivot) returns."""
    out = proto.flood(world, src, **kw)
    return out[0], out[1]


def run_star(label, factory, packets=50):
    world = StarWorld(100)
    proto = factory()
    tx = 0
    for src in [world.center, world.leaves[0]]:
        t, rcv = _flood(proto, world, src, hop_limit=3)
        tx += t
        n = len(world.leaves) + 1
        print(f"  {label:28} src={src[-4:]}  "
              f"cover {100*len(rcv)/n:5.1f}%  tx {t:5.1f}")
    return tx


def run_triangle(label, factory, packets=100):
    results = []
    for p_ac in (0.95, 0.15):
        world = TriangleWorld(0.95, 0.95, p_ac)
        proto = factory()
        dlv = tx = 0
        for _ in range(packets):
            t, rcv = _flood(proto, world, world.src, hop_limit=3)
            dlv += "!c" in rcv
            tx += t
        tag = "strong AC" if p_ac >= 0.5 else "weak AC"
        print(f"  {label:28} {tag:9}  "
              f"dlv {100*dlv/packets:5.1f}%  tx/pkt {tx/packets:4.1f}")
        results.append(tx / packets)
    return results


def run_world_cover(world, factory, src, packets, hop_limit, n_nodes=None):
    proto = factory()
    for _ in range(10):
        _flood(proto, world, src, hop_limit=hop_limit)
    cov = tx = 0
    denom = n_nodes or len(world.nodes)
    for _ in range(packets):
        t, rcv = _flood(proto, world, src, hop_limit=hop_limit)
        cov += len(rcv)
        tx += t
    return 100 * cov / (packets * denom), tx / packets


def run_norway(factory, label, n_samples=200, seeds=(1, 2)):
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, 168)
    rng = random.Random(4242)
    cands = [t for t in trs if S.real(t["src"])]
    t0 = min(t["ts"] for t in trs)
    samples = [(t["src"], min(167, int((t["ts"] - t0) // 3600)))
               for t in rng.sample(cands, n_samples)]
    covr = reach_tot = txs = nf = 0
    for seed in seeds:
        world = S.World(links, nodes, presence, 168, seed=seed,
                        x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
        proto = factory()
        for src, hour in samples:
            world.hour = hour
            if not world.on(src):
                continue
            nf += 1
            reach = bfs_cover(world, src)
            reach_tot += len(reach)
            t, received = _flood(proto, world, src,
                                 relay_ok=lambda n: world.on(n))
            covr += len(set(received) & reach)
            txs += t
    cov = 100 * covr / max(1, reach_tot)
    tpf = txs / max(1, nf)
    print(f"  {label:34} cover-reachable {cov:5.1f}%   tx/pkt {tpf:6.1f}")
    return cov, tpf


def main():
    factories = [
        (lambda: StaticFlood(1, 1, 1), "managed flood (cancel@1)"),
        (PressureFlood, "relay pressure"),
        (lambda: PivotFlood(ExactDigest), "PIVOT exact"),
        (lambda: PivotFlood(bloom_factory(64, 2)), "PIVOT 64-bit"),
        (lambda: PivotFlood(bloom_factory(256, 3)), "PIVOT 256-bit"),
    ]

    print("== STAR 101 nodes: centre tx=1, leaf tx≈2 ==")
    for f, label in factories:
        run_star(label, f)

    print("\n== TRIANGLE: direct suppresses pivot; weak AC uses pivot ==")
    for f, label in factories:
        run_triangle(label, f)

    print("\n== OVERLAP CLUSTERS / UNIQUE LEAF FANOUT ==")
    for world, name in ((OverlapClusters(), "overlap"), (UniqueLeafFanout(), "fanout")):
        for f, label in factories[-2:]:
            cov, tpf = run_world_cover(world, f, world.src, 100, 5)
            print(f"  {label:28} {name:8}  cover {cov:5.1f}%  tx/pkt {tpf:5.1f}")

    print("\n== DENSE cliques (suppression regime) ==")
    for f, label in factories:
        w = DenseWorld(0.9, 0.8, 11)
        cov, tpf = run_world_cover(w, f, w.src, 200, 10, len(w.nodes))
        print(f"  {label:34} coverage {cov:5.1f}%   tx/pkt {tpf:6.1f}")

    print("\n== BRAID d=50 (persistence regime) ==")
    for f, label in factories:
        w = BraidWorld(50, 2, 0.7, 11)
        dlv = tx = 0
        proto = f()
        for _ in range(200):
            t, rcv = _flood(proto, w, w.src, hop_limit=10**6)
            dlv += w.dst in rcv
            tx += t
        print(f"  {label:34} delivery {100*dlv/200:5.1f}%   tx/pkt {tx/200:6.1f}")

    print("\n== NORWAY replay ==")
    for f, label in factories:
        run_norway(f, label)


if __name__ == "__main__":
    main()
