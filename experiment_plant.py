"""Is on-demand gradient planting a causal cheat, and does removing it matter?

In the replay, a source with no gradient triggers a planting flood FROM the
destination at that instant (charged to the packet). Causally, nothing in a
real deployment tells the destination to flood on demand. The deployable
cold-start paths are:

  1. SEEDING: the destination's ordinary periodic broadcasts (NodeInfo /
     position) double as planting floods -- traffic the mesh sends anyway.
  2. FALLBACK: a source with no gradient managed-floods the data packet
     (exactly today's Meshtastic behaviour); if it delivers, the delivery
     refresh plants the gradient along the proven path for every packet after.

This experiment replaces the on-demand shortcut with those mechanisms:

  GRADCOR-R    on-demand plant (the paper's headline shortcut), reference
  SEED-3H/6H   no on-demand plant; dst floods a broadcast every 3/6 h while
               online (deterministic per-dst phase); cold sends fall back to
               a managed flood + delivery-refresh planting
  NO-SEED      no seeding at all: cold start purely via fallback + refresh

Seeding airtime is reported separately AND folded into a combined tx/dlv:
in deployment those broadcasts already exist, so the marginal cost lies
between the two accountings.
"""
import random
from collections import defaultdict

import sim_norway as S

PARAMS = dict(x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
SEEDS = tuple(range(1, 11))
HOURS = 168


class BroadcastSeededGrad(S.ReactiveGradProto):
    """GradCor-R with the on-demand plant removed (causally clean cold start).

    Gradients come only from (a) the destination's periodic broadcasts,
    merged into the table (nodes missed by one broadcast keep old entries),
    and (b) delivery refreshes -- including from the fallback flood a
    gradient-less source uses to carry the packet."""

    def __init__(self, cadence):
        super().__init__()
        self.cadence = cadence  # hours between dst broadcasts; 0 = never

    def seed_tick(self, world, dsts, hour):
        tx = 0
        if not self.cadence:
            return 0
        for dst in dsts:
            phase = int(dst[1:], 16) % self.cadence
            if world.on(dst) and hour % self.cadence == phase:
                _, ftx, _, received = S.flood(world, dst, "\x00none")
                tx += ftx
                g = self.grad.setdefault(dst, {})
                for n, h in received.items():
                    g[n] = (h, 0)
        return tx

    def send(self, world, src, dst):
        g = self.grad.get(dst)
        if g is None or src not in g:
            # cold start: managed-flood the packet itself; on delivery the
            # refresh plants the gradient along the proven path (same
            # idealization as the in-walk refresh, threat: refresh rides ACK)
            ok, tx, parents, _ = S.flood(world, src, dst, collect_parents=True)
            if ok:
                path = [dst]
                while parents.get(path[-1]) is not None:
                    path.append(parents[path[-1]])
                gd = self.grad.setdefault(dst, {})
                for i, n in enumerate(path):
                    gd[n] = (i, 0)
            return ok, tx
        # corridor walk identical to ReactiveGradProto.send after its plant guard
        tx = 0
        visited = {src}
        holder = src
        chain = [src]
        while tx < S.MAX_TX_PER_PKT:
            gh = g.get(holder, (10**6, 10**9))[0]
            forwarded = None
            for level in range(3 + S.GRAD_RETRIES):
                strict = level <= S.GRAD_RETRIES
                equal_ok = not strict
                any_ok = level == 2 + S.GRAD_RETRIES
                tx += 1
                cands = []
                for v in world.out.get(holder, ()):
                    if v in visited:
                        continue
                    if not world.rx(holder, v):
                        continue
                    if v == dst:
                        for i, n in enumerate(chain + [dst]):
                            g[n] = (len(chain) - i, 0)
                        return True, tx
                    if not world.can_relay(v):
                        continue
                    gv = g.get(v, (10**6, 10**9))[0]
                    if gv < gh or (equal_ok and gv == gh) or any_ok:
                        cands.append((gv, v))
                if cands:
                    forwarded = min(cands)[1]
                    break
            if forwarded is None:
                return False, tx
            visited.add(forwarded)
            chain.append(forwarded)
            holder = forwarded
        return False, tx


def main():
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, HOURS)

    agg = defaultdict(lambda: [0, 0, 0])   # proto -> [delivered, sent, pkt_tx]
    seed_tx = defaultdict(int)             # proto -> seeding tx
    for seed in SEEDS:
        world = S.World(links, nodes, presence, HOURS, seed=seed, **PARAMS)
        rng = random.Random(seed + 999)
        pairs = S.pick_pairs(trs, presence, HOURS, rng, S.PAIRS)
        dsts = sorted({d for (_, d) in pairs})
        protos = {
            "FLOOD": None,
            "GRADCOR-R (on-demand plant)": S.ReactiveGradProto(),
            "SEED-3H (broadcast-seeded)": BroadcastSeededGrad(3),
            "SEED-6H (broadcast-seeded)": BroadcastSeededGrad(6),
            "NO-SEED (fallback+refresh only)": BroadcastSeededGrad(0),
        }
        for hour in range(HOURS):
            world.hour = hour
            for name, proto in protos.items():
                if isinstance(proto, BroadcastSeededGrad):
                    seed_tx[name] += proto.seed_tick(world, dsts, hour)
            for (s, d) in pairs:
                if not (world.on(s) and world.on(d)):
                    continue
                for name, proto in protos.items():
                    if proto is None:
                        ok, tx, _, _ = S.flood(world, s, d)
                    else:
                        ok, tx = proto.send(world, s, d)
                    a = agg[name]
                    a[0] += ok
                    a[1] += 1
                    a[2] += tx

    print(f"{'proto':34} {'delivery%':>9} {'tx/pkt':>7} {'tx/dlv':>7} "
          f"{'seed tx':>8} {'tx/dlv incl. seed':>18}")
    for name, (dlv, snt, tx) in agg.items():
        st_ = seed_tx[name]
        print(f"{name:34} {100*dlv/max(1,snt):>8.1f} {tx/max(1,snt):>7.1f} "
              f"{tx/max(1,dlv):>7.1f} {st_:>8} {(tx+st_)/max(1,dlv):>18.1f}")


if __name__ == "__main__":
    main()
