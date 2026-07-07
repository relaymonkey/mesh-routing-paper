"""Does GradCor survive real depth? Synthetic long-path stress test.

The Norway replay cannot exercise paths beyond 7 hops (its link graph is
built from hop<=7 traceroutes and its floods obey the wire's hop field), so
the no-hop-limit property is spec-proven but empirically untested. This
experiment builds synthetic "braid" topologies with controlled true
distance and measures behaviour at depths the replay never sees.

Topology: w parallel lanes of length d (rails), full bipartite links
between consecutive positions, rungs within a position, symmetric links,
every link the same per-transmission delivery probability p. All nodes
always on: depth is isolated from churn. src sits at position 0, dst at d.

Conditions per (d, w, p):
  WARM corridor   gradients pre-planted with true distances (as after one
                  successful exchange); GradCor-R walk, no hop counter.
  FLOOD unlimited a flood with no hop limit carries each packet (the
                  "just remove the counter" alternative).
  COLD ramp       no state at all: packet 1 falls back to a flood
                  (hop limit 7 = today's wire, or unlimited), delivery
                  refresh plants, packets 2..N ride the corridor.
Writes depth_results.csv.
"""
import csv
import random

import sim_norway as S
from experiment_target99 import RescueGrad

PACKETS = 300
DEPTHS = (7, 20, 50, 100, 200)
WIDTHS = (1, 2, 3)
PS = (0.5, 0.7, 0.9)


class BraidWorld:
    """Minimal world compatible with sim_norway's flood/walk machinery."""

    def __init__(self, depth, width, p, seed):
        self.rng = random.Random(seed)
        self.depth = depth
        self.p = {}
        self.snr_db = {}
        self.out = {}
        nodes = [(i, l) for i in range(depth + 1) for l in range(width)]
        self.names = {n: f"!{i:04x}{l:02x}00" for n, (i, l) in
                      ((n, n) for n in nodes)}
        def name(i, l):
            return f"!{i:04x}{l:02x}00"
        for i, l in nodes:
            u = name(i, l)
            self.out[u] = []
            for j, m in nodes:
                if (j, m) == (i, l):
                    continue
                if abs(j - i) == 1 or (j == i and m != l):
                    v = name(j, m)
                    self.out[u].append(v)
                    self.p[(u, v)] = p
                    self.snr_db[(u, v)] = 0.0
        self.src = name(0, 0)
        self.dst = name(depth, 0)
        # true hop distance to dst (lane changes are free within a hop here:
        # distance is the positional gap, +1 if you sit in the wrong lane at
        # the destination column -- braid symmetric, use positional distance)
        self.true_g = {name(i, l): depth - i for i, l in nodes}
        self.hour = 0
        self.hours = 1

    def on(self, n):
        return True

    def can_relay(self, n):
        return True

    def rx(self, u, v):
        pr = self.p.get((u, v))
        return pr is not None and self.rng.random() < pr


def warm_proto(world):
    proto = S.ReactiveGradProto()
    proto.grad[world.dst] = {n: (g, 0) for n, g in world.true_g.items()}
    return proto


def run_cell(depth, width, p, seed=1):
    out = {}
    # WARM corridor
    world = BraidWorld(depth, width, p, seed)
    proto = warm_proto(world)
    dlv = tx = 0
    for _ in range(PACKETS):
        ok, t = proto.send(world, world.src, world.dst)
        dlv += ok
        tx += t
    out["warm_corridor"] = (100 * dlv / PACKETS, tx / PACKETS)

    # FLOOD as transport, unlimited hops
    world = BraidWorld(depth, width, p, seed + 1)
    dlv = tx = 0
    for _ in range(PACKETS):
        ok, t, _, _ = S.flood(world, world.src, world.dst, hop_limit=10**6)
        dlv += ok
        tx += t
    out["flood_unlimited"] = (100 * dlv / PACKETS, tx / PACKETS)
    return out


def cold_ramp(depth, width, p, hl, n_packets=10, trials=150):
    """Fresh state; send n_packets in sequence; per-packet delivery rate."""
    per_pkt = [0] * n_packets
    for trial in range(trials):
        world = BraidWorld(depth, width, p, 1000 + trial)
        proto = RescueGrad(rescue=False, hl=hl)
        for i in range(n_packets):
            ok, _ = proto.send(world, world.src, world.dst)
            per_pkt[i] += ok
    return [100 * c / trials for c in per_pkt]


if __name__ == "__main__":
    rows = []
    print(f"{'d':>4} {'w':>2} {'p':>4} {'warm corridor':>18} {'flood unlimited':>18}")
    for depth in DEPTHS:
        for width in WIDTHS:
            for p in PS:
                cell = run_cell(depth, width, p)
                wc, ft = cell["warm_corridor"], cell["flood_unlimited"]
                rows.append(dict(depth=depth, width=width, p=p,
                                 warm_dlv=round(wc[0], 1), warm_tx=round(wc[1], 1),
                                 flood_dlv=round(ft[0], 1), flood_tx=round(ft[1], 1)))
                print(f"{depth:>4} {width:>2} {p:>4} {wc[0]:>9.1f}% {wc[1]:>7.1f}tx "
                      f"{ft[0]:>9.1f}% {ft[1]:>7.1f}tx")
    with open("depth_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n== cold start ramp (w=2, p=0.7): per-packet delivery, fresh mesh ==")
    for depth in (20, 50):
        for hl, label in ((7, "fallback flood @ hop limit 7 (today's wire)"),
                          (10**6, "fallback flood, unlimited")):
            ramp = cold_ramp(depth, 2, 0.7, hl)
            print(f"d={depth:>3} {label:44} " +
                  " ".join(f"{v:5.1f}" for v in ramp))
    print("\nwrote depth_results.csv")
