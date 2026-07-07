"""Headroom control: slide along the price curve by measured channel state.

The price curve (6.4) says coverage costs airtime. Static policies pick one
point on it forever; the airtime governor of 6.7 only derates near breach.
This experiment tests the full controller: each node measures its local
channel utilization u (transmissions it can hear x airtime, a quantity
Meshtastic firmware already tracks) and sets its own persistence and
cancellation from the surplus:

    u < 10%   ->  R=3, never cancel     (idle: spend surplus on coverage)
    u < 20%   ->  R=2, cancel@2
    u >= 20%  ->  R=1, cancel@1         (busy: retreat below plain flood)

Congestion must cost something for this to be a fair test, so reception
suffers utilization-coupled interference: extra loss = min(0.6, 0.8u),
applied from the neighbourhood's EWMA utilization. Offered load is swept
from quiet to saturating; static policies are run under the same model.

Metrics per (load, policy): coverage of reachable, tx per flood, mean node
utilization, share of nodes above the 25% health cap.
"""
import random
from collections import defaultdict

import sim_norway as S
from experiment_alltoall import bfs_cover
from experiment_pressure import PressureFlood, StaticFlood

T_TX = 0.5           # seconds of airtime per transmission
HOUR = 3600.0
U_CAP = 0.25         # community health threshold for channel utilization
SLOTS = 3


class HeadroomFlood(PressureFlood):
    """Policy from measured local utilization (set per hour by the runner).

    The retreat ladder descends THROUGH the Pareto frontier: full
    persistence -> plain flood (R=1, never cancel) -> emergency cancel@1.
    An earlier version stepped persist -> (R=2, cancel@2) -> cancel@1,
    coupling every persistence reduction with more cancellation; since
    cancellation starves bridge feeding, that ladder skipped the plain
    flood's operating point entirely and under-covered at moderate load
    (65% where flood managed 74%). Kept as HeadroomStrict: it buys
    near-perfect cap compliance at saturating load at extra coverage
    cost."""

    def __init__(self):
        super().__init__()
        self.util = {}

    def _policy(self, n):
        u = self.util.get(n, 0.0)
        if u < 0.16:
            return 0, None                # full persistence, never cancel
        if u < 0.21:
            return 1, None                # plain flood rung
        return 2, 1                       # emergency

    def persist_R(self, n):
        return 3 if self.util.get(n, 0.0) < 0.16 else 1


class HeadroomStrict(HeadroomFlood):
    """The cancellation-coupled ladder: strictest cap enforcement."""

    def _policy(self, n):
        u = self.util.get(n, 0.0)
        if u < 0.18:
            return 0, None
        if u < 0.24:
            return 1, 2
        return 2, 1

    def persist_R(self, n):
        u = self.util.get(n, 0.0)
        return 3 if u < 0.18 else 2 if u < 0.24 else 1


RUNGS = [(2, 1, 1),        # emergency: cancel@1
         (1, None, 1),     # plain flood
         (0, None, 2), (0, None, 3), (0, None, 4), (0, None, 5)]
SETPOINT_TARGET = 0.22     # margin under the 25% cap


class SetpointFlood(HeadroomFlood):
    """Cap-filling controller: maximize coverage subject to u <= cap.

    Instead of thresholds that retreat, each node hill-climbs a rung
    ladder ordered by airtime appetite (emergency -> plain flood ->
    persist R=2..5): climb while own utilization < 0.8*target, descend
    above target. The channel is kept exactly as full as allowed and the
    coverage is whatever that budget buys -- above every static policy
    wherever headroom exists."""

    def __init__(self):
        super().__init__()
        from collections import defaultdict as _dd
        self.rung = _dd(lambda: 3)
        self._util = {}

    @property
    def util(self):
        return self._util

    @util.setter
    def util(self, u):
        self._util = u
        for n, x in u.items():
            if x > SETPOINT_TARGET:
                self.rung[n] = max(0, self.rung[n] - 1)
            elif x < 0.8 * SETPOINT_TARGET:
                self.rung[n] = min(len(RUNGS) - 1, self.rung[n] + 1)

    def _policy(self, n):
        s, c, _ = RUNGS[self.rung[n]]
        return s, c

    def persist_R(self, n):
        return RUNGS[self.rung[n]][2]


def run(policy_factory, label, lam, hours=24, seed=1):
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, 168)
    world = S.World(links, nodes, presence, 168, seed=seed,
                    x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
    proto = policy_factory()

    # utilization-coupled interference: wrap rx with the neighbourhood's u
    util = defaultdict(float)          # EWMA per node, updated hourly
    base_rx = world.rx

    def rx(u_, v):
        if not base_rx(u_, v):
            return False
        return world.rng.random() >= min(0.6, 0.8 * util[v])

    world.rx = rx
    rng = random.Random(seed + 77)

    covr = reach_tot = txs = nf = 0
    for h in range(hours):
        world.hour = h % 168
        online = [n for n in world.presence if world.on(n)]
        heard = defaultdict(int)

        orig_transmit_count = [0]
        # count carrier-hearing per node by wrapping out-iteration is
        # invasive; instead approximate: every tx is heard by all link
        # neighbours of the transmitter
        def flood_and_count(src):
            t, received = proto.flood(world, src,
                                      relay_ok=lambda m: world.on(m))
            return t, received

        for _ in range(lam):
            src = rng.choice(online)
            reach = bfs_cover(world, src)
            if len(reach) < 2:
                continue
            nf += 1
            reach_tot += len(reach)
            t, received = flood_and_count(src)
            covr += len(set(received) & reach)
            txs += t
            # crude carrier accounting: charge each tx to the neighbours of
            # every node that received the packet (the active region)
            for n in received:
                for v in world.out.get(n, ()):
                    heard[v] += 1
        # hourly utilization update
        for n in online:
            u_now = heard[n] * T_TX / HOUR
            util[n] = util[n] + 0.4 * (u_now - util[n])
        if hasattr(proto, "util"):
            proto.util = dict(util)

    us = [util[n] for n in util] or [0.0]
    mean_u = sum(us) / len(us)
    over = sum(1 for x in us if x > U_CAP) / len(us)
    print(f"  {label:26} cover {100*covr/max(1,reach_tot):5.1f}%  "
          f"tx/flood {txs/max(1,nf):6.1f}  mean-util {100*mean_u:5.1f}%  "
          f"nodes>{int(U_CAP*100)}%: {100*over:4.1f}%")


def run_dense(policy_factory, label, lam, hours=24, seed=1):
    from experiment_pressure import DenseWorld
    world = DenseWorld(0.9, 0.8, seed=seed)
    proto = policy_factory()
    util = defaultdict(float)
    base_rx = world.rx

    def rx(u_, v):
        if not base_rx(u_, v):
            return False
        return world.rng.random() >= min(0.6, 0.8 * util[v])

    world.rx = rx
    rng = random.Random(seed + 77)
    all_nodes = world.nodes

    covr = txs = nf = 0
    for h in range(hours):
        heard = defaultdict(int)
        for _ in range(lam):
            src = rng.choice(all_nodes)
            nf += 1
            t, received = proto.flood(world, src, hop_limit=10,
                                      relay_ok=lambda m: True)
            covr += len(received)
            txs += t
            for n in received:
                for v in world.out.get(n, ()):
                    heard[v] += 1
        for n in all_nodes:
            u_now = heard[n] * T_TX / HOUR
            util[n] = util[n] + 0.4 * (u_now - util[n])
        if hasattr(proto, "util"):
            proto.util = dict(util)

    us = [util[n] for n in all_nodes]
    mean_u = sum(us) / len(us)
    over = sum(1 for x in us if x > U_CAP) / len(us)
    print(f"  {label:26} cover {100*covr/(nf*len(all_nodes)):5.1f}%  "
          f"tx/flood {txs/max(1,nf):6.1f}  mean-util {100*mean_u:5.1f}%  "
          f"nodes>{int(U_CAP*100)}%: {100*over:4.1f}%")


if __name__ == "__main__":
    print("#### NORWAY (sparse: congestion physically unreachable) ####")
    for lam in (20, 120):
        print(f"== offered load {lam} floods/hour ==")
        run(lambda: StaticFlood(1, None, 1), "static plain flood", lam)
        run(lambda: StaticFlood(1, None, 3), "static persist R=3", lam)
        run(HeadroomFlood, "HEADROOM controller", lam)
        print()

    print("#### DENSE world (60 nodes, cliques+bridges: congestion regime) ####")
    for lam in (10, 40, 90, 160):
        print(f"== offered load {lam} floods/hour ==")
        run_dense(lambda: StaticFlood(1, None, 1), "static plain flood", lam)
        run_dense(lambda: StaticFlood(1, 1, 1), "static cancel@1", lam)
        run_dense(lambda: StaticFlood(1, None, 3), "static persist R=3", lam)
        run_dense(HeadroomFlood, "HEADROOM (via flood rung)", lam)
        run_dense(HeadroomStrict, "HEADROOM strict", lam)
        run_dense(SetpointFlood, "SETPOINT (fill the cap)", lam)
        print()
