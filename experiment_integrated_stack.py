"""End-to-end integration test for every mechanism in Figure 24.

Three policies receive identical production-shaped traffic:

  MANAGED CURRENT
    Broadcast and addressed packets use managed flood. Addressed packets with
    want_ack receive up to three end-to-end retries (current ReliableRouter-like
    behaviour).

  INTEGRATED FAST
    Broadcast: relay pressure + message-class cap + utilization setpoint.
    Addressed: GradCor-R with fallback-flood cold start, local rescue flood,
    and the same three end-to-end retries when want_ack is set.

  INTEGRATED FAST+PIVOT
    Same as integrated fast but replaces relay pressure with the PIVOT backbone
    (64-bit digest) for broadcast relay election.

  INTEGRATED FULL
    INTEGRATED FAST plus 24-hour custody for failed want_ack packets.

Canonical study-week traffic shares are replayed:
  78.93% BULK broadcast, 0.25% STANDARD broadcast,
  14.17% want_ack addressed, 6.65% best-effort addressed.
There was no historical ASSURED marker, so source-reflood ASSURED broadcasts
are implemented but not injected. This distinction matters: the reliability
envelope is optional policy, not free capacity.
"""
import csv
import random
import statistics
from collections import Counter, defaultdict, deque

import experiment_capacity as C
import sim_norway as S
from experiment_pivot import BloomDigest, PivotFlood

BULK_SHARE = 40960 / 51892
STANDARD_SHARE = 130 / 51892
ACKED_SHARE = 7352 / 51892
BEST_EFFORT_SHARE = 3450 / 51892

POLICIES = ("managed current", "integrated fast", "integrated fast+pivot",
            "integrated full")
SCALES = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0)
SEEDS = (1, 2, 3)
SIM_HOURS = 54
UTIL_START = 30
COHORT_START = 6
COHORT_END = 30
CUSTODY_HOURS = 24
ACK_RETRIES = 3
SETPOINT_TARGET = 0.22
RUNGS = [(2, 1, 1), (1, None, 1), (0, None, 2),
         (0, None, 3), (0, None, 4), (0, None, 5)]


class PivotBroadcast:
    """PIVOT backbone + message-class persistence + utilization setpoint."""

    def __init__(self, digest_cls=BloomDigest):
        self.pivot = PivotFlood(digest_cls)
        self.rung = defaultdict(lambda: 3)

    def set_util(self, util):
        for node, value in util.items():
            self.pivot.state.set_util(node, value)
            if value > SETPOINT_TARGET:
                self.rung[node] = max(0, self.rung[node] - 1)
            elif value < 0.8 * SETPOINT_TARGET:
                self.rung[node] = min(len(RUNGS) - 1, self.rung[node] + 1)

    def flood(self, world, src, message_class):
        import experiment_pivot as P
        class_r = {"BULK": 1, "STANDARD": 2, "ASSURED": 3}[message_class]
        budget_r = RUNGS[self.rung.get(src, 3)][2]
        old_persist = P.PIVOT_PERSIST
        P.PIVOT_PERSIST = min(class_r, budget_r)
        repeats = 2 if message_class == "ASSURED" else 1
        total_tx = 0
        all_received = {}
        all_txers = []
        for _ in range(repeats):
            tx, received, txers = self.pivot.flood(
                world, src, relay_ok=lambda n: world.on(n))
            total_tx += tx
            all_received.update(received)
            all_txers.extend(txers)
        P.PIVOT_PERSIST = old_persist
        return total_tx, all_received, all_txers


def flood_traced(world, src, dst):
    ok, tx, parents, received = S.flood(
        world, src, dst, collect_parents=True)
    return ok, tx, list(C.transmitting_nodes(world, received)), parents, received


def charge(heard, world, transmitters):
    for node in transmitters:
        heard[node] += 1
        for neighbour in world.out.get(node, ()):
            if world.on(neighbour):
                heard[neighbour] += 1


class TracedRescueGrad:
    """Fallback cold start + GradCor-R walk + local rescue, all traced."""

    def __init__(self):
        self.grad = {}

    def _stamp(self, dst, chain, parents, holder):
        path = [dst]
        while parents.get(path[-1]) is not None and path[-1] != holder:
            path.append(parents[path[-1]])
        path.reverse()
        full = chain[:-1] + path
        gradient = self.grad.setdefault(dst, {})
        for i, node in enumerate(full):
            gradient[node] = (len(full) - 1 - i, 0)

    def send(self, world, src, dst):
        gradient = self.grad.get(dst)
        if gradient is None or src not in gradient:
            ok, tx, txers, parents, _ = flood_traced(world, src, dst)
            if ok:
                self._stamp(dst, [src], parents, src)
            return ok, tx, txers

        tx = 0
        txers = []
        visited = {src}
        holder = src
        chain = [src]
        while tx < S.MAX_TX_PER_PKT:
            holder_gradient = gradient.get(holder, (10**6, 10**9))[0]
            forwarded = None
            for level in range(3 + S.GRAD_RETRIES):
                strict = level <= S.GRAD_RETRIES
                equal_ok = not strict
                any_ok = level == 2 + S.GRAD_RETRIES
                tx += 1
                txers.append(holder)
                candidates = []
                for node in world.out.get(holder, ()):
                    if node in visited or not world.rx(holder, node):
                        continue
                    if node == dst:
                        for i, path_node in enumerate(chain + [dst]):
                            gradient[path_node] = (len(chain) - i, 0)
                        return True, tx, txers
                    if not world.can_relay(node):
                        continue
                    node_gradient = gradient.get(node, (10**6, 10**9))[0]
                    if (node_gradient < holder_gradient
                            or (equal_ok and node_gradient == holder_gradient)
                            or any_ok):
                        candidates.append((node_gradient, node))
                if candidates:
                    forwarded = min(candidates)[1]
                    break
            if forwarded is None:
                ok, rescue_tx, rescue_by, parents, _ = flood_traced(
                    world, holder, dst)
                tx += rescue_tx
                txers.extend(rescue_by)
                if ok:
                    self._stamp(dst, chain, parents, holder)
                return ok, tx, txers
            visited.add(forwarded)
            chain.append(forwarded)
            holder = forwarded
        return False, tx, txers


class IntegratedBroadcast:
    """Relay pressure, message classes and setpoint in one flood."""

    def __init__(self):
        self.c_est = {}
        self.novelty = {}
        self.rung = defaultdict(lambda: 3)

    def set_util(self, util):
        for node, value in util.items():
            if value > SETPOINT_TARGET:
                self.rung[node] = max(0, self.rung[node] - 1)
            elif value < 0.8 * SETPOINT_TARGET:
                self.rung[node] = min(len(RUNGS) - 1, self.rung[node] + 1)

    def pressure(self, node):
        copies = self.c_est.get(node, 2.0)
        crowd = max(0.05, min(1.0, (2.0 - copies) / 2.0 + 0.5))
        return max(crowd, self.novelty.get(node, 0.5))

    def policy(self, node):
        pressure = self.pressure(node)
        if pressure >= 0.7:
            slot, cancel, persistence = 0, None, 3
        elif pressure >= 0.35:
            slot, cancel, persistence = 1, 2, 2
        else:
            slot, cancel, persistence = 2, 1, 1
        budget_slot, budget_cancel, budget_r = RUNGS[self.rung[node]]
        slot = max(slot, budget_slot)
        if budget_cancel is not None:
            cancel = budget_cancel if cancel is None else min(cancel, budget_cancel)
        return slot, cancel, persistence, budget_r

    def observe(self, node, copies):
        old = self.c_est.get(node, 2.0)
        self.c_est[node] = old + 0.15 * (copies - old)

    def observe_novelty(self, node, novel):
        old = self.novelty.get(node, 0.5)
        self.novelty[node] = old + 0.25 * ((1.0 if novel else 0.0) - old)

    def flood_once(self, world, src, message_class):
        class_r = {"BULK": 1, "STANDARD": 2, "ASSURED": 3}[message_class]
        txers = []
        received = {src: 0}
        frontier = [src]
        for hop in range(S.HOP_LIMIT):
            copies = defaultdict(int)
            heard_relays = defaultdict(int)
            arrivals = defaultdict(list)
            decoded_by = defaultdict(set)
            relayers = [node for node in frontier
                        if hop == 0 or world.on(node)]

            def transmit(node, slot):
                txers.append(node)
                for receiver in world.out.get(node, ()):
                    if not world.rx(node, receiver):
                        continue
                    copies[receiver] += 1
                    if receiver in relayers:
                        heard_relays[receiver] += 1
                    if receiver not in received:
                        arrivals[receiver].append((slot, node))
                        decoded_by[node].add(receiver)

            fired = []
            for slot in range(3):
                for node in relayers:
                    node_slot, cancel_at, _, _ = self.policy(node)
                    if node_slot != slot or node in fired:
                        continue
                    if cancel_at is not None and heard_relays[node] >= cancel_at:
                        continue
                    transmit(node, slot)
                    fired.append(node)

            nxt = []
            for receiver, frames in arrivals.items():
                by_slot = defaultdict(list)
                for slot, node in frames:
                    by_slot[slot].append(node)
                first = min(by_slot)
                if (len(by_slot[first]) > 1
                        and world.rng.random() >= S.CAPTURE_P
                        and not any(slot > first for slot in by_slot)):
                    continue
                received[receiver] = hop + 1
                nxt.append(receiver)

            onward_relays = set(nxt)
            for node in fired:
                _, _, pressure_r, budget_r = self.policy(node)
                persistence = min(class_r, pressure_r, budget_r)
                tries = 1
                while tries < persistence and not (decoded_by[node] & onward_relays):
                    transmit(node, 3)
                    tries += 1
                    for receiver in list(arrivals):
                        if receiver not in received:
                            received[receiver] = hop + 1
                            nxt.append(receiver)
                            onward_relays.add(receiver)

            for node, count in copies.items():
                self.observe(node, count)
            for node in fired:
                self.observe_novelty(node, bool(decoded_by[node]))
            frontier = nxt
            if not frontier:
                break
        return len(txers), received, txers

    def flood(self, world, src, message_class):
        repeats = 2 if message_class == "ASSURED" else 1
        total_tx = 0
        all_received = {}
        all_txers = []
        for _ in range(repeats):
            tx, received, txers = self.flood_once(world, src, message_class)
            total_tx += tx
            all_received.update(received)
            all_txers.extend(txers)
        return total_tx, all_received, all_txers


def pair_counts(traceroutes):
    counts = Counter()
    for trace in traceroutes:
        pair = (trace["src"], trace["dst"])
        if S.real(pair[0]) and S.real(pair[1]) and pair[0] != pair[1]:
            counts[pair] += 1
    return counts


def make_schedule(presence, pairs, scale, seed):
    rng = random.Random(seed + 8800)
    offered = round(C.P95_PACKETS_PER_HOUR * scale)
    schedule = []
    for step in range(SIM_HOURS):
        hour = ((seed - 1) * 56 + step) % 168
        online = [node for node in presence if hour in presence[node]]
        active_pairs = [(pair, weight) for pair, weight in pairs.items()
                        if pair[0] in online and pair[1] in online]
        values = [pair for pair, _ in active_pairs]
        weights = [weight for _, weight in active_pairs]
        events = []
        for _ in range(offered):
            draw = rng.random()
            if draw < BULK_SHARE:
                events.append(("broadcast", "BULK", rng.choice(online), None))
            elif draw < BULK_SHARE + STANDARD_SHARE:
                events.append(("broadcast", "STANDARD", rng.choice(online), None))
            else:
                src, dst = rng.choices(values, weights=weights)[0]
                acked = draw < BULK_SHARE + STANDARD_SHARE + ACKED_SHARE
                events.append(("unicast", "ACKED" if acked else "BEST", src, dst))
        schedule.append((hour, events))
    return schedule


def send_flood_reliable(world, src, dst, retries):
    total_tx = 0
    txers = []
    for _ in range(1 + retries):
        ok, tx, attempt_by, _, _ = flood_traced(world, src, dst)
        total_tx += tx
        txers.extend(attempt_by)
        if ok:
            return True, total_tx, txers
    return False, total_tx, txers


def send_grad_reliable(proto, world, src, dst, retries):
    total_tx = 0
    txers = []
    for _ in range(1 + retries):
        ok, tx, attempt_by = proto.send(world, src, dst)
        total_tx += tx
        txers.extend(attempt_by)
        if ok:
            return True, total_tx, txers
    return False, total_tx, txers


def run_policy(links, nodes, presence, schedule, policy, seed):
    world = S.World(links, nodes, presence, 168, seed=seed, **C.PARAMS)
    util = defaultdict(float)
    base_rx = world.rx
    gradient = TracedRescueGrad()
    broadcast = (PivotBroadcast() if policy == "integrated fast+pivot"
                 else IntegratedBroadcast())
    pending = deque()
    node_hours = []
    tx_measured = offered_measured = 0
    cohort_sent = cohort_delivered = 0
    broadcast_receivers = broadcast_sent = 0

    def rx(u, v):
        if not base_rx(u, v):
            return False
        return world.rng.random() >= min(0.6, 0.8 * util[v])

    world.rx = rx

    for step, (hour, events) in enumerate(schedule):
        world.hour = hour
        online = [node for node in presence if world.on(node)]
        heard = defaultdict(int)
        measure_util = step >= UTIL_START

        if policy == "integrated full":
            for _ in range(len(pending)):
                src, dst, born, in_cohort = pending.popleft()
                if step - born > CUSTODY_HOURS:
                    continue
                if not (world.on(src) and world.on(dst)):
                    pending.append((src, dst, born, in_cohort))
                    continue
                ok, tx, txers = send_grad_reliable(
                    gradient, world, src, dst, ACK_RETRIES)
                charge(heard, world, txers)
                if measure_util:
                    tx_measured += tx
                if ok:
                    if in_cohort:
                        cohort_delivered += 1
                else:
                    pending.append((src, dst, born, in_cohort))

        for kind, message_class, src, dst in events:
            in_cohort = COHORT_START <= step < COHORT_END

            if kind == "broadcast":
                if policy == "managed current":
                    _, tx, txers, _, received = flood_traced(
                        world, src, "\x00none")
                else:
                    tx, received, txers = broadcast.flood(
                        world, src, message_class)
                ok = True
                if measure_util:
                    broadcast_sent += 1
                    broadcast_receivers += len(received)
            else:
                if in_cohort:
                    cohort_sent += 1
                retries = ACK_RETRIES if message_class == "ACKED" else 0
                if policy == "managed current":
                    ok, tx, txers = send_flood_reliable(
                        world, src, dst, retries)
                else:
                    ok, tx, txers = send_grad_reliable(
                        gradient, world, src, dst, retries)
                if (policy == "integrated full" and message_class == "ACKED"
                        and not ok):
                    pending.append((src, dst, step, in_cohort))

            charge(heard, world, txers)
            if measure_util:
                tx_measured += tx
                offered_measured += 1
            if kind == "unicast" and in_cohort and ok:
                cohort_delivered += 1

        for node in online:
            current = heard[node] * C.T_TX / C.HOUR_SECONDS
            util[node] += C.EWMA_ALPHA * (current - util[node])
        if policy != "managed current":
            broadcast.set_util(util)
        if measure_util:
            node_hours.extend(util[node] for node in online)

    return {
        "mean_util": 100 * statistics.mean(node_hours),
        "p95_util": 100 * C.percentile(node_hours, 0.95),
        "p99_util": 100 * C.percentile(node_hours, 0.99),
        "tx_per_offered": tx_measured / max(1, offered_measured),
        "cohort_delivery": 100 * cohort_delivered / max(1, cohort_sent),
        "receivers_per_broadcast": broadcast_receivers / max(1, broadcast_sent),
        "pending_at_end": len(pending),
    }


def main():
    nodes = S.load_nodes()
    traceroutes = S.load_traceroutes()
    links = S.links_from_traceroutes(traceroutes)
    presence, _ = S.load_presence(traceroutes, 168)
    pairs = pair_counts(traceroutes)
    rows = []

    print(f"{'policy':17} {'scale':>5} {'nodes':>6} {'p95':>7} {'p99':>7} "
          f"{'tx/off':>7} {'delivery':>9} {'rx/bcast':>9} {'queued':>7}")
    for scale in SCALES:
        schedules = {
            seed: make_schedule(presence, pairs, scale, seed)
            for seed in SEEDS
        }
        for policy in POLICIES:
            runs = [
                run_policy(links, nodes, presence, schedules[seed], policy, seed)
                for seed in SEEDS
            ]
            row = {
                "policy": policy,
                "scale": scale,
                "equiv_nodes": round(C.KNOWN_NODES * scale),
                "equiv_active_per_hour": round(C.MEAN_ACTIVE_SOURCES * scale),
                "packets_per_hour": round(C.P95_PACKETS_PER_HOUR * scale),
            }
            for key in runs[0]:
                row[key] = round(statistics.mean(run[key] for run in runs), 2)
            rows.append(row)
            print(f"{policy:17} {scale:5.2f} {row['equiv_nodes']:6d} "
                  f"{row['p95_util']:6.1f}% {row['p99_util']:6.1f}% "
                  f"{row['tx_per_offered']:7.1f} {row['cohort_delivery']:8.1f}% "
                  f"{row['receivers_per_broadcast']:9.1f} "
                  f"{row['pending_at_end']:7.0f}")

    with open("integrated_stack_capacity.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print("\n25% utilization crossings:")
    for policy in POLICIES:
        policy_rows = [row for row in rows if row["policy"] == policy]
        p99 = C.crossing(policy_rows, "p99_util")
        p95 = C.crossing(policy_rows, "p95_util")
        hotspot = f"{C.KNOWN_NODES*p99:.0f}" if p99 else "below first point"
        broad = f"{C.KNOWN_NODES*p95:.0f}" if p95 else "outside sweep"
        print(f"  {policy:17} hotspot {hotspot}; broad {broad}")
    print("wrote integrated_stack_capacity.csv")


if __name__ == "__main__":
    main()
