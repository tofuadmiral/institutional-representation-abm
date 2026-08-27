# Institutional Representation ABM

*How democratic institutions mediate the translation of citizen preferences into legislative outcomes.*

[![CI](https://github.com/tofuadmiral/institutional-representation-abm/actions/workflows/ci.yml/badge.svg)](https://github.com/tofuadmiral/institutional-representation-abm/actions/workflows/ci.yml)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-2608.24554-b31b1b.svg)](https://arxiv.org/abs/2608.24554)
[![Tests](https://img.shields.io/badge/tests-80%20passing-brightgreen.svg)](tests/)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://institutional-representation-abm.streamlit.app/)

<p align="center">
  <img src="docs/figures/forest_passage.png" width="85%" alt="Passage rates across four institutions and four scenarios (N=200 seeds)">
</p>

<p align="center">
  <b>🔗 <a href="https://institutional-representation-abm.streamlit.app/">Live interactive demo</a></b>
  &nbsp;·&nbsp;
  <b>📄 <a href="https://arxiv.org/abs/2608.24554">Paper (arXiv:2608.24554)</a></b>
  &nbsp;·&nbsp;
  <b>📋 <a href="paper/poster.pdf">Conference poster (A0)</a></b>
  &nbsp;·&nbsp;
  <b>📝 <a href="docs/blog_draft.pdf">Blog post (PDF)</a></b>
  &nbsp;·&nbsp;
  <a href="docs/PHASE_H_NOTES.md">Phase H notes</a>
</p>

This repository implements a Mesa-based agent-based model that compares four democratic legislative institutions (pure parliamentary, pure republican, premier-presidential, president-parliamentary) across four scenarios (baseline, fragmented, polarised, small-system) with a full statistical harness (N=200 seeds, bootstrap CIs, Morris and Sobol sensitivity, mechanism ablations).

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v

# full four-institution comparison at N=200 seeds (~5 minutes on 8 cores)
python -m experiments.multiseed_comparison --scenarios all --seeds 200 --output results/main/

# hung-parliament variant comparison (Phase H decomposition)
python -m experiments.hung_parliament --seeds 200 --output results/phase_h/

# Morris + Sobol sensitivity analysis
python -m experiments.sensitivity --output results/main/

# mechanism ablations (committees / discipline / veto)
python -m experiments.ablation --scenarios baseline fragmented polarized --seeds 200 --output results/main/

# passage-representation tradeoff figure
python -m experiments.representation --seeds 200 --output results/phase_g/

# discipline-default robustness sweep
python -m experiments.discipline_robustness --seeds 100 --output results/phase_f/

# interactive UI with sliders over every config parameter
# (or use the hosted version: https://institutional-representation-abm.streamlit.app/)
streamlit run streamlit_app/app.py
```

## Headline findings

### 1. Fragmented parliaments collapse only when oppositions cohere

Under fragmentation, no coalition can form, and parliamentary passage collapses to 0.05%. Formation failure by itself doesn't explain it: a new `hung_parliament_behavior` flag separates two readings of a hung parliament.

| Institution | Cohesive obstruction | Personal vote | Δ |
|---|---:|---:|---:|
| Parliamentary | 0.0005 | **0.464** | +0.464 |
| Premier-presidential | 0.013 | 0.333 | +0.320 |
| President-parliamentary | 0.086 | 0.086 | 0 |
| Republican | 0.448 | 0.448 | 0 |

With MPs voting personally (the issue-by-issue-majority world of Strøm-style minority governance), fragmented parliamentary passage is statistically indistinguishable from the presidential benchmark (46.4% vs 44.8%). Collapse requires cohesive obstruction — every MP whipped against all business, the anti-system pattern of polarised blocs like Weimar's. The flag binds only where the coalition list can be empty, so the other six cells are bit-identical across variants.

The `no_discipline` ablation corroborates from an independent direction: zeroing the whip everywhere restores passage to 46.7%, and the rescue magnitude falls monotonically across the four institutions in the order of their dependence on parliamentary-majority government formation:

| Institution | Passage @ fragmented | `no_discipline` Δ |
|---|---:|---:|
| Parliamentary | 0.0005 | **+0.466** |
| Premier-presidential | 0.013 | +0.312 |
| President-parliamentary | 0.086 | +0.228 |
| Republican | 0.448 | −0.242 |

Under polarisation the same ordering holds in magnitude but with the opposite sign (`no_discipline` costs parliamentary 66 percentage points). Discipline is the mechanism blocs use to aggregate votes: governing coalitions pass, anti-system oppositions obstruct. The sign of its effect flips with scenario; which side holds the whip in a hung parliament decides whether it legislates at all.

### 2. Passage–representation tradeoff

A new `policy_representation_gap` metric (L2 distance between passed bills and constituency median) shows that filtering and throughput lie on a single spectrum:

| Institution | Passage @ polarised | Representation gap |
|---|---:|---:|
| Parliamentary | 0.882 | +0.037 |
| Premier-presidential | 0.725 | −0.012 |
| President-parliamentary | 0.730 | −0.010 |
| Republican | 0.218 | **−0.530** |

Parliamentary maximises legislative throughput at the cost of representational fidelity. Republican maximises fidelity via the presidential veto at the cost of throughput. Semi-presidential variants split the difference.

### Figures

<table>
  <tr>
    <td align="center"><img src="docs/figures/hung_parliament_comparison.png" width="100%"><br><sub>Hung-parliament decomposition</sub></td>
    <td align="center"><img src="docs/figures/ablation_forest.png" width="100%"><br><sub>Mechanism ablations</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/figures/sobol_bars.png" width="100%"><br><sub>Sobol variance decomposition</sub></td>
    <td align="center"><img src="docs/figures/representation_tradeoff.png" width="100%"><br><sub>Passage–representation tradeoff</sub></td>
  </tr>
</table>

## Architecture

| Package | Purpose |
|---|---|
| `institutions/` | Four institutional presets across three Mesa `Model` classes (`ParliamentaryModel`, `RepublicanModel`, `SemiPresidentialModel`) |
| `agents/` | `LegislatorAgent`, `ConstituencyAgent`, `PartyAgent`, `CommitteeAgent` |
| `config/` | Frozen `@dataclass` configs; every mechanism knob lives here |
| `experiments/` | CLI runners: `multiseed_comparison`, `hung_parliament`, `clustered_robustness`, `sensitivity`, `ablation`, `parameter_sweep`, `discipline_robustness`, `representation` |
| `analysis/` | Bootstrap CIs, Welch/Mann-Whitney/Cohen's d (`aggregate.py`) and plotting (`plots.py`, `sensitivity_plots.py`, `representation_plots.py`, `robustness_plots.py`) |
| `streamlit_app/` | Interactive UI exposing every config parameter as a slider, with scenario-comparison, parameter-sweep, and ablation tabs |
| `tests/` | 80 tests covering determinism, config, mechanisms, multiseed, regression, sensitivity, ablation, semi-presidential, robustness, representation, clustered-init, and Streamlit |
| `paper/` | LaTeX manuscript (`main.tex`), bibliography, Makefile |
| `.github/workflows/ci.yml` | Python 3.13 CI on Ubuntu |

The `SemiPresidentialConfig` has two independent toggles (`government_formation` and `president_can_dismiss_pm`) that reach both Shugart-Carey variants from a single class. Use the `premier_presidential_config()` or `president_parliamentary_config()` presets, or mix toggles freely.

## Documentation

| File | Contents |
|---|---|
| [`paper/main.tex`](paper/main.tex) | JASSS-targeted manuscript |
| [`docs/ODD_PROTOCOL.md`](docs/ODD_PROTOCOL.md) | Full ODD description (Grimm et al. 2020) |
| [`docs/COMSES_METADATA.md`](docs/COMSES_METADATA.md) | CoMSES Network deposit card |
| [`docs/PHASE_A_NOTES.md`](docs/PHASE_A_NOTES.md) | Statistical harness and hypothesis tests |
| [`docs/PHASE_B_NOTES.md`](docs/PHASE_B_NOTES.md) | Sensitivity analysis and mechanism ablations |
| [`docs/PHASE_C_NOTES.md`](docs/PHASE_C_NOTES.md) | Semi-presidential variants |
| [`docs/PHASE_D_NOTES.md`](docs/PHASE_D_NOTES.md) | Streamlit interactive UI |
| [`docs/PHASE_E_NOTES.md`](docs/PHASE_E_NOTES.md) | Paper scaffold |
| [`docs/PHASE_F_NOTES.md`](docs/PHASE_F_NOTES.md) | Robustness checks and the dismissal fix |
| [`docs/PHASE_G_NOTES.md`](docs/PHASE_G_NOTES.md) | Representation metric and real-world benchmarks |
| [`docs/PHASE_H_NOTES.md`](docs/PHASE_H_NOTES.md) | Hung-parliament decomposition and bibliography audit |

## Reproducibility

All results are deterministic under seed. The pinned regression fixture [`institutional_comparison_results.csv`](institutional_comparison_results.csv) is checked against [`tests/test_regression.py`](tests/test_regression.py) on every push, so any mechanism change that shifts seed-42 outputs for parliamentary or republican fails CI. The Phase H `hung_parliament_behavior` flag defaults to `cohesive_obstruction`, which reproduces all pre-Phase-H numbers exactly — the fixture is unchanged. A second regression test enforces that the Phase F monotone rescue ordering survives at representative discipline levels.

Full 200-seed four-institution runs complete in under five minutes on eight cores. All figures in this README and in the paper are reproducible from the CLI entry points listed in Quick Start.

## Citation

If you use this work, please cite the paper ([`CITATION.cff`](CITATION.cff) carries the machine-readable version):

```
Ali, F. (2026). Why fragmented parliaments stop passing legislation:
  Opposition discipline and representation across four democratic institutions.
  arXiv:2608.24554. https://arxiv.org/abs/2608.24554
```

The arXiv v1 preprint corresponds to repository tag
[`v1.0.1`](https://github.com/tofuadmiral/institutional-representation-abm/releases/tag/v1.0.1);
every figure and table in the paper regenerates from that tree. Later commits
on `main` may extend the model beyond what the paper describes.

## License

[MIT](LICENSE). Copyright 2025–2026 Fuad Ali.
