"""Is the age-based corridor widening (3 h / 24 h) justified, sensitive, or
replaceable by something adaptive?

1. HAZARD: bucket GradCor sends by the gradient age at the source ->
   empirical decay curve of gradient usefulness (the science the fixed
   thresholds should be derived from).
2. SWEEP: grid over AGE_WIDEN and AGE_DEAD -> sensitivity of delivery/cost.
3. REACTIVE: variant that ignores wall-clock age for eligibility entirely
   (strict -> equal -> any purely by per-hop escalation); age only for replant.
4. ADAPTIVE: variant that starts each packet at the corridor level that the
   last delivery to that destination needed (learned prior, no wall clock).
"""
import random
from collections import defaultdict

import sim_norway as S

PARAMS = dict(x0=8, pmax=0.8, pmin=0.25, kobs=10, rev_p=0.0)
SEEDS = (1, 2, 3)


def run_proto(make_proto, age_widen=None, age_dead=None, hook=None):
    """Replay GRADCOR-only with optional threshold overrides."""
    saved = (S.AGE_WIDEN, S.AGE_DEAD)
    if age_widen is not None:
        S.AGE_WIDEN = age_widen
    if age_dead is not None:
        S.AGE_DEAD = age_dead
    try:
        nodes, trs, links, presence = _DATA
        tot = [0, 0, 0]
        for seed in SEEDS:
            world = S.World(links, nodes, presence, 168, seed=seed, **PARAMS)
            rng = random.Random(seed + 999)
            pairs = S.pick_pairs(trs, presence, 168, rng, S.PAIRS)
            proto = make_proto()
            for hour in range(168):
                world.hour = hour
                proto.age_all()
                for (s, d) in pairs:
                    if not (world.on(s) and world.on(d)):
                        continue
                    if hook:
                        hook(proto, world, s, d)
                    ok, tx = proto.send(world, s, d)
                    tot[0] += ok
                    tot[1] += 1
                    tot[2] += tx
        return tot
    finally:
        S.AGE_WIDEN, S.AGE_DEAD = saved


class ReactiveGrad(S.GradProto):
    """No wall-clock widening: strict(3 tries) -> equal -> any, per hop.
    Age is used only for the replant decision."""

    def send(self, world, src, dst):
        tx = 0
        g = self.grad.get(dst)
        src_entry = g.get(src) if g else None
        if g is None or src_entry is None or src_entry[1] >= S.AGE_DEAD:
            tx += self.plant(world, dst)
            g = self.grad[dst]
            if src not in g:
                return False, tx
        visited = {src}
        holder = src
        chain = [src]
        while tx < S.MAX_TX_PER_PKT:
            gh, _ah = g.get(holder, (10**6, 10**9))
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


class AdaptiveGrad(ReactiveGrad):
    """Reactive, plus a learned per-destination starting level: begin at the
    corridor level below the one the previous packet to dst needed."""

    def __init__(self):
        super().__init__()
        self.start_level = defaultdict(int)

    def send(self, world, src, dst):
        tx = 0
        g = self.grad.get(dst)
        src_entry = g.get(src) if g else None
        if g is None or src_entry is None or src_entry[1] >= S.AGE_DEAD:
            tx += self.plant(world, dst)
            g = self.grad[dst]
            if src not in g:
                return False, tx
        visited = {src}
        holder = src
        chain = [src]
        max_level_used = 0
        lvl0 = self.start_level[dst]
        while tx < S.MAX_TX_PER_PKT:
            gh, _ah = g.get(holder, (10**6, 10**9))
            forwarded = None
            for level in range(lvl0, 3 + S.GRAD_RETRIES):
                max_level_used = max(max_level_used, level)
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
                        self.start_level[dst] = max(0, max_level_used - 1)
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
                self.start_level[dst] = 0    # failure -> reset prior
                return False, tx
            visited.add(forwarded)
            chain.append(forwarded)
            holder = forwarded
        return False, tx


def hazard_curve():
    """Delivery and cost bucketed by gradient age at the source at send time."""
    nodes, trs, links, presence = _DATA
    buckets = defaultdict(lambda: [0, 0, 0])
    for seed in SEEDS:
        world = S.World(links, nodes, presence, 168, seed=seed, **PARAMS)
        rng = random.Random(seed + 999)
        pairs = S.pick_pairs(trs, presence, 168, rng, S.PAIRS)
        proto = S.GradProto()
        for hour in range(168):
            world.hour = hour
            proto.age_all()
            for (s, d) in pairs:
                if not (world.on(s) and world.on(d)):
                    continue
                g = proto.grad.get(d)
                age = g[s][1] if (g and s in g) else None
                ok, tx = proto.send(world, s, d)
                if age is None or age >= S.AGE_DEAD:
                    key = "replant"
                elif age == 0:
                    key = "age 0 (just planted/refreshed)"
                elif age <= 2:
                    key = "age 1-2 h"
                elif age <= 6:
                    key = "age 3-6 h"
                elif age <= 12:
                    key = "age 7-12 h"
                else:
                    key = "age 13-23 h"
                b = buckets[key]
                b[0] += ok
                b[1] += 1
                b[2] += tx
    return buckets


def show(label, tot):
    dlv, snt, tx = tot
    print(f"{label:44} {100*dlv/max(1,snt):8.1f}% {tx/max(1,dlv):10.1f} tx/dlv")


if __name__ == "__main__":
    _DATA = (S.load_nodes(), S.load_traceroutes(), None, None)
    trs = _DATA[1]
    _DATA = (_DATA[0], trs, S.links_from_traceroutes(trs),
             S.load_presence(trs, 168)[0])

    print("== 1. hazard: gradient age at source vs outcome (baseline 3/24) ==")
    hb = hazard_curve()
    order = ["age 0 (just planted/refreshed)", "age 1-2 h", "age 3-6 h",
             "age 7-12 h", "age 13-23 h", "replant"]
    for k in order:
        if k in hb:
            dlv, snt, tx = hb[k]
            print(f"{k:32} sent {snt:5}  delivery {100*dlv/max(1,snt):5.1f}%  "
                  f"tx/dlv {tx/max(1,dlv):6.1f}")

    print("\n== 2a. sweep AGE_WIDEN (AGE_DEAD=24) ==")
    for w in (0, 1, 3, 6, 12, 999):
        show(f"AGE_WIDEN={w:>3}", run_proto(S.GradProto, age_widen=w))

    print("\n== 2b. sweep AGE_DEAD (AGE_WIDEN=3) ==")
    for d in (6, 12, 24, 48, 999):
        show(f"AGE_DEAD={d:>3}", run_proto(S.GradProto, age_dead=d))

    print("\n== 3. variants ==")
    show("baseline (age-widened, 3/24)", run_proto(S.GradProto))
    show("reactive-only (no wall-clock widening)", run_proto(ReactiveGrad))
    show("adaptive start level (learned prior)", run_proto(AdaptiveGrad))
