"""Cross-network validation: replay all five protocols on six real production
networks, each with its OWN link-model calibration (grid search against that
network's hop-count distribution and round-trip completion rate).

Usage: python3 experiment_multinet.py
Writes multinet_results.csv and multinet_meta.csv.
"""
import csv
import random
from collections import defaultdict

import sim_norway as S

NETWORKS = [
    ("norway", "data"),
    ("bay-area", "data_networks/bay-area"),
    ("florida", "data_networks/florida"),
    ("socal", "data_networks/socal"),
    ("meshtastic-pt", "data_networks/meshtastic-pt"),
    ("italia", "data_networks/italia"),
]
SEEDS = (1, 2, 3, 4, 5)
HOURS = 168


def run_network(name, datadir):
    S.DATA = datadir
    nodes = S.load_nodes()
    trs = S.load_traceroutes()
    links = S.links_from_traceroutes(trs)
    presence, _ = S.load_presence(trs, HOURS)

    pairs_set = set(links)
    recip = sum(1 for (a, b) in pairs_set if (b, a) in pairs_set)
    rt = sum(1 for t in trs if t["back"]) / len(trs)

    (score, x0, pmax, pmin, kobs, rev_p, rt_sim, _simh), rt_target = S.calibrate(
        links, nodes, presence, HOURS, trs)
    meta = dict(network=name, nodes=len(nodes), traceroutes=len(trs),
                links=len(links), recip_pct=round(100 * recip / max(1, len(links)), 1),
                rt_real=round(rt_target, 3), rt_sim=round(rt_sim, 3),
                cal_score=round(score, 3), x0=x0, pmax=pmax, pmin=pmin,
                kobs=kobs, rev_p=rev_p)
    print(f"[{name}] nodes={len(nodes)} links={len(links)} recip={meta['recip_pct']}% "
          f"cal: x0={x0} pmin={pmin} rev_p={rev_p} score={score:.3f} "
          f"rt {rt_sim:.2f}/{rt_target:.2f}")

    agg = defaultdict(lambda: [0, 0, 0])
    for seed in SEEDS:
        world = S.World(links, nodes, presence, HOURS, x0, pmax, pmin, kobs, rev_p, seed)
        rng = random.Random(seed + 999)
        pairs = S.pick_pairs(trs, presence, HOURS, rng, S.PAIRS)
        protos = {"FLOOD": None, "PATH": S.PathProto(),
                  "NEXTHOP": S.NextHopProto(), "GRADCOR": S.GradProto(),
                  "GRADCOR-R": S.ReactiveGradProto()}
        for hour in range(HOURS):
            world.hour = hour
            protos["GRADCOR"].age_all()
            protos["GRADCOR-R"].age_all()
            for (s, d) in pairs:
                if not (world.on(s) and world.on(d)):
                    continue
                for pname, proto in protos.items():
                    if pname == "FLOOD":
                        ok, tx, _, _ = S.flood(world, s, d)
                    else:
                        ok, tx = proto.send(world, s, d)
                    a = agg[pname]
                    a[0] += ok
                    a[1] += 1
                    a[2] += tx
    rows = []
    for pname, (dlv, snt, tx) in agg.items():
        rows.append(dict(network=name, proto=pname,
                         delivery_pct=round(100 * dlv / max(1, snt), 2),
                         tx_per_pkt=round(tx / max(1, snt), 2),
                         tx_per_delivered=round(tx / max(1, dlv), 2),
                         sent=snt))
        print(f"  {pname:10} {rows[-1]['delivery_pct']:6.1f}%  "
              f"{rows[-1]['tx_per_delivered']:8.1f} tx/dlv")
    return meta, rows


if __name__ == "__main__":
    metas, results = [], []
    for name, datadir in NETWORKS:
        meta, rows = run_network(name, datadir)
        metas.append(meta)
        results.extend(rows)
    with open("multinet_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    with open("multinet_meta.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(metas[0].keys()))
        w.writeheader()
        w.writerows(metas)
    print("\nwrote multinet_results.csv, multinet_meta.csv")
