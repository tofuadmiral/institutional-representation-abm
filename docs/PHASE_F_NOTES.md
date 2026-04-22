# Phase F: Robustness Checks

This phase addresses three concerns I raised after reviewing Phases A–E, all of
which could have undermined the paper's headline finding if left alone:

1. **Could the monotone `no_discipline` rescue ordering be an artefact of our
   default `discipline_strength` values?** Under Phase B/C defaults, the
   institutions happened to be ordered by discipline (parl 0.8 > premier-pres
   0.6 ≈ president-parl 0.6 > rep 0.4). The rescue magnitudes were ordered the
   same way. That identifiability concern needed a robustness test.
2. **Was the Phase B sensitivity analysis misleading for being baseline-only?**
   The most interesting sensitivity question is *what parameters matter under
   fragmentation*, and we hadn't run that.
3. **Was the presidential dismissal mechanism dead code in batch runs?** The
   `step()`-only placement meant CLI figures never triggered it. I flagged this
   in `PHASE_C_NOTES.md` but didn't fix it at the time.

## 1. Dismissal mechanism now fires in batch runs

`_maybe_dismiss_pm()` is called at the top of `pass_legislation()`, not only in
`step()`. Every bill is a legislative opportunity, so per-bill dismissal is the
natural semantic and what Shugart-Carey intends in the president-parliamentary
variant. A regression test in `tests/test_semi_presidential.py` guards this:
over 50 seeds × 30 fragmented bills, president-parliamentary produces >0
dismissals while premier-presidential produces exactly 0.

**Effect on Phase C passage rates (N=200, dismissal-fix applied):**

| scenario | institution | before fix | after fix | Δ |
|---|---|---|---|---|
| fragmented | president_parliamentary | 0.089 | 0.086 | −0.003 |
| polarized | president_parliamentary | 0.7275 | 0.7233 | −0.004 |

Small shifts, but now empirically attributable to the mechanism rather than
dead code. The fragmented rescue claim (president-parliamentary partially
rescues passage relative to parliamentary and premier-presidential) holds
both pre- and post-fix.

## 2. Fragmented-scenario sensitivity

Morris (r=20) and Sobol (N=256) rerun on `FRAGMENTED` for all four
institutions (Phase B was baseline-only):

**Sobol ST changes, baseline → fragmented:**

| institution | parameter | baseline ST | fragmented ST | Δ |
|---|---|---|---|---|
| parliamentary | num_parties | 0.808 | 0.760 | −0.048 |
| parliamentary | **confidence_threshold** | 0.178 | **0.294** | **+0.117** |
| parliamentary | discipline_strength | 0.166 | 0.134 | −0.033 |
| republican | committee_gatekeeping_power | 0.671 | 0.571 | −0.100 |
| republican | discipline_strength | 0.477 | 0.475 | ≈0 |
| premier_presidential | num_parties | — | 0.794 | new |
| premier_presidential | confidence_threshold | — | 0.280 | new |
| president_parliamentary | num_parties | — | 0.768 | new |
| president_parliamentary | confidence_threshold | — | 0.257 | new |

Key reads:

- **`num_parties` dominates all three majority-dependent institutions under
  fragmentation** (ST ≈ 0.76–0.79), consistent with the story that
  fragmentation is the primary gate failure.
- **`confidence_threshold` matters meaningfully more under fragmentation**
  for all three — when majorities are already hard to form, the threshold
  level becomes a sharper constraint.
- **Republican is structurally insensitive to `num_parties`** (ST=0.14) —
  the separation-of-powers system doesn't have a majority-formation gate to
  fail.
- **Discipline's Sobol ST is moderate across all systems**, *not* the largest
  effect under fragmentation. This is an important nuance: the ablation
  finding (zeroing discipline restores passage) is a large discrete jump,
  but smooth discipline variation within [0,1] contributes less variance
  than `num_parties` does. Both are true.

Committed to `results/phase_f/fragmented/{morris,sobol}_results.csv`.

## 3. Discipline-default robustness — the headline test

New experiment (`experiments/discipline_robustness.py`):

> For each `D ∈ {0.0, 0.1, …, 0.9}`, set all four institutions'
> `discipline_strength=D`. For each institution × scenario, compute
> `rescue(D) = passage_rate(D=0) − passage_rate(D)` with N=100 seeds per cell.

If the Phase C monotone ordering `parl > premier > president-parl > rep` is
structural, it should hold across the D grid. If it was an artefact of the
default parameter ordering, the rescue lines should cross.

### Result: under fragmented, the ordering holds at 9/9 tested D values

```
  D     parl   premier  president-parl   rep
  0.1  +0.091  +0.067   +0.018          −0.076
  0.2  +0.205  +0.138   +0.047          −0.153
  0.3  +0.293  +0.218   +0.104          −0.203
  0.4  +0.368  +0.274   +0.149          −0.244
  0.5  +0.422  +0.307   +0.189          −0.284
  0.6  +0.445  +0.321   +0.225          −0.306
  0.7  +0.458  +0.333   +0.250          −0.326
  0.8  +0.462  +0.335   +0.280          −0.339
  0.9  +0.462  +0.336   +0.291          −0.355
```

See `docs/figures/discipline_rescue_curves.png`.

**The monotone ordering parl > premier > president-parl > rep is preserved at
every tested D level**, and the test
`test_fragmented_rescue_ordering_is_monotone_over_discipline_grid` enforces
this as a regression check at D ∈ {0.0, 0.2, 0.5, 0.8} with N=50 seeds.

### Result: under baseline, discipline HELPS every system

At baseline, `rescue(D)` is negative for every institution at every D. That
is — **zeroing discipline hurts passage at baseline** (it un-whips the
government's own MPs). The ordering is also different: republican shows the
largest harm from zeroing discipline (it relies most on weak discipline to
aggregate votes), and the other three shuffle.

This is consistent with the Phase B ablation finding that `no_discipline`
adds to passage only under fragmentation. At baseline it subtracts.

### What this means for the paper's lead finding

The finding is **robust and sharpens**. The causal claim is:

> Under fragmentation, the `no_discipline` rescue magnitude is monotone in
> institutional majority-dependence. This ordering is preserved across
> common discipline levels D ∈ {0.1, …, 0.9} and is therefore a structural
> property of the formation-rule hierarchy, not an artefact of default
> parameter choices.

That's a much stronger claim than the Phase B version because it's conditioned
on discipline level rather than assuming the defaults.

## What changes in the paper

The `PAPER_OUTLINE.md` claim about monotonicity is now backed by Phase F data.
The figure `discipline_rescue_curves.png` belongs in the paper as a direct
robustness plot — probably right after the headline ablation-forest figure.

The `fragmented_sensitivity` results are an appendix piece: they show what the
reader would want to know about sensitivity within the fragmented regime.

The paper's Discussion section should note that the `no_discipline` ablation
is a large discrete ablation (0 vs. default), while the smooth Sobol measure
on [0, 1] gives a different — and smaller — picture. Both are informative;
neither is the "right" answer in isolation.

## Tests and determinism

- 64 tests pass in ~7s (6 new: 5 robustness unit tests + 1 dismissal
  regression).
- The monotone-ordering regression test is a hard guard: if a future
  mechanism change breaks the ordering under fragmentation, CI fails.
- Regression fixture unchanged — the parl/rep seed=42 passages are
  unaffected because dismissal only applies to semi-presidential.

## Files

- **New**: `experiments/discipline_robustness.py`,
  `analysis/robustness_plots.py`, `tests/test_robustness.py`,
  `docs/PHASE_F_NOTES.md`, `docs/figures/discipline_rescue_curves.png`.
- **Modified**: `institutions/semi_presidential.py` (dismissal moved),
  `experiments/sensitivity.py` (added semi-presidential problems),
  `tests/test_semi_presidential.py` (+ dismissal regression).
