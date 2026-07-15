"""Capacity: today's managed flood versus the deployable improved stack.

Observed traffic maps onto the paper's mechanisms as follows:
  - 79.2% broadcast, overwhelmingly periodic POSITION/TELEMETRY/NODEINFO:
    BULK class, ordinary k=1 flood. Relay pressure converges to this same point
    on sparse Norway and the class cap prevents setpoint from adding persistence.
  - 20.8% addressed: GradCor-R instead of managed flood.

The baseline managed-floods both shares. Both policies receive the same event
schedule at every scale. GradCor-R transmissions are traced to their holder;
planting-flood transmitters are reconstructed from the flood receive map, so
local utilization is charged by the same neighbourhood rule as the baseline.
"""
import csv
import random
import statistics
from collections import Counter, defaultdict

import experiment_capacity as C
import sim_norway as S
from experiment_alltoall import bfs_cover


class TracedReactiveGrad(S.ReactiveGradProto):
    """ReactiveGradProto with the transmitter sequence exposed."""

    def plant_traced(self, world, dst):
        _, tx, _, received = S.flood(world, dst, "\x00none")
        self.grad[dst] = {n: (h, 0) for n, h in received.items()}
        return tx, list(C.transmitting_nodes(world, received))

    def send_traced(self, world, src, dst):
        tx = 0
        txers = []
        g = self.grad.get(dst)
        if g is None or src not in g:
            planted, planted_by = self.plant_traced(world, dst)
            tx += planted
            txers.extend(planted_by)
            g = self.grad[dst]
            if src not in g:
                return False, tx, txers

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
                txers.append(holder)
                candidates = []
                for node in world.out.get(holder, ()):
                    if node in visited or not world.rx(holder, node):
                        continue
                    if node == dst:
                        for i, path_node in enumerate(chain + [dst]):
                            g[path_node] = (len(chain) - i, 0)
                        return True, tx, txers
                    if not world.can_relay(node):
                        continue
                    gradient = g.get(node, (10**6, 10**9))[0]
                    if gradient < gh or (equal_ok and gradient == gh) or any_ok:
                        candidates.append((gradient, node))
                if candidates:
                    forwarded = min(candidates)[1]
                    break
            if forwarded is None:
                return False, tx, txers
            visited.add(forwarded)
            chain.append(forwarded)
            holder = forwarded
        return False, tx, txers


def observed_pairs(traceroutes):
    counts = Counter()
    for trace in traceroutes:
        pair = (trace["src"], trace["dst"])
        if S.real(pair[0]) and S.real(pair[1]) and pair[0] != pair[1]:
            counts[pair] += 1
    return counts


def event_schedule(presence, pair_counts, scale, seed):
    """Same deterministic events are replayed under both policies."""
    rng = random.Random(seed + 7700)
    offered = round(C.P95_PACKETS_PER_HOUR * scale)
    hour_offset = (seed - 1) * 56
    schedule = []
    for step in range(C.HOURS):
        hour = (hour_offset + step) % 168
        online = [n for n in presence if hour in presence[n]]
        pairs = [(pair, weight) for pair, weight in pair_counts.items()
                 if pair[0] in online and pair[1] in online]
        pair_values = [pair for pair, _ in pairs]
        pair_weights = [weight for _, weight in pairs]
        events = []
        for _ in range(offered):
            if rng.random() < C.BROADCAST_SHARE or not pair_values:
                events.append(("broadcast", rng.choice(online), None))
            else:
                src, dst = rng.choices(pair_values, weights=pair_weights)[0]
                events.append(("unicast", src, dst))
        schedule.append((hour, events))
    return schedule


def charge(heard, world, transmitters):
    for node in transmitters:
        heard[node] += 1
        for neighbour in world.out.get(node, ()):
            if world.on(neighbour):
                heard[neighbour] += 1


def run_policy(links, nodes, presence, schedule, policy, seed):
    world = S.World(links, nodes, presence, 168, seed=seed, **C.PARAMS)
    util = defaultdict(float)
    base_rx = world.rx
    grad = TracedReactiveGrad()

    def rx(u, v):
        if not base_rx(u, v):
            return False
        return world.rng.random() >= min(0.6, 0.8 * util[v])

    world.rx = rx
    node_hours = []
    tx_total = packet_total = 0
    broadcast_covered = broadcast_reachable = 0
    unicast_delivered = unicast_sent = 0

    for step, (hour, events) in enumerate(schedule):
        world.hour = hour
        online = [n for n in presence if world.on(n)]
        heard = defaultdict(int)
        measure = step >= C.WARMUP_HOURS

        for kind, src, dst in events:
            if kind == "broadcast" or policy == "managed flood":
                target = "\x00none" if kind == "broadcast" else dst
                ok, tx, _, received = S.flood(world, src, target)
                transmitters = list(C.transmitting_nodes(world, received))
            else:
                ok, tx, transmitters = grad.send_traced(world, src, dst)
                received = {}
            charge(heard, world, transmitters)

            if not measure:
                continue
            packet_total += 1
            tx_total += tx
            if kind == "broadcast":
                reach = bfs_cover(world, src)
                broadcast_covered += len(set(received) & reach)
                broadcast_reachable += len(reach)
            else:
                unicast_sent += 1
                unicast_delivered += ok

        for node in online:
            current = heard[node] * C.T_TX / C.HOUR_SECONDS
            util[node] += C.EWMA_ALPHA * (current - util[node])
        if measure:
            node_hours.extend(util[node] for node in online)

    return {
        "mean_util": 100 * statistics.mean(node_hours),
        "p95_util": 100 * C.percentile(node_hours, 0.95),
        "p99_util": 100 * C.percentile(node_hours, 0.99),
        "tx_per_packet": tx_total / max(1, packet_total),
        "broadcast_coverage": 100 * broadcast_covered / max(1, broadcast_reachable),
        "unicast_delivery": 100 * unicast_delivered / max(1, unicast_sent),
    }


def main():
    nodes = S.load_nodes()
    traceroutes = S.load_traceroutes()
    links = S.links_from_traceroutes(traceroutes)
    presence, _ = S.load_presence(traceroutes, 168)
    pair_counts = observed_pairs(traceroutes)
    rows = []

    print(f"{'policy':16} {'scale':>5} {'nodes':>6} {'p95 u':>7} {'p99 u':>7} "
          f"{'tx/msg':>7} {'bcast cov':>10} {'unicast':>8}")
    for scale in C.SCALES:
        schedules = {
            seed: event_schedule(presence, pair_counts, scale, seed)
            for seed in C.SEEDS
        }
        for policy in ("managed flood", "improved stack"):
            runs = [
                run_policy(links, nodes, presence, schedules[seed], policy, seed)
                for seed in C.SEEDS
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
            print(f"{policy:16} {scale:5.2f} {row['equiv_nodes']:6d} "
                  f"{row['p95_util']:6.1f}% {row['p99_util']:6.1f}% "
                  f"{row['tx_per_packet']:7.1f} {row['broadcast_coverage']:9.1f}% "
                  f"{row['unicast_delivery']:7.1f}%")

    with open("capacity_compare.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print("\n25% utilization crossings:")
    for policy in ("managed flood", "improved stack"):
        policy_rows = [row for row in rows if row["policy"] == policy]
        p99 = C.crossing(policy_rows, "p99_util")
        p95 = C.crossing(policy_rows, "p95_util")
        print(f"  {policy:16} hotspot ~{C.KNOWN_NODES*p99:.0f} nodes; "
              f"broad ~{C.KNOWN_NODES*p95:.0f} nodes")
    print("wrote capacity_compare.csv")


if __name__ == "__main__":
    main()
