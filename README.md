# institutional-representation-abm

An agent-based model comparing four democratic legislative institutions —
pure parliamentary, pure republican/presidential, premier-presidential
(France), and president-parliamentary (Russia) — on their ability to pass
legislation, represent constituencies, and remain operational under
fragmentation and polarisation.

Not calibrated to any specific country; the goal is to isolate
structural tradeoffs through reproducible, parameterised experiments.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v

# reproduce all four-institution figures at N=200 seeds
python -m experiments.multiseed_comparison --scenarios all --seeds 200 --output results/main/

# Morris + Sobol sensitivity
python -m experiments.sensitivity --output results/main/

# mechanism ablations
python -m experiments.ablation --scenarios baseline fragmented polarized --seeds 200 --output results/main/

# interactive UI with sliders over every config parameter
streamlit run streamlit_app/app.py
```

## Headline finding

Under fragmentation, parliamentary passage collapses to 0.05% — a widely
reported but poorly attributed empirical pattern. The `no_discipline`
ablation restores passage to 46.7%, and the rescue magnitude decreases
monotonically across four institutions with their dependence on
parliamentary-majority government formation:

| institution | no_discipline Δ @ fragmented |
|---|---|
| parliamentary | **+0.466** |
| premier_presidential | +0.312 |
| president_parliamentary | +0.233 |
| republican | −0.242 |

The collapse is a party-discipline effect amplified by majority-rule
government formation — not a coalition-formation pathology on its own.

See `docs/PAPER_OUTLINE.md` for the full writeup.

## Architecture

- `institutions/` — the four Mesa `Model` subclasses (`ParliamentaryModel`,
  `RepublicanModel`, `SemiPresidentialModel`).
- `agents/` — `LegislatorAgent`, `ConstituencyAgent`, `PartyAgent`,
  `CommitteeAgent`.
- `config/` — frozen `@dataclass` configs. All mechanism knobs live here.
  `SemiPresidentialConfig` has two independent toggles (`government_formation`
  and `president_can_dismiss_pm`) so both Shugart-Carey variants are reachable
  from the same class; use `premier_presidential_config()` or
  `president_parliamentary_config()` presets, or mix toggles freely.
- `experiments/` — CLI runners (`multiseed_comparison`, `sensitivity`,
  `ablation`, `parameter_sweep`).
- `analysis/` — statistics (`aggregate.py`) and plotting
  (`plots.py`, `sensitivity_plots.py`).
- `streamlit_app/` — interactive UI with all-config sliders, scenario
  comparison, parameter sweep, and ablation tabs.
- `tests/` — 57 tests (determinism, config, mechanisms, multiseed,
  regression, sensitivity, ablation, semi-presidential, Streamlit).
- `.github/workflows/ci.yml` — Python 3.13 on Ubuntu.

## Documentation

- `docs/ODD_PROTOCOL.md` — ODD description per Grimm et al. (2020).
- `docs/PAPER_OUTLINE.md` — JASSS submission skeleton.
- `docs/COMSES_METADATA.md` — CoMSES deposit card.
- `docs/PHASE_A_NOTES.md` — statistical harness, bootstrap CIs, hypothesis tests.
- `docs/PHASE_B_NOTES.md` — sensitivity analysis + mechanism ablations.
- `docs/PHASE_C_NOTES.md` — semi-presidential variants.
- `docs/PHASE_D_NOTES.md` — Streamlit interactive UI.
- `docs/PHASE_E_NOTES.md` — paper scaffold + lead finding summary.
- `docs/RESEARCH_REVIEW.md` — original roadmap that this repo has now
  completed.

## Reproducibility

All results are deterministic under seed. The pinned regression fixture
(`institutional_comparison_results.csv`) is checked against `tests/test_regression.py`
on every PR. 200-seed runs complete in under 5 minutes on 8 cores.

## Author

Ahmed Fuad Ali, 2025–2026.
