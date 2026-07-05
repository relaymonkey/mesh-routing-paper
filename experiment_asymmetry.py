"""Does GradCor survive gradients that underestimate the true forward distance?

For every GRADCOR send in the Norway replay, record:
  g_src   planted/refreshed gradient at the source at send time
  d_fwd   true forward BFS distance src->dst over currently-online nodes
  hops    hops actually taken when delivered
  tx      transmissions spent
Bucket outcomes by (d_fwd - g_src): positive = gradient optimistic
(asymmetry bias), i.e. the packet needs MORE hops than the source imagines.
"""
import random
from collections import defaultdict, deque

import sim_norway as S


def bfs_forward(world, src, dst):
    """Shortest forward path length over online nodes and existing links."""
    if not (world.on(src) and world.on(dst)):
        return None
    seen = {src: 0}
    dq = deque([src])
    while dq:
        u = dq.popleft()
        if u == dst:
            return seen[u]
        for v in world.out.get(u, ()):
            if v not in seen and world.on(v) and world.p.get((u, v), 0) > 0.02:
                # relay-capable check mirrors flood behaviour
                if v != dst and not world.can_relay(v):
                    continue
                seen[v] = seen[u] + 1
                dq.append(v)
    return None


class InstrumentedGrad(S.GradProto):
    """send() clone that also reports the hop count actually taken."""

    def send_logged(self, world, src, dst):
        g0 = self.grad.get(dst)
        g_src = g0[src][0] if (g0 and src in g0 and g0[src][1] < S.AGE_DEAD) else None

        tx = 0
        g = self.grad.get(dst)
        src_entry = g.get(src) if g else None
        if g is None or src_entry is None or src_entry[1] >= S.AGE_DEAD:
            tx += self.plant(world, dst)
            g = self.grad[dst]
            if src not in g:
                return False, tx, g_src, None
        visited = {src}
        holder = src
        chain = [src]
        while tx < S.MAX_TX_PER_PKT:
            gh, ah = g.get(holder, (10**6, 10**9))
            forwarded = None
            for level in range(3 + S.GRAD_RETRIES):
                strict = level <= S.GRAD_RETRIES and ah < S.AGE_WIDEN
                equal_ok = (not strict) or ah >= S.AGE_WIDEN
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
                        return True, tx, g_src, len(chain)
                    if not world.can_relay(v):
                        continue
                    gv = g.get(v, (10**6, 10**9))[0]
                    if gv < gh or (equal_ok and gv == gh) or any_ok:
                        cands.append((gv, v))
                if cands:
                    forwarded = min(cands)[1]
                    break
            if forwarded is None:
                return False, tx, g_src, None
            visited.add(forwarded)
            chain.append(forwarded)
            holder = forwarded
        return False, tx, g_src, None


def main():
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    hours = 168
    presence, _ = S.load_presence(trs, hours)

    buckets = defaultdict(lambda: [0, 0, 0])   # gap -> [delivered, sent, tx]
    over_took = 0     # delivered while taking more hops than g_src promised
    over_total = 0
    longer_all = [0, 0]
    over_hops = []
    for seed in (1, 2, 3):
        # calibration of the D-280 corrected extraction; rev_p=0 means
        # unobserved reverse links do not exist -- asymmetry fully binding
        world = S.World(links, nodes, presence, hours,
                        x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0, seed=seed)
        rng = random.Random(seed + 999)
        pairs = S.pick_pairs(trs, presence, hours, rng, S.PAIRS)
        proto = InstrumentedGrad()
        longer = [0, 0]     # delivered taking more hops than g_src promised
        for hour in range(hours):
            world.hour = hour
            proto.age_all()
            for (s, d) in pairs:
                if not (world.on(s) and world.on(d)):
                    continue
                d_fwd = bfs_forward(world, s, d)
                ok, tx, g_src, hops = proto.send_logged(world, s, d)
                if ok and g_src is not None:
                    longer[1] += 1
                    if hops > g_src:
                        longer[0] += 1
                        over_hops.append((g_src, hops))
                if d_fwd is None:
                    key = "unreachable"
                elif g_src is None:
                    key = "no gradient (fresh plant)"
                else:
                    gap = d_fwd - g_src
                    if gap <= 0:
                        key = "gap <= 0 (g honest/pessimistic)"
                    elif gap <= 2:
                        key = "gap 1-2 (g optimistic)"
                    else:
                        key = "gap >= 3 (g very optimistic)"
                    if gap > 0:
                        over_total += 1
                        over_took += ok
                b = buckets[key]
                b[0] += ok
                b[1] += 1
                b[2] += tx
        longer_all[0] += longer[0]
        longer_all[1] += longer[1]

    print(f"{'bucket':38} {'sent':>6} {'delivery%':>10} {'tx/delivered':>13}")
    order = ["gap <= 0 (g honest/pessimistic)", "gap 1-2 (g optimistic)",
             "gap >= 3 (g very optimistic)", "no gradient (fresh plant)", "unreachable"]
    for k in order:
        if k not in buckets:
            continue
        dlv, snt, tx = buckets[k]
        dr = 100 * dlv / max(1, snt)
        tpd = tx / max(1, dlv)
        print(f"{k:38} {snt:>6} {dr:>9.1f} {tpd:>13.1f}")
    print(f"\npackets sent while g underestimated the true forward distance: "
          f"{over_total}, delivered anyway: {over_took} ({100*over_took/max(1,over_total):.1f}%)")
    print(f"deliveries that took MORE hops than the source's g promised: "
          f"{longer_all[0]}/{longer_all[1]} ({100*longer_all[0]/max(1,longer_all[1]):.1f}%)")
    if over_hops:
        import statistics as st
        exceed = [h - g for g, h in over_hops]
        print(f"  overshoot among those: median +{st.median(exceed):.0f} hops, "
              f"max +{max(exceed)} (g promised {st.median(g for g,_ in over_hops):.0f} median)")


if __name__ == "__main__":
    main()
