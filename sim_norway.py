"""
Routing-strategy simulation on the REAL Norway mesh topology.

Data sources (production, 2026-06-27 .. 2026-07-04):
- data/nodes.csv          Memgraph :Node  (499 nodes, roles, positions)
- data/edges.csv          Memgraph :HEARD (3613 directed links, old D-267 extraction)
- data/traceroutes_v2.tsv raw TRACEROUTE_APP packets from ClickHouse (18919 pkts,
                          incl. hop_start/hop_limit for request/response
                          classification). Link extraction mirrors builder.go
                          D-280: response-row orientation flip, evidence-gated
                          endpoints, route_back return legs, INT8_MIN sentinel.
- data/activity_hourly.tsv per-node hourly message counts (real presence/churn)

Improvements over the toy unit-square sim:
1. Real directed link graph (traceroute-observed, incl. route_back links the
   production builder currently drops).
2. Link delivery probability from measured SNR (raw/4 -> dB) via a logistic
   PER curve, CALIBRATED so simulated flood hop-count distribution matches the
   empirically observed traceroute hop distribution.
3. Real churn: per-hour node presence from activity + traceroute relay
   appearances (median node online 22/168 h), replacing synthetic mobility.
4. Role-aware flooding: CLIENT_MUTE nodes never rebroadcast (Meshtastic
   semantics), matching the 66 CLIENT_MUTE nodes in the network.
5. Crude collision/capture model in flood rounds (the toy sim's idealized MAC
   was its own stated weakness): when several frames arrive at a receiver in
   the same round, only the strongest decodes, with capture probability CAPTURE_P.
6. Traffic = real (src,dst) traceroute pairs, weighted by observed frequency.

Protocols compared (same three as the research):
  FLOOD    managed flood, hop limit 7
  PATH     MeshCore-like source routing: flood discovery + source-routed ACK,
           strict per-hop unicast with retries, re-discovery on failure
  GRADCOR  gradient-corridor anycast: per-destination hop-gradient planted by
           one flood, anycast forwarding down the gradient, corridor widens
           with gradient age, graceful degradation toward flood
"""

import ast
import csv
import math
import random
import statistics as st
from collections import Counter, defaultdict

DATA = "data"
HOP_LIMIT = 7
HOP_RETRIES = 3
GRAD_RETRIES = 2
AGE_WIDEN = 3            # hours until corridor admits equal-gradient nodes
AGE_DEAD = 24            # hours until gradient is replanted
CAPTURE_P = 0.8          # P(strongest frame survives a same-round collision)
PRESENCE_GAP_FILL = 3    # observed at h1 and h2, gap <= this -> assume on between
MAX_TX_PER_PKT = 2000
PAIRS = 30
SEEDS = tuple(range(1, 11))

BROADCAST, PLACEHOLDER = "!ffffffff", "!00000000"


def canon(x):
    return f"!{x:08x}"


# ---------------- data loading ----------------
def load_nodes():
    nodes = {}
    with open(f"{DATA}/nodes.csv") as f:
        for r in csv.DictReader(f):
            nid = r["id"].strip('"')
            nodes[nid] = {
                "short": r["short"].strip('"'),
                "role": r["role"].strip('"') or "UNKNOWN",
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "hasPos": r["hasPos"] == "true",
            }
    return nodes


def load_traceroutes():
    rows = []
    with open(f"{DATA}/traceroutes_v2.tsv") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            def _i(x):
                try:
                    return int(x)
                except ValueError:
                    return None
            hs, hl = _i(r["hop_start"]), _i(r["hop_limit"])
            rows.append({
                "src": r["source_node_id"],
                "dst": r["dest_node_id"],
                "route": ast.literal_eval(r["route"]),
                "snr_t": ast.literal_eval(r["snr_towards"]),
                "back": ast.literal_eval(r["route_back"]),
                "snr_b": ast.literal_eval(r["snr_back"]),
                "ts": int(r["ts"]),
                "hops_taken": hs - hl if hs is not None and hl is not None else -1,
            })
    return rows


def real(nid):
    return nid not in ("", BROADCAST, PLACEHOLDER)


SNR_UNKNOWN = -128  # firmware INT8_MIN sentinel for unknown hops


def is_response(t):
    """A traceroute *response* is a new packet: envelope src = responder,
    dst = original requester, route[] copied unchanged from the request
    (still requester->responder order). Classified by payload shape
    (route_back/snr_back present) or hop accounting (hop counters restart
    at the responder, so a forward-complete row observed at fewer hops than
    its route length can only be a response). Mirrors builder.go D-280."""
    fwd_complete = len(t["snr_t"]) == len(t["route"]) + 1
    return bool(t["back"]) or bool(t["snr_b"]) or (
        fwd_complete and t["hops_taken"] >= 0 and t["hops_taken"] != len(t["route"]))


def leg_links(links, path, snrs, ts):
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        if not real(a) or not real(b) or a == b:
            continue
        e = links[(a, b)]
        e[0] += 1
        e[2].add(ts)
        if i < len(snrs) and snrs[i] not in (0, SNR_UNKNOWN):
            e[1].append(snrs[i])


def links_from_traceroutes(trs):
    """Directed link inventory from both traceroute legs, with correct
    response orientation and evidence-gated endpoints (D-280).
    Returns {(u,v): [obs_count, [snr_raw...], set(obs_ts)]} in radio
    direction u->v."""
    links = defaultdict(lambda: [0, [], set()])
    for t in trs:
        resp = is_response(t)
        requester, responder = (t["dst"], t["src"]) if resp else (t["src"], t["dst"])
        fwd_complete = len(t["snr_t"]) == len(t["route"]) + 1
        # Forward leg: [requester] + route (+ responder only on arrival
        # evidence -- mid-flight rows must not invent the final hop).
        fwd = [requester] + [canon(x) for x in t["route"]]
        if fwd_complete and real(responder):
            fwd.append(responder)
        leg_links(links, fwd, t["snr_t"], t["ts"])
        # Return leg (responses only): [responder] + route_back
        # (+ requester on arrival evidence).
        if resp:
            bp = [responder] + [canon(x) for x in t["back"]]
            if len(t["snr_b"]) == len(t["back"]) + 1 and real(requester):
                bp.append(requester)
            leg_links(links, bp, t["snr_b"], t["ts"])
    return links


def load_presence(trs, hours):
    """presence[node] = set(hour_idx). Union of hourly activity buckets and
    traceroute path appearances, with short-gap fill."""
    t0 = min(t["ts"] for t in trs)
    seen = defaultdict(set)
    with open(f"{DATA}/activity_hourly.tsv") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            # hour string "2026-06-27 12:00:00" -> approximate index vs t0
            import datetime as dt
            h = dt.datetime.fromisoformat(r["hour"]).replace(tzinfo=dt.timezone.utc)
            idx = int((h.timestamp() - t0) // 3600)
            if 0 <= idx < hours:
                seen[r["source_node_id"]].add(idx)
    for t in trs:
        idx = int((t["ts"] - t0) // 3600)
        if not 0 <= idx < hours:
            continue
        for n in [t["src"], t["dst"]] + [canon(x) for x in t["route"]] + [canon(x) for x in t["back"]]:
            if real(n):
                seen[n].add(idx)
    # gap fill
    for n, hs in seen.items():
        ordered = sorted(hs)
        for a, b in zip(ordered, ordered[1:]):
            if b - a <= PRESENCE_GAP_FILL:
                hs.update(range(a + 1, b))
    return seen, t0


# ---------------- world ----------------
class World:
    """Static real topology + real per-hour presence. Link success sampled
    per transmission from an SNR-derived delivery probability."""

    def __init__(self, links, nodes, presence, hours, x0, pmax, pmin, kobs, rev_p, seed):
        self.rng = random.Random(seed)
        self.nodes = nodes
        self.presence = presence
        self.hours = hours
        self.hour = 0
        median_db = st.median(raw / 4 for _, s, _ in links.values() for raw in s) if links else 0
        self.p = {}
        self.snr_db = {}
        out = defaultdict(list)
        for (u, v), (obs, snrs, _ts) in links.items():
            db = (st.mean(snrs) / 4) if snrs else median_db
            self.snr_db[(u, v)] = db
            snr_p = pmin + (pmax - pmin) / (1 + math.exp(-(db - x0) / 4.0))
            # Evidence weight: a link observed once in 7 days is not a
            # dependable link; one observed hundreds of times is.
            w = obs / (obs + kobs)
            self.p[(u, v)] = snr_p * w
            out[u].append(v)
        # Reverse-link prior: an observed u->v implies v->u exists at some
        # discount (LoRa asymmetry), unless v->u was itself observed.
        # rev_p is calibrated against the real route_back completion rate.
        for (u, v) in list(self.p):
            if (v, u) not in self.p and rev_p > 0:
                self.p[(v, u)] = rev_p * self.p[(u, v)]
                self.snr_db[(v, u)] = self.snr_db[(u, v)]
                out[v].append(u)
        self.out = out
        self.relay_ok = {n: nodes.get(n, {}).get("role") != "CLIENT_MUTE" for n in nodes}

    def on(self, n):
        return self.hour in self.presence.get(n, ())

    def can_relay(self, n):
        return self.relay_ok.get(n, True)

    def rx(self, u, v):
        p = self.p.get((u, v))
        return p is not None and self.on(v) and self.rng.random() < p


# ---------------- FLOOD with collision/capture ----------------
def flood(world, src, dst, hop_limit=HOP_LIMIT, collect_parents=False):
    tx = 0
    received = {src: 0}
    parents = {src: None}
    frontier = [src]
    for hop in range(hop_limit):
        arrivals = defaultdict(list)   # v -> [(snr, u)]
        for u in frontier:
            if hop > 0 and not world.can_relay(u):
                continue
            tx += 1
            for v in world.out.get(u, ()):
                if v in received:
                    continue
                if world.rx(u, v):
                    arrivals[v].append((world.snr_db[(u, v)], u))
        nxt = []
        for v, frames in arrivals.items():
            if len(frames) > 1:
                # same-round collision: strongest may capture, rest are lost
                if world.rng.random() >= CAPTURE_P:
                    continue
            u = max(frames)[1]
            received[v] = hop + 1
            parents[v] = u
            nxt.append(v)
        frontier = nxt
        if not frontier:
            break
    return (dst in received), tx, (parents if collect_parents else None), received


# ---------------- PATH (MeshCore-like) ----------------
class PathProto:
    def __init__(self):
        self.routes = {}

    def discover(self, world, src, dst):
        ok, tx, parents, _ = flood(world, src, dst, collect_parents=True)
        if not ok:
            return None, tx
        path = [dst]
        while path[-1] != src:
            path.append(parents[path[-1]])
        path.reverse()
        for i in range(len(path) - 1, 0, -1):   # ACK back along reverse links
            u, v = path[i], path[i - 1]
            got = False
            for _ in range(HOP_RETRIES):
                tx += 1
                if world.rx(u, v):
                    got = True
                    break
            if not got:
                return None, tx
        return path, tx

    def send(self, world, src, dst):
        tx = 0
        key = (src, dst)
        for _ in range(2):
            path = self.routes.get(key)
            if path is None:
                path, dtx = self.discover(world, src, dst)
                tx += dtx
                if path is None:
                    return False, tx
                self.routes[key] = path
            ok = True
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                got = False
                for _ in range(HOP_RETRIES):
                    tx += 1
                    if world.rx(u, v):
                        got = True
                        break
                if not got:
                    ok = False
                    del self.routes[key]
                    break
            if ok:
                return True, tx
        return False, tx


# ---------------- NEXTHOP (Meshtastic 2.6-like) ----------------
class NextHopProto:
    """Per-node next-hop cache toward each destination, learned reactively
    from the parent chain of a successful flood. Unicast chains down the
    caches; any miss or per-hop failure falls back to flood from the holder
    (which re-teaches caches on success). Zero control traffic."""

    def __init__(self):
        self.nh = defaultdict(dict)   # node -> {dst: next_hop}

    def learn(self, parents, src, dst):
        node = dst
        while parents.get(node) is not None:
            prev = parents[node]
            self.nh[prev][dst] = node
            node = prev

    def send(self, world, src, dst):
        tx = 0
        holder = src
        visited = {src}
        while True:
            hop = self.nh[holder].get(dst)
            if hop is None or hop in visited:
                ok, ftx, parents, _ = flood(world, holder, dst, collect_parents=True)
                tx += ftx
                if ok:
                    self.learn(parents, holder, dst)
                else:
                    self.nh[holder].pop(dst, None)
                return ok, tx
            got = False
            for _ in range(HOP_RETRIES):
                tx += 1
                if world.rx(holder, hop):
                    got = True
                    break
            if not got:
                del self.nh[holder][dst]
                ok, ftx, parents, _ = flood(world, holder, dst, collect_parents=True)
                tx += ftx
                if ok:
                    self.learn(parents, holder, dst)
                return ok, tx
            visited.add(hop)
            holder = hop
            if holder == dst:
                return True, tx


# ---------------- GRADCOR ----------------
class GradProto:
    def __init__(self):
        self.grad = {}

    def plant(self, world, dst):
        _, tx, _, received = flood(world, dst, "\x00none")
        self.grad[dst] = {n: (h, 0) for n, h in received.items()}
        return tx

    def age_all(self):
        for d in self.grad:
            self.grad[d] = {n: (h, a + 1) for n, (h, a) in self.grad[d].items()}

    def send(self, world, src, dst):
        tx = 0
        g = self.grad.get(dst)
        src_entry = g.get(src) if g else None
        if g is None or src_entry is None or src_entry[1] >= AGE_DEAD:
            tx += self.plant(world, dst)
            g = self.grad[dst]
            if src not in g:
                return False, tx
        visited = {src}
        holder = src
        chain = [src]
        while tx < MAX_TX_PER_PKT:
            gh, ah = g.get(holder, (10**6, 10**9))
            forwarded = None
            for level in range(3 + GRAD_RETRIES):
                strict = level <= GRAD_RETRIES and ah < AGE_WIDEN
                equal_ok = (not strict) or ah >= AGE_WIDEN
                any_ok = level == 2 + GRAD_RETRIES
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


# ---------------- GRADCOR-R (final spec: no clocks) ----------------
class ReactiveGradProto(GradProto):
    """GradCor-R: wall-clock age removed entirely. Corridor widens purely by
    per-hop failure escalation (strict -> equal -> any); replant only when the
    source has no gradient at all. Age fields are carried but never consulted."""

    def send(self, world, src, dst):
        tx = 0
        g = self.grad.get(dst)
        if g is None or src not in g:
            tx += self.plant(world, dst)
            g = self.grad[dst]
            if src not in g:
                return False, tx
        visited = {src}
        holder = src
        chain = [src]
        while tx < MAX_TX_PER_PKT:
            gh = g.get(holder, (10**6, 10**9))[0]
            forwarded = None
            for level in range(3 + GRAD_RETRIES):
                strict = level <= GRAD_RETRIES
                equal_ok = not strict
                any_ok = level == 2 + GRAD_RETRIES
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


# ---------------- calibration ----------------
def real_hop_hist(trs):
    """Observed forward hop counts, restricted to rows whose forward leg
    demonstrably arrived (len(snr_towards) == len(route)+1). Mid-flight rows
    only prove a lower bound and previously polluted the histogram."""
    h = Counter()
    for t in trs:
        if len(t["snr_t"]) == len(t["route"]) + 1:
            h[len(t["route"]) + 1] += 1
    tot = sum(h.values())
    return {k: v / tot for k, v in h.items()}


def sim_hop_hist(world, samples, rng):
    """Simulated flood hop histogram + round-trip completion rate (a delivered
    forward flood followed by a delivered reverse flood, like a traceroute
    request/reply exchange)."""
    h = Counter()
    fwd_ok = 0
    rt_ok = 0
    for src, dst, hour in samples:
        world.hour = hour
        ok, _, _, received = flood(world, src, dst)
        if ok:
            h[received[dst]] += 1
            fwd_ok += 1
            back, _, _, _ = flood(world, dst, src)
            rt_ok += back
    tot = sum(h.values()) or 1
    rt_rate = rt_ok / max(1, fwd_ok)
    return {k: v / tot for k, v in h.items()}, rt_rate


def calibrate(links, nodes, presence, hours, trs):
    """Grid-search the link model against two empirical anchors:
    1. flood hop-count distribution ~= observed traceroute hop distribution
    2. round-trip completion rate ~= observed fraction of traceroutes
       carrying a route_back (23%)."""
    target = real_hop_hist(trs)
    rt_target = sum(1 for t in trs if t["back"]) / len(trs)
    rng = random.Random(42)
    cands = [t for t in trs if real(t["dst"]) and t["src"] != t["dst"]]
    t0 = min(t["ts"] for t in trs)
    samples = []
    for t in rng.sample(cands, 400):
        samples.append((t["src"], t["dst"], min(hours - 1, int((t["ts"] - t0) // 3600))))
    best = None
    for x0 in (0, 4, 8, 12):
        for pmax in (0.80, 0.90):
            for pmin in (0.10, 0.25):
                for kobs in (2, 5, 10):
                    for rev_p in (0.0, 0.25, 0.5):
                        w = World(links, nodes, presence, hours, x0, pmax, pmin, kobs, rev_p, seed=7)
                        sim, rt = sim_hop_hist(w, samples, rng)
                        keys = set(target) | set(sim)
                        l1 = sum(abs(target.get(k, 0) - sim.get(k, 0)) for k in keys)
                        score = l1 + abs(rt - rt_target)
                        if best is None or score < best[0]:
                            best = (score, x0, pmax, pmin, kobs, rev_p, rt, sim)
    return best, rt_target


# ---------------- experiment ----------------
def pick_pairs(trs, presence, hours, rng, n):
    freq = Counter()
    for t in trs:
        if real(t["dst"]) and t["src"] != t["dst"]:
            freq[(t["src"], t["dst"])] += 1
    # require both endpoints online >= 20 h so conversations actually happen
    cands = [(p, c) for p, c in freq.items()
             if len(presence.get(p[0], ())) >= 20 and len(presence.get(p[1], ())) >= 20]
    pairs, weights = zip(*cands)
    chosen = []
    idx = list(range(len(pairs)))
    while len(chosen) < n and idx:
        i = rng.choices(idx, weights=[weights[j] for j in idx])[0]
        idx.remove(i)
        chosen.append(pairs[i])
    return chosen


def run(seed, links, nodes, presence, hours, trs, x0, pmax, pmin, kobs, rev_p):
    world = World(links, nodes, presence, hours, x0, pmax, pmin, kobs, rev_p, seed)
    rng = random.Random(seed + 999)
    pairs = pick_pairs(trs, presence, hours, rng, PAIRS)
    protos = {"FLOOD": None, "PATH": PathProto(),
              "NEXTHOP": NextHopProto(), "GRADCOR": GradProto(),
              "GRADCOR-R": ReactiveGradProto()}
    stats = {k: [0, 0, 0] for k in protos}
    hourly = {k: defaultdict(lambda: [0, 0]) for k in protos}   # hour -> [dlv, sent]
    for hour in range(hours):
        world.hour = hour
        protos["GRADCOR"].age_all()
        for (s, d) in pairs:
            if not (world.on(s) and world.on(d)):
                continue
            for name, proto in protos.items():
                if name == "FLOOD":
                    ok, tx, _, _ = flood(world, s, d)
                else:
                    ok, tx = proto.send(world, s, d)
                stats[name][0] += ok
                stats[name][1] += 1
                stats[name][2] += tx
                hourly[name][hour][0] += ok
                hourly[name][hour][1] += 1
    return stats, hourly


def main():
    nodes = load_nodes()
    trs = load_traceroutes()
    links = links_from_traceroutes(trs)
    hours = 168
    presence, t0 = load_presence(trs, hours)
    print(f"nodes={len(nodes)} links={len(links)} traceroutes={len(trs)}")

    (score, x0, pmax, pmin, kobs, rev_p, rt_sim, simh), rt_target = calibrate(
        links, nodes, presence, hours, trs)
    print(f"calibration: score={score:.3f}  x0={x0} dB  pmax={pmax} pmin={pmin} "
          f"kobs={kobs} rev_p={rev_p}")
    print(f"round-trip completion: real={rt_target:.2f} sim={rt_sim:.2f}")
    target = real_hop_hist(trs)
    print("hops  real   sim")
    for k in sorted(set(target) | set(simh)):
        print(f"  {k}  {target.get(k, 0):.3f}  {simh.get(k, 0):.3f}")

    agg = {}
    hourly_agg = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for seed in SEEDS:
        stats, hourly = run(seed, links, nodes, presence, hours, trs, x0, pmax, pmin, kobs, rev_p)
        for k, (dlv, snt, tx) in stats.items():
            a = agg.setdefault(k, [0, 0, 0])
            a[0] += dlv
            a[1] += snt
            a[2] += tx
        for k, hh in hourly.items():
            for h, (dlv, snt) in hh.items():
                hourly_agg[k][h][0] += dlv
                hourly_agg[k][h][1] += snt

    print(f"\n{'proto':>8} {'delivery%':>10} {'tx/pkt':>8} {'tx/delivered':>13}")
    results = {}
    for k, (dlv, snt, tx) in agg.items():
        dr = 100 * dlv / max(1, snt)
        results[k] = (dr, tx / max(1, snt), tx / max(1, dlv))
        print(f"{k:>8} {dr:>9.1f} {tx / max(1, snt):>8.1f} {tx / max(1, dlv):>13.1f}")

    with open("results_summary.csv", "w") as f:
        f.write("proto,delivery_pct,tx_per_pkt,tx_per_delivered\n")
        for k, (dr, tpp, tpd) in results.items():
            f.write(f"{k},{dr:.2f},{tpp:.2f},{tpd:.2f}\n")
    with open("results_hourly.csv", "w") as f:
        f.write("proto,hour,delivered,sent\n")
        for k, hh in hourly_agg.items():
            for h in sorted(hh):
                f.write(f"{k},{h},{hh[h][0]},{hh[h][1]}\n")
    print("\nwrote results_summary.csv, results_hourly.csv")
    return results, target, simh, (x0, pmax, pmin, kobs, rev_p)


if __name__ == "__main__":
    main()
