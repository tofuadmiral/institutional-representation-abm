# Phase A Notes — Statistical Hardening

This document accompanies the `feat/phase-a-statistical-hardening` PR. Phase A replaced a single-seed comparison pipeline with a parallelized N-seed harness, fixed a latent reproducibility bug, and extracted all magic numbers into typed configs.

## Reproducing the headline results

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v                                              # 28 tests, ~1s
python -m experiments.multiseed_comparison \
    --scenarios all --seeds 200 --output results/phase_a
```

Artifacts in `results/phase_a/`:
- `results_long.csv` — one row per (scenario, institution, seed). 1,600 rows at N=200.
- `summary.csv` — mean, std, 95% percentile-bootstrap CI per (scenario, institution, metric).
- `hypothesis_tests.csv` — Welch's t, Mann-Whitney U, Cohen's d for parliamentary vs republican on each (scenario, metric).
- `figures/forest_passage.png`, `figures/violin_passage.png`, `figures/heatmap_metrics.png`.

Wall time: ~8 seconds for 1,600 simulations on an M-series MacBook with 10 cores.

## What actually shifted from the single-seed headline

The original `institutional_comparison_results.csv` was generated from a single run per (scenario, institution). Two effects show up now:

1. **The committee RNG fix**. `agents/committee.py` previously called module-level `random.sample` and `random.random`, bypassing the model's seeded `Random` instance. Committee outcomes were therefore silently nondeterministic, and running the same seed twice could produce different results. Fixing this (by passing `rng=self.model.random` through `CommitteeAgent`) shifts the seed=42 single-run numbers — not dramatically, but enough that the fixture was re-pinned in the same commit as the fix.
2. **N=200 stabilizes noisy cells**. Some scenarios were much noisier than others, and the single-seed snapshot happened to land on misleading points.

Passage rates, single-seed fixture vs N=200 bootstrap mean (95% CI):

| Scenario     | Institution   | Single-seed | N=200 mean [95% CI]      |
|--------------|---------------|-------------|---------------------------|
| baseline     | parliamentary | 0.68        | 0.74 [0.73, 0.75]         |
| baseline     | republican    | 0.44        | 0.45 [0.44, 0.46]         |
| fragmented   | parliamentary | 0.00        | 0.0005 [0.00, 0.001]      |
| fragmented   | republican    | 0.47        | 0.45 [0.44, 0.46]         |
| polarized    | parliamentary | 0.90        | 0.88 [0.87, 0.89]         |
| polarized    | republican    | 0.25        | 0.22 [0.21, 0.24]         |
| small_system | parliamentary | 0.73        | 0.79 [0.78, 0.81]         |
| small_system | republican    | 0.73        | 0.61 [0.59, 0.62]         |

The `small_system` single-seed point landed at a tie (0.73 vs 0.73). With N=200 the parliamentary advantage there is 18 percentage points, not zero. That revision would not have surfaced without the harness.

## Figures

Snapshots rendered from the 200-seed run (also regenerated into `results/phase_a/figures/` whenever the runner is executed):

- `docs/figures/forest_passage.png` — per-scenario mean passage rate with 95% bootstrap CI, one row per scenario, both institutions.
- `docs/figures/violin_passage.png` — per-seed passage rate distribution per (scenario, institution).
- `docs/figures/heatmap_metrics.png` — metric means across all scenarios and institutions.

## Hypothesis tests (N=200) — parliamentary vs republican

| Scenario     | Mean diff | Welch p  | MWU p    | Cohen's d |
|--------------|-----------|----------|----------|-----------|
| baseline     | +0.292    | < 1e-100 | < 1e-70  | +3.11     |
| fragmented   | −0.448    | < 1e-100 | < 1e-70  | −7.28     |
| polarized    | +0.656    | < 1e-100 | < 1e-70  | +7.71     |
| small_system | +0.184    | < 1e-44  | < 1e-30  | +1.62     |

All effects are "large" (|d| ≥ 0.8). The direction flip under fragmentation — parliamentary collapses while republican is unchanged — survives the sample-size increase and is the most striking finding in the phase-A output.

**Why the collapse?** In the fragmented scenario (24 legislators / 5 parties) no single party holds a majority, and the current coalition rule only tries a 2-party coalition. When that also falls short, `government_formed` stays true but `government_coalition` is empty, so no legislator is inside the coalition and party discipline flips every vote against the government. This is a modeling artifact of the coalition-formation rule, not a substantive political science claim. It is preserved here as-is because the purpose of phase A is to confirm *which* results are robust to noise, not to fix mechanisms. The coalition-formation logic is a natural target for phase-B sensitivity analysis.

## What phase A did not do

Deferred to later chunks:
- Sensitivity analysis (Morris / Sobol) over the new config surface.
- Ablations: disable committees, disable discipline, disable veto.
- Semi-presidential model.
- ODD protocol documentation and CoMSES deposit.
- UI / SolaraViz.

## Files worth reviewing first

- `config/institutions.py` — every magic number now lives here as a frozen dataclass.
- `agents/committee.py` — RNG is injected, no more module-level `random.*`.
- `experiments/multiseed_comparison.py` — the harness and CLI.
- `analysis/aggregate.py` — bootstrap CIs and pairwise tests.
- `tests/test_regression.py` — 8 parameterized cases pinning seed=42 to the fixture with `abs=1e-6`.
