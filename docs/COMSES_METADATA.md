# CoMSES Net Deposit Metadata

For submission to the CoMSES Network Computational Model Library.
Fields follow the CoMSES deposit form layout.

---

**Title**: Institutional Representation ABM: Parliamentary, Presidential, and
Semi-Presidential Legislative Passage

**Authors**:
- Fuad Ali

**Language**: Python 3.13

**Framework**: Mesa 2.4 (ABM) + joblib (parallelisation) + SALib (sensitivity)
+ scipy (statistics) + Streamlit (interactive UI).

**Operating systems tested**: macOS (Darwin 25.4.0), Ubuntu 24.04 (GitHub
Actions CI).

**License**: MIT

**Keywords**: legislative studies, institutional design, political science,
agent-based model, party discipline, coalition formation, committee
gatekeeping, executive veto, semi-presidentialism.

---

## Overview

An agent-based model comparing four democratic legislative institutions —
pure parliamentary, pure republican/presidential, premier-presidential
(France), and president-parliamentary (Russia) — on their ability to pass
legislation under different scenarios of party-system fragmentation and
ideological polarisation. Every scenario is replicated over N=200 random
seeds with bootstrap confidence intervals, hypothesis tests, Morris and
Sobol sensitivity analyses, and mechanism ablations.

## How to run

```bash
git clone https://github.com/tofuadmiral/institutional-representation-abm
cd institutional-representation-abm
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# reproduce every figure in the paper:
python -m experiments.multiseed_comparison --scenarios all --seeds 200 --output results/paper/
python -m experiments.sensitivity --output results/paper/
python -m experiments.ablation --scenarios baseline fragmented polarized --seeds 200 --output results/paper/

# interactive exploration:
streamlit run streamlit_app/app.py
```

## Primary observed patterns

- Parliamentary passage advantage at baseline (75% vs. 45% republican).
- Parliamentary collapse under fragmentation (0.05% passage with 5 parties).
- Presidential gridlock under polarisation (22.5% passage at ±1.5 ideology
  range, 2 parties).
- Semi-presidential variants sit between the two pure types, with
  president-parliamentary partially rescuing passage under fragmentation.
- Ablation-demonstrated causal role of party discipline in the fragmentation
  collapse.

## Files deposited

- **Model code**: `institutions/`, `agents/`, `bills/`, `config/`, `metrics/`.
- **Experiment runners**: `experiments/`.
- **Analysis**: `analysis/`.
- **Interactive UI**: `streamlit_app/`.
- **Tests**: `tests/` (57 tests, GitHub Actions CI).
- **Regression fixture**: `institutional_comparison_results.csv`.
- **Documentation**:
  - `docs/ODD_PROTOCOL.md` — full ODD per Grimm et al. (2020).
  - `docs/PAPER_OUTLINE.md` — JASSS submission skeleton.
  - `docs/PHASE_A_NOTES.md` through `docs/PHASE_E_NOTES.md` — per-phase
    reviewer documents.
  - `docs/figures/` — all publication figures at N=200 seeds.
- **Raw run data**: `results/paper/` (gitignored in the repo; provided as a
  separate CoMSES data-set).

## Citation format (suggested)

Ali, F. (2026). *Institutional Representation ABM: Parliamentary,
Presidential, and Semi-Presidential Legislative Passage*. CoMSES
Computational Model Library. Submitted.

## Reproducibility statement

All results are deterministic under seed. The 200-seed runs complete in
under 5 minutes on 8 cores. Full CI is green on Python 3.13 Ubuntu. A
pinned regression fixture guards against drift.
