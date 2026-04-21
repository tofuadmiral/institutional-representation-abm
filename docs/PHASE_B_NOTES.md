# Phase B: Sensitivity Analysis & Mechanism Ablations

## What this adds

Phase A gave us confidence intervals and hypothesis tests over a single-seed
pipeline. Phase B answers two downstream questions:

1. **Which parameters matter?** Morris elementary effects and Sobol variance
   decomposition over the six primary config knobs per institution.
2. **Which mechanisms matter?** Ablation runs that disable committees, party
   discipline, and executive veto one at a time and measure the contribution of
   each to the full-model passage rate.

## Reproduction

```bash
python -m experiments.sensitivity \
    --morris-trajectories 20 --sobol-samples 256 --seeds-per-sample 3 \
    --output results/phase_b/
python -m experiments.ablation \
    --scenarios baseline fragmented --seeds 200 \
    --output results/phase_b/
```

Baseline scenario only for sensitivity (scenarios×parameters explodes
quadratically). Both baseline and fragmented for ablations (fragmentation is
where the key finding lives).

## Headline findings

### Sensitivity (passage rate @ baseline)

Morris-screened, Sobol-confirmed. Parameters ordered by Sobol total-order index:

**Parliamentary**

| parameter | mu\* | ST | interpretation |
|---|---|---|---|
| `num_parties` | 0.62 | 0.81 | dominant by a wide margin |
| `committee_gatekeeping_power` | 0.22 | 0.20 | secondary |
| `discipline_strength` | 0.34 | 0.17 | secondary, nonlinear |
| `confidence_threshold` | 0.09 | 0.18 | interaction-heavy |
| `opposition_discipline_multiplier` | 0.12 | 0.05 | minor |
| `num_constituencies` | 0.06 | 0.03 | noise |

**Republican**

| parameter | mu\* | ST | interpretation |
|---|---|---|---|
| `committee_gatekeeping_power` | 0.39 | 0.67 | dominant |
| `discipline_strength` | 0.27 | 0.48 | strong |
| `executive_opposition_rate` | 0.13 | 0.18 | moderate |
| `num_parties` | 0.11 | 0.16 | moderate |
| `num_constituencies` | 0.10 | 0.13 | moderate |
| `max_veto_probability` | 0.09 | 0.13 | moderate |

The two institutions have **different dominant drivers**: parliamentary passage
is gated overwhelmingly by fragmentation (`num_parties`), republican passage by
committee gatekeeping. This is consistent with the story that coalition
formation is the bottleneck in parliamentary systems while agenda control is
the bottleneck in presidential systems.

### Ablations

Each row is Δ passage_rate vs. the full model at the same scenario and
institution, N=200 seeds per cell.

**Baseline**

| institution | ablation | Δ passage_rate |
|---|---|---|
| parliamentary | no_committees | +0.231 |
| parliamentary | no_discipline | −0.291 |
| republican | no_committees | +0.181 |
| republican | no_discipline | −0.247 |
| republican | no_veto | +0.072 |

At baseline, committees reduce passage by ~20pp in both systems (gatekeeping
kills bills). Discipline raises passage by ~25–29pp in both systems (herding
MPs to the party line past the 50% mark). Executive veto is a small drag
(~7pp) in republican systems at baseline ideological conflict levels.

**Fragmented — the key finding**

| institution | ablation | mean passage | Δ vs. full |
|---|---|---|---|
| parliamentary | **baseline (full model)** | **0.001** | 0.000 |
| parliamentary | no_committees | 0.002 | +0.001 |
| parliamentary | **no_discipline** | **0.467** | **+0.466** |
| republican | baseline | 0.448 | 0.000 |
| republican | no_committees | 0.601 | +0.153 |
| republican | no_discipline | 0.206 | −0.242 |
| republican | no_veto | 0.528 | +0.080 |

Phase A flagged the fragmentation collapse as "a modeling artifact of the
coalition-formation rule." Phase B pins the mechanism: **it is not the
coalition rule itself, nor committee gatekeeping, but party discipline acting
against a majority that cannot form.** With five parties and a 50%+1
threshold, coalition formation fails; discipline then whips MPs of the
would-be opposition to vote against bills that a free-vote majority would
support. Turning committees off barely moves the result (from 0.0005 to
0.0015). Turning discipline off restores passage to 46.7% — in the same ball
park as the republican system under identical fragmentation.

This is the strongest causal statement the paper can make today:

> The parliamentary passage collapse under fragmentation is caused by the
> *interaction* between the coalition-formation failure and strict party
> discipline, not by the coalition rule alone. Systems with the same
> coalition rule but weaker discipline (republican) do not collapse.

Republican under fragmentation degrades gracefully to 44.8% — the same
committee and discipline ablation directions hold, and the absolute magnitudes
are smaller because the system does not have a government-formation gate.

## Files

- `experiments/sensitivity.py` — Morris + Sobol over 6 params × 2 institutions.
- `experiments/ablation.py` — mechanism toggles by monkey-patching.
- `analysis/sensitivity_plots.py` — Morris scatter, Sobol bars, ablation forest.
- `tests/test_sensitivity.py`, `tests/test_ablation.py` — 13 tests.
- `results/phase_b/` — raw CSVs.
- `docs/figures/morris_scatter.png`, `sobol_bars.png`, `ablation_forest.png`.

## What changes for later phases

Phase C (semi-presidential): need to add `premier_presidential` and
`president_parliamentary` variants and re-run ablations. The prediction: as the
semi-presidential variant slides from majority-driven toward president-driven
government formation, the fragmentation collapse should soften, because the
president-appointed government is not contingent on a coalition majority. The
ablation harness built here will test that prediction directly.

Phase D (Streamlit UI): the Sobol top-2 parameters per institution are the
obvious candidates for the "turn into a sweep axis" widget — wiring it to
`discipline_strength` (both systems) and `num_parties` (parliamentary) /
`committee_gatekeeping_power` (republican) lets a reader reproduce the Phase B
headline findings interactively.
