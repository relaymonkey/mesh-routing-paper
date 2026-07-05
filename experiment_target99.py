"""What would it take to reach 99% unicast delivery?

Steps:
1. ORACLE CEILING: per attempt, does ANY forward path exist over online,
   relay-capable nodes? No algorithm can deliver an unreachable packet, so
   this bounds every protocol from above.
2. FAILURE ANATOMY: where do GradCor-R's failures actually occur
   (unreachable / cold start / mid-walk dead end)?
3. LADDER OF SIMPLE FIXES, stacked, each one firmware-cheap:
     R0  GradCor-R as published (on-demand plant)
     R1  + fallback-flood cold start (no oracle plant; from experiment_plant)
     R2  + rescue: at a local minimum, the stuck holder floods the packet
         (graceful degradation exactly at the failure point, hop limit 7)
     R3  + end-to-end retries (k = 1, 2, 3, 5) -- machinery Meshtastic DMs
         already have (ReliableRouter); each retry re-walks with fresh
         channel draws and benefits from gradients refreshed meanwhile
All configs report delivery %, delivery as % of reachable, tx/packet and
tx/delivered, 10 seeds.
"""
import random
from collections import defaultdict, deque

import sim_norway as S
from experiment_plant import BroadcastSeededGrad

PARAMS = dict(x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
SEEDS = tuple(range(1, 11))
HOURS = 168


def reachable(world, src, dst):
    """Forward path exists over online nodes; interior hops must be
    relay-capable. Links = anything with p > 0 in this world."""
    seen = {src}
    dq = deque([src])
    while dq:
        u = dq.popleft()
        for v in world.out.get(u, ()):
            if v in seen or not world.on(v):
                continue
            if v == dst:
                return True
            if not world.can_relay(v):
                continue
            seen.add(v)
            dq.append(v)
    return False


class RescueGrad(BroadcastSeededGrad):
    """Fallback-flood cold start + rescue flood at a local minimum.

    The corridor walk is identical to GradCor-R; the one change is the
    dead-end action: instead of a deterministic drop, the stuck holder
    floods the packet (it is the node that just proved, over the whole
    escalation ladder, that it has no routable neighbour -- flooding from
    *there* is the narrowest possible flood that can still help)."""

    def __init__(self, rescue=True, hl=S.HOP_LIMIT):
        super().__init__(cadence=0)
        self.rescue = rescue
        self.hl = hl                    # hop limit for its own internal floods

    def _stamp(self, dst, chain, parents, holder):
        """Refresh gradients along chain + flood path holder->dst."""
        path = [dst]
        while parents.get(path[-1]) is not None and path[-1] != holder:
            path.append(parents[path[-1]])
        path.reverse()                      # holder ... dst
        full = chain[:-1] + path            # chain ends at holder
        g = self.grad.setdefault(dst, {})
        for i, n in enumerate(full):
            g[n] = (len(full) - 1 - i, 0)

    def send(self, world, src, dst):
        g = self.grad.get(dst)
        if g is None or src not in g:
            ok, tx, parents, _ = S.flood(world, src, dst, hop_limit=self.hl,
                                         collect_parents=True)
            if ok:
                self._stamp(dst, [src], parents, src)
            return ok, tx
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
                if self.rescue:
                    ok, ftx, parents, _ = S.flood(world, holder, dst,
                                                  hop_limit=self.hl,
                                                  collect_parents=True)
                    tx += ftx
                    if ok:
                        self._stamp(dst, chain, parents, holder)
                    return ok, tx
                return False, tx
            visited.add(forwarded)
            chain.append(forwarded)
            holder = forwarded
        return False, tx


class Retry:
    """End-to-end retry wrapper: re-invoke the underlying send up to k
    extra times on failure (fresh channel draws; gradient state persists,
    including anything a failed attempt planted or refreshed)."""

    def __init__(self, proto, k):
        self.proto = proto
        self.k = k

    def send(self, world, src, dst):
        tx = 0
        for _ in range(1 + self.k):
            ok, t = self.proto.send(world, src, dst)
            tx += t
            if ok:
                return True, tx
        return False, tx


def run(make_proto, label, anatomy=False):
    agg = [0, 0, 0]                    # delivered, sent, tx
    reach_agg = [0, 0]                 # delivered|reachable, reachable
    fail = defaultdict(int)
    for seed in SEEDS:
        world = S.World(*_DATA, HOURS, seed=seed, **PARAMS)
        rng = random.Random(seed + 999)
        pairs = S.pick_pairs(_TRS, _PRESENCE, HOURS, rng, S.PAIRS)
        proto = make_proto()
        for hour in range(HOURS):
            world.hour = hour
            for (s, d) in pairs:
                if not (world.on(s) and world.on(d)):
                    continue
                r = reachable(world, s, d)
                had_grad = (getattr(proto, "proto", proto).grad.get(d) or {}).get(s) is not None \
                    if hasattr(getattr(proto, "proto", proto), "grad") else None
                ok, tx = proto.send(world, s, d)
                agg[0] += ok
                agg[1] += 1
                agg[2] += tx
                if r:
                    reach_agg[1] += 1
                    reach_agg[0] += ok
                if anatomy and not ok:
                    if not r:
                        fail["unreachable (no forward path this hour)"] += 1
                    elif had_grad is False:
                        fail["cold start (no gradient, fallback failed)"] += 1
                    else:
                        fail["mid-walk (dead end / cap, reachable)"] += 1
    dlv, snt, tx = agg
    print(f"{label:44} {100*dlv/snt:6.1f}%   of-reachable {100*reach_agg[0]/max(1,reach_agg[1]):6.1f}%   "
          f"tx/pkt {tx/snt:6.1f}   tx/dlv {tx/max(1,dlv):6.1f}")
    if anatomy:
        tot_fail = snt - dlv
        print(f"    failure anatomy ({tot_fail} failures / {snt} sent):")
        for k, v in sorted(fail.items(), key=lambda kv: -kv[1]):
            print(f"      {k:46} {v:6}  ({100*v/max(1,tot_fail):.1f}% of failures)")
    return agg, reach_agg


if __name__ == "__main__":
    nodes = S.load_nodes()
    _TRS = S.load_traceroutes()
    links = S.links_from_traceroutes(_TRS)
    _PRESENCE, _ = S.load_presence(_TRS, HOURS)
    _DATA = (links, nodes, _PRESENCE)

    print("== oracle ceiling (BFS reachability over online nodes) ==")
    tot = [0, 0]
    for seed in SEEDS:
        world = S.World(*_DATA, HOURS, seed=seed, **PARAMS)
        rng = random.Random(seed + 999)
        pairs = S.pick_pairs(_TRS, _PRESENCE, HOURS, rng, S.PAIRS)
        for hour in range(HOURS):
            world.hour = hour
            for (s, d) in pairs:
                if not (world.on(s) and world.on(d)):
                    continue
                tot[1] += 1
                tot[0] += reachable(world, s, d)
    print(f"reachable attempts: {tot[0]}/{tot[1]} = {100*tot[0]/tot[1]:.1f}%  "
          f"<- upper bound for ANY algorithm\n")

    print(f"{'config':44} {'delivery':>8} {'':>14} {'':>14}")
    run(S.ReactiveGradProto, "R0  GradCor-R (published, oracle plant)")
    run(lambda: BroadcastSeededGrad(0), "R1  + fallback-flood cold start")
    run(lambda: RescueGrad(), "R2  + rescue flood at local minimum")
    for k in (1, 2, 3, 5):
        run(lambda k=k: Retry(RescueGrad(), k), f"R3  + e2e retries k={k}")
    run(lambda: Retry(RescueGrad(hl=15), 5), "R4  + deep internal floods (hl=15), k=5")
    run(lambda: Retry(RescueGrad(hl=15), 10), "R5  same, k=10")
    print()
    print("anatomy of the best config's remaining failures:")
    run(lambda: Retry(RescueGrad(hl=15), 10), "R5 anatomy", anatomy=True)
