# GradCor: Gradient-Corridor Anycast Routing, Evaluated on Real Meshtastic Networks

Reproduction package for the paper **"An Empirically Calibrated Evaluation of Flood,
Source-Path, Next-Hop and Gradient-Corridor Forwarding on Real Meshtastic Networks"**
([`paper.pdf`](paper.pdf) / [`paper.html`](paper.html)).

GradCor is a proposed LoRa mesh routing method: one byte of state per active destination,
receiver-side anycast forwarding, no hop limit. Replayed on the real 7-day topology of the
Norwegian Meshtastic mesh (499 nodes, 1,423 directed links from 18,919 production traceroutes),
its final clock-free form (**GradCor-R**) delivers **2× the unicast packets of managed flooding
at 3.3× less airtime per delivered packet**. The ranking reproduces on five further production
networks.

| Protocol | Delivery % | Tx / delivered |
|---|---:|---:|
| FLOOD (hop limit 7) | 25.3 | 71.0 |
| PATH (stylized source routing) | 4.0 | 473.2 |
| NEXTHOP (Meshtastic 2.6-style cache) | 30.4 | 59.9 |
| GRADCOR v1 (age-widened corridor) | 48.6 | 21.4 |
| **GRADCOR-R (final spec, no clocks)** | **50.7** | **21.3** |

## Contents

| Path | What it is |
|---|---|
| `paper.pdf`, `paper.html` | The paper (HTML is the source; PDF is rendered from it) |
| `sim_norway.py` | Trace-driven replay: link extraction, calibration, all five protocols |
| `experiment_widening.py` | Clock ablation (hazard curve, threshold sweeps, reactive/adaptive variants) |
| `experiment_asymmetry.py` | Resilience to gradients that underestimate true forward distance |
| `experiment_multinet.py` | Cross-network validation on six networks, per-network calibration |
| `fig_*.py`, `plot_results.py` | Figure generators (all figures in the paper) |
| `data/` | Norway exports: traceroutes, hourly node activity, node roles |
| `data_networks/` | Same exports for Bay Area, Florida, SoCal, Portugal, Italia |
| `results_summary.csv`, `results_hourly.csv`, `multinet_results.csv`, `multinet_meta.csv` | Result tables |

## Reproduce

Python 3.10+; figures need `matplotlib`.

```bash
python3 sim_norway.py             # headline five-protocol replay (~20 s)
python3 experiment_widening.py    # clock ablation
python3 experiment_asymmetry.py   # asymmetry resilience
python3 experiment_multinet.py    # six-network validation (~2 min)
python3 fig_paper.py && python3 fig_method.py && python3 fig_summary.py \
  && python3 fig_plant.py && python3 fig_ablation.py && python3 fig_multinet.py
```

Render the PDF (any Chromium browser):

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --no-pdf-header-footer --print-to-pdf=paper.pdf paper.html
```

Everything is deterministic (fixed seeds); the scripts print the tables that appear in the
paper.

## Data notes

- Exports come from [RelayMesh](https://www.relaymonkey.com/relaymesh/)'s production ingestion of public Meshtastic MQTT traffic,
  window 2026-06-27 → 2026-07-04 (UTC).
- Ground truth is what MQTT gateways heard: absolute delivery rates are model outputs, not
  field measurements — rankings and ratios are the robust findings (see paper §8, Threats to
  validity).
- Node identifiers and names appear as broadcast publicly by the nodes themselves.
