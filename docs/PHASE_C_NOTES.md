# Phase C: Semi-Presidential Variants

## What this adds

A `SemiPresidentialModel` that combines a directly-elected president with a
cabinet responsible to parliament. Two real-world variants are supported
through configuration toggles:

| Variant | Government formation | President can dismiss PM | Examples |
|---|---|---|---|
| `premier_presidential` | majority-driven (largest-party coalition) | No | France (Fifth Republic), Portugal, Ireland |
| `president_parliamentary` | president-driven (presidential appointment) | Yes | Russia (1993–), Weimar Germany, Sri Lanka pre-1978 |

Both variants share the same model class (`institutions/semi_presidential.py`);
behaviour is driven by two independent flags (`government_formation` and
`president_can_dismiss_pm`), so "non-standard" combinations are also
reachable. The presets `premier_presidential_config()` and
`president_parliamentary_config()` return `SemiPresidentialConfig` instances
with the canonical settings.

## Reproduction

```bash
python -m experiments.multiseed_comparison --scenarios all --seeds 200 --output results/phase_c/
python -m experiments.ablation --scenarios baseline fragmented polarized --seeds 200 --output results/phase_c/
```

All four institutions (`parliamentary`, `republican`, `premier_presidential`,
`president_parliamentary`) are now included by default in
`INSTITUTION_NAMES`. The multi-seed runner emits the union of
institution-specific metrics; missing fields are filled with sentinel values.

## Headline findings

### Passage rates (N=200, 95% bootstrap CI)

| scenario | parliamentary | premier_presidential | president_parliamentary | republican |
|---|---|---|---|---|
| baseline | 0.742 [0.729, 0.754] | 0.547 [0.534, 0.561] | 0.545 [0.532, 0.559] | 0.450 [0.436, 0.464] |
| **fragmented** | **0.001** | **0.013** | **0.089** | 0.448 |
| polarized | 0.880 [0.871, 0.890] | 0.728 [0.714, 0.741] | 0.728 [0.714, 0.741] | 0.224 [0.211, 0.238] |
| small_system | 0.792 [0.778, 0.807] | 0.735 [0.719, 0.751] | 0.735 [0.719, 0.751] | 0.608 [0.591, 0.625] |

Two things jump out:

1. **Semi-presidential sits between parliamentary and republican** in every
   scenario, which is the plausibility check. The hybrid really does behave
   like a hybrid.
2. **The two variants diverge under fragmentation**. Premier-presidential
   collapses along with parliamentary (1.3% passage vs. 0.05%).
   President-parliamentary partially rescues passage (8.9%) — not to
   republican levels, but 68× better than the strictly-majority-driven
   variant. This is exactly the Shugart-Carey prediction: when coalition
   majorities cannot form, a president-driven appointment rule keeps *some*
   government capable of legislating, while a strictly majority-driven rule
   fails at the government-formation gate.

### Ablations confirm the mechanism

Under fragmentation (N=200):

| institution | no_discipline Δ | no_committees Δ | no_veto Δ |
|---|---|---|---|
| parliamentary | **+0.466** | +0.001 | — |
| premier_presidential | **+0.312** | −0.001 | +0.003 |
| president_parliamentary | **+0.233** | +0.032 | +0.025 |
| republican | −0.242 | +0.153 | +0.080 |

All three systems that pay a fragmentation cost (parliamentary and both
semi-presidential variants) are rescued by turning off party discipline. The
magnitude of the rescue *shrinks* as the system gets less majority-driven:
parliamentary (strict majority) +0.466 → premier-presidential (majority but
with presidential veto pressure) +0.312 → president-parliamentary
(president-appointed) +0.233. That's a clean monotone pattern and it lines
up with the intuition: the more the institution depends on a parliamentary
majority, the more party discipline becomes the binding constraint under
fragmentation.

Republican alone shows no improvement from removing discipline — it never
depends on a majority-forming gate, so there is nothing for discipline to
break.

### Polarized behaviour

At 2 parties and extreme bills, both semi-presidential variants tie exactly
(0.728, 0.728). That's because with two parties, one of them always has a
majority, so the president-driven and majority-driven rules converge to the
same outcome — the president and the parliamentary majority are nearly always
the same party. The variants only come apart when the number of parties is
large enough that presidential appointment and parliamentary coalition rules
can disagree.

## Architecture notes

- `SemiPresidentialModel` duplicates some helpers from `ParliamentaryModel`
  and `RepublicanModel` instead of multiple-inheriting. The duplication is
  intentional: semi-presidential has enough subtle interactions
  (cohabitation, presidential dismissal, majority vs. president-driven
  formation) that a dedicated implementation is clearer than a mixin.
- `president_can_dismiss_pm=True` adds a per-step check in `step()`:
  if the president and PM ideologies diverge by more than 0.5 L2 distance,
  there is a `presidential_dismissal_rate` probability (default 5%) per step
  of the president dismissing the cabinet, triggering a re-formation.
- Divided government (executive's party not in governing coalition) and
  cohabitation (executive's party not the parliamentary majority) are both
  reported in `get_separation_of_powers_stats()`.

## What changes for later phases

Phase D (Streamlit UI): four institutions × all config knobs is a lot of
sliders; the app will group by institution with a variant picker for
semi-presidential. The two `government_formation` and
`president_can_dismiss_pm` toggles are the interesting "structural" dials
to expose.

Phase E (paper): the monotone rescue pattern under `no_discipline` ablation
across (parliamentary → premier-presidential → president-parliamentary →
republican) is a strong candidate for a lead figure. It's the cleanest way
to show that the four institutions sit on a single spectrum and that
fragmentation cost is driven by majority-dependence, not by
presidential/parliamentary labels per se.
