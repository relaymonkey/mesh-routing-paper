"""Echo-persistent flooding at depth: can broadcast be fixed the same way
the corridor was?

Per-hop persistence applied to the flood: a relay retransmits (up to R
times) until it overhears an onward arrival -- the same implicit-ack
primitive as GradCor's contention race and the managed flood's
overhear-cancellation, with the policy inverted (repeat-until-heard
instead of mute-when-heard). Measured on the synthetic braids of
experiment_depth.py. R=1 is today's flood.
"""
from collections import defaultdict

from experiment_depth import BraidWorld

PACKETS = 300


def flood_persist(world, src, R, hop_limit=10**6):
    """Round-based flood; relay u retransmits up to R times, stopping once
    one of its transmissions produced an arrival at a farther position
    (its implicit ack)."""
    def pos(n):
        return int(n[1:5], 16)

    tx = 0
    received = {src: 0}
    frontier = [src]
    for hop in range(hop_limit):
        arrivals = defaultdict(list)
        for u in frontier:
            got_echo = False
            for _ in range(R):
                tx += 1
                for v in world.out.get(u, ()):
                    if v in received:
                        continue
                    if world.rx(u, v):
                        arrivals[v].append(u)
                        if pos(v) > pos(u):
                            got_echo = True
                if got_echo:
                    break
        nxt = []
        for v in arrivals:
            received[v] = hop + 1
            nxt.append(v)
        frontier = nxt
        if not frontier:
            break
    return (world.dst in received), tx


if __name__ == "__main__":
    print(f"{'d':>4} {'w':>2} {'p':>4} {'R':>2} {'delivery to far end':>20} {'tx':>8}")
    for depth in (20, 50, 200):
        for width, p in ((2, 0.5), (2, 0.7), (1, 0.7)):
            for R in (1, 3, 5):
                world = BraidWorld(depth, width, p, seed=7)
                dlv = tx = 0
                for _ in range(PACKETS):
                    ok, t = flood_persist(world, world.src, R)
                    dlv += ok
                    tx += t
                print(f"{depth:>4} {width:>2} {p:>4} {R:>2} "
                      f"{100*dlv/PACKETS:>19.1f}% {tx/PACKETS:>8.1f}")
        print()
