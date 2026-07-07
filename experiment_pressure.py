"""Relay pressure: can one self-calibrating scalar replace roles?

Hypothesis: the right flood policy is regime-dependent (sparse meshes need
persistence, dense meshes need suppression, bridges need priority), and the
discriminating signal is measurable locally for free: how many duplicate
copies of each packet a node decodes (c, neighbourhood redundancy).

Mechanism (no roles, no configuration, no control traffic):
  c_est   EWMA of copies-per-packet decoded (duplicates included)
  P       relay pressure = clamp((c_target - c_est)/c_target + 0.5, 0.05, 1)
  policy  P high  -> transmit in the early contention slot, never cancel,
                     persist up to R=3 until an onward echo is heard
          P mid   -> middle slot, cancel after 2 overheard relays, R=2
          P low   -> late slot, cancel after 1 overheard relay, R=1
A node in a crowded neighbourhood (c >> target) fades toward silence; a
bridge that rarely hears duplicates promotes itself toward router-like
behaviour. State: one float per node.

Three worlds, three regimes, same rule:
  NORWAY  sparse organic replay (must not lose coverage to the baseline)
  DENSE   three 20-node cliques joined by two single bridges, slotted
          contention with same-slot collisions (suppression must win;
          the test is whether pressure finds the bridges)
  BRAID   d=50 w=2 p=0.7 (persistence must win; from experiment_depth)
Static comparators per world: plain flood, shipped-style cancel@1,
blanket persist R=3.
"""
import random
import statistics as st
from collections import defaultdict, deque

import sim_norway as S
from experiment_depth import BraidWorld
from experiment_alltoall import bfs_cover

SLOTS = 3
CAPTURE_P = S.CAPTURE_P


# ---------------- the mechanism ----------------
class PressureFlood:
    """v3: crowding + novelty.

    c_est[u]  EWMA of copies-per-packet decoded (inbound redundancy:
              "how covered am I without doing anything?")
    nov[u]    EWMA of "my last relay produced at least one FIRST-COPY
              receiver" (outbound utility: "does my transmission create
              coverage that would not otherwise exist?"). Observable over
              the air because a first-copy receiver relays (or acks) at
              least once, while dup receivers stay silent under dedup.

    pressure = max(crowding term, novelty term): a node in a crowded
    neighbourhood fades to silence UNLESS its relays keep reaching someone
    new -- which is exactly a bridge. No roles, no probes, no config."""

    def __init__(self, c_target=2.0, alpha=0.15, nov_alpha=0.25):
        self.c_target = c_target
        self.alpha = alpha
        self.nov_alpha = nov_alpha
        self.c_est = {}
        self.nov = {}

    def pressure(self, n):
        c = self.c_est.get(n, self.c_target)     # unknown -> neutral
        crowd = max(0.05, min(1.0, (self.c_target - c) / self.c_target + 0.5))
        return max(crowd, self.nov.get(n, 0.5))

    def _policy(self, n):
        p = self.pressure(n)
        if p >= 0.7:
            return 0, None                       # slot, cancel_at
        if p >= 0.35:
            return 1, 2
        return 2, 1

    def persist_R(self, n):
        p = self.pressure(n)
        return 3 if p >= 0.7 else 2 if p >= 0.35 else 1

    def _observe(self, n, copies):
        old = self.c_est.get(n, self.c_target)
        self.c_est[n] = old + self.alpha * (copies - old)

    def _observe_novelty(self, u, novel):
        old = self.nov.get(u, 0.5)
        self.nov[u] = old + self.nov_alpha * ((1.0 if novel else 0.0) - old)

    def flood(self, world, src, hop_limit=S.HOP_LIMIT, relay_ok=None):
        """Slotted, pressure-driven flood. Returns (tx, received)."""
        relay_ok = relay_ok or (lambda n: True)
        tx = 0
        received = {src: 0}
        frontier = [src]
        for hop in range(hop_limit):
            copies = defaultdict(int)            # node -> frames decoded this round
            heard_relays = defaultdict(int)      # transmitter -> relays overheard
            arrivals = defaultdict(list)         # new receiver -> [(slot, u)]
            decoded_by = defaultdict(set)
            txers = [u for u in frontier if hop == 0 or relay_ok(u)]

            def transmit(u, slot):
                nonlocal tx
                tx += 1
                for v in world.out.get(u, ()):
                    if not world.rx(u, v):
                        continue
                    copies[v] += 1
                    if v in txers:
                        heard_relays[v] += 1
                    if v not in received:
                        arrivals[v].append((slot, u))
                        decoded_by[u].add(v)

            # slot pass with cancellation
            fired = []
            for slot in range(SLOTS):
                for u in txers:
                    s, cancel_at = self._policy(u)
                    if s != slot or u in fired:
                        continue
                    if cancel_at is not None and heard_relays[u] >= cancel_at:
                        continue
                    transmit(u, slot)
                    fired.append(u)

            # resolve same-slot collisions per receiver
            nxt = []
            for v, frames in arrivals.items():
                by_slot = defaultdict(list)
                for slot, u in frames:
                    by_slot[slot].append(u)
                first = min(by_slot)
                if len(by_slot[first]) > 1 and world.rng.random() >= CAPTURE_P:
                    # collided and lost; later-slot frames still deliver
                    later = [s_ for s_ in by_slot if s_ > first]
                    if not later:
                        continue
                received[v] = hop + 1
                nxt.append(v)

            # persistence: unechoed transmitters with R>1 retransmit
            relayers = set(nxt)
            for u in fired:
                R = self.persist_R(u)
                tries = 1
                while tries < R and not (decoded_by[u] & relayers):
                    transmit(u, SLOTS)           # late, collision-free slot
                    tries += 1
                    for v in list(arrivals):
                        if v not in received:
                            received[v] = hop + 1
                            nxt.append(v)
                            relayers.add(v)

            for n, k in copies.items():
                self._observe(n, k)
            # novelty: did u's transmission create any first-copy receiver?
            # (decoded_by[u] only ever contains nodes not yet in received
            # at decode time, i.e. first copies)
            for u in fired:
                self._observe_novelty(u, bool(decoded_by[u]))
            frontier = nxt
            if not frontier:
                break
        return tx, received


# ---------------- static comparators (same slotted machinery) ----------------
class StaticFlood(PressureFlood):
    """Fixed policy for every node: (slot, cancel_at, R)."""

    def __init__(self, slot, cancel_at, R):
        super().__init__()
        self.fixed = (slot, cancel_at)
        self.R = R

    def _policy(self, n):
        return self.fixed

    def persist_R(self, n):
        return self.R

    def _observe(self, n, copies):
        pass

    def _observe_novelty(self, u, novel):
        pass


# ---------------- dense world ----------------
class DenseWorld:
    """Three 20-node cliques chained by two single-link bridges."""

    def __init__(self, p_in, p_bridge, seed):
        self.rng = random.Random(seed)
        self.out = defaultdict(list)
        self.p = {}
        self.snr_db = {}
        def name(c, i):
            return f"!{c:02x}{i:02x}0000"
        self.nodes = []
        for c in range(3):
            members = [name(c, i) for i in range(20)]
            self.nodes += members
            for a in members:
                for b in members:
                    if a != b:
                        self.out[a].append(b)
                        self.p[(a, b)] = p_in
                        self.snr_db[(a, b)] = 0.0
        for c in range(2):
            a, b = name(c, 19), name(c + 1, 0)   # bridge endpoints
            for u, v in ((a, b), (b, a)):
                self.out[u].append(v)
                self.p[(u, v)] = p_bridge
                self.snr_db[(u, v)] = 0.0
        self.src = name(0, 0)

    def on(self, n):
        return True

    def can_relay(self, n):
        return True

    def rx(self, u, v):
        pr = self.p.get((u, v))
        return pr is not None and self.rng.random() < pr


# ---------------- runners ----------------
def run_dense(proto_factory, label, packets=300, warmup=30):
    world = DenseWorld(0.9, 0.8, seed=11)
    proto = proto_factory()
    for _ in range(warmup):
        proto.flood(world, world.src, hop_limit=10)
    cov = tx = 0
    for _ in range(packets):
        t, received = proto.flood(world, world.src, hop_limit=10)
        cov += len(received)
        tx += t
    print(f"  {label:34} coverage {100*cov/(packets*len(world.nodes)):5.1f}%   "
          f"tx/pkt {tx/packets:6.1f}")
    return proto


def run_braid(proto_factory, label, packets=300, warmup=30):
    world = BraidWorld(50, 2, 0.7, seed=11)
    proto = proto_factory()
    for _ in range(warmup):
        proto.flood(world, world.src, hop_limit=10**6)
    dlv = tx = 0
    for _ in range(packets):
        t, received = proto.flood(world, world.src, hop_limit=10**6)
        dlv += world.dst in received
        tx += t
    print(f"  {label:34} delivery {100*dlv/packets:5.1f}%   tx/pkt {tx/packets:6.1f}")


def run_norway(proto_factory, label, n_samples=200, seeds=(1, 2)):
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
        proto = proto_factory()
        for src, hour in samples:
            world.hour = hour
            if not world.on(src):
                continue
            nf += 1
            reach = bfs_cover(world, src)
            reach_tot += len(reach)
            # pressure replaces roles: every online node may relay
            t, received = proto.flood(world, src,
                                      relay_ok=lambda n: world.on(n))
            covr += len(set(received) & reach)
            txs += t
    print(f"  {label:34} cover-reachable {100*covr/reach_tot:5.1f}%   "
          f"tx/pkt {txs/nf:6.1f}")


if __name__ == "__main__":
    factories = [
        (lambda: StaticFlood(1, None, 1), "static: plain flood"),
        (lambda: StaticFlood(1, 1, 1), "static: cancel@1 (shipped-style)"),
        (lambda: StaticFlood(1, None, 3), "static: blanket persist R=3"),
        (PressureFlood, "PRESSURE (self-calibrating)"),
    ]

    print("== DENSE: 3 cliques x 20, two single bridges (suppression regime) ==")
    protos = {}
    for f, label in factories:
        protos[label] = run_dense(f, label)
    pf = protos["PRESSURE (self-calibrating)"]
    ps = sorted(pf.pressure(n) for n in DenseWorld(0.9, 0.8, 1).nodes)
    high = [n for n in DenseWorld(0.9, 0.8, 1).nodes if pf.pressure(n) >= 0.7]
    print(f"  learned pressure: median {st.median(ps):.2f}, "
          f"nodes at P>=0.7: {len(high)} -> {sorted(high)}")

    print("\n== BRAID d=50 w=2 p=0.7 (persistence regime) ==")
    for f, label in factories:
        run_braid(f, label)

    print("\n== NORWAY replay (sparse organic; must not lose) ==")
    for f, label in factories:
        run_norway(f, label)
