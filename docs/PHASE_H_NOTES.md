# Phase H: Hung-Parliament Decomposition and Bibliography Audit

This phase came out of an external adversarial review of the Phase A–G
results. It addresses two problems that could have sunk the paper:

1. **The fragmentation-collapse headline was an undocumented edge case.**
2. **The bibliography contained at least one likely-nonexistent reference
   and several with wrong metadata.**

## 1. The collapse was confounded — now it is decomposed

### The problem

In the fragmented scenario (24 legislators, 5 parties), seats are
deterministically 5-5-5-5-4 via `i % num_parties` assignment. No coalition
can reach the majority threshold of 13, so `government_coalition` is empty —
for every seed, by construction.

The original `_get_disciplined_vote` then applied the *opposition*-whip
branch to **every** MP (`party_id not in []` is true for all), so all 24 MPs
voted NO with probability `0.8 × 0.7 = 0.56`. Measured per-vote yes-rate
under fragmentation: **0.22**. The "fragmentation collapse" to ~0 passage was
therefore produced by a rule that treats a hung parliament as unanimous
anti-system obstruction — never stated in the paper, and arguably a bug.
The `no_discipline` rescue to ~47% was just the personal-vote majority
probability recovering.

### The fix: make it a measured variant

New config flag on `ParliamentaryConfig` and `SemiPresidentialConfig`:

    hung_parliament_behavior ∈ {cohesive_obstruction, personal_vote}

- `cohesive_obstruction` (default): pre-Phase-H behaviour; every MP counts as
  opposition when the coalition is empty. Anti-system reading of hung
  parliaments (Sartori's anti-system parties; Capoccia's interwar blocs).
- `personal_vote`: no whip in play, every MP reverts to their own preference.
  Issue-by-issue-majority world of minority governance (Strøm 1984, 1990;
  Laver & Schofield 1990).

The flag can only bind when the coalition list is empty, so baseline,
polarised, and small-system cells are bit-identical across variants, as are
republican (no formation gate) and president-parliamentary (always seats at
least a minority cabinet).

### Result (N=200 seeds per cell)

| institution | cohesive_obstruction | personal_vote | Δ |
|---|---:|---:|---:|
| parliamentary | 0.0005 [0, 0.0012] | 0.4643 [0.4525, 0.4763] | +0.464 |
| premier_presidential | 0.0128 | 0.3332 | +0.320 |
| president_parliamentary | 0.0860 | 0.0860 | 0 |
| republican | 0.4480 [0.4360, 0.4597] | 0.4480 | 0 |

**New headline claim:** government formation failure alone does not halt
legislation — a fragmented chamber of personally-voting MPs passes bills at
presidential-system rates (CIs overlap). Collapse requires cohesive
opposition obstruction. The pathology lives on the opposition side of the
whip, not in coalition bargaining.

Cross-validation: the independent `no_discipline` ablation restores
parliamentary fragmented passage to 46.7% (vs 46.4% here) via a different
manipulation.

### Harness-compatibility detail

`experiments/hung_parliament.py::_simulate_variant` replicates the
`_simulate_one` flow (bills generated up-front from `model.random`, then
passed one at a time) so its default-config rows match the paper's main
tables bit-for-bit. An earlier draft reused `_simulate_with_config`, which
interleaves bill generation with voting and therefore consumes a different
RNG stream (baseline parliamentary mean 0.7566 vs 0.742) — replaced for
exact comparability.

### Fixture compatibility

Defaults preserve behaviour, so `institutional_comparison_results.csv`
regenerates identically: `tests/test_regression.py` passes unchanged. No
fixture update required. (Also fixed en passant: §4.2 previously displayed
"0.001" where the current-harness value at N=200 is 0.0005 = 0.05%; the
abstract already said 0.05%. Now consistent everywhere.)

## 2. Bibliography audit

Every entry verified against publisher records:

- **Removed `laver2014`** ("Laver & Kenny, *Party Competition in Government
  Formation*, OUP 2014") — no evidence this book exists; almost certainly a
  garbled/hallucinated reference. Replaced with Laver & Schofield (1990),
  *Multiparty Government* (OUP), verified.
- **`shugart2016` → `shugart2008`**: the chapter is real but published 2008
  in the Oxford Handbook of Political Institutions (online 2009), not 2016.
  Added DOI.
- **`noble2017` → `noble2018`**: real work, but it is a book chapter in
  Treisman (ed.), *The New Autocracy* (Brookings, 2018), pp. 49–82 — not a
  2017 working paper.
- **`dalton2009` → `dalton1993`**: Dalton's own site confirms *Politics in
  Germany* 2nd ed. was HarperCollins (Scott-Foresman lineage), 1993. The
  "3rd ed., Pearson Longman, 2009" details were wrong.
- **Added**, all verified: Strøm (1984, *Comparative Political Studies*
  17(2):199–227 — note: not APSR), Sartori (1976, CUP),
  Capoccia (2005, Johns Hopkins UP).

## 3. Other changes

- `experiments/hung_parliament.py` — runner, summary with deltas, grouped-bar
  figure (`docs/figures/hung_parliament_comparison.png`).
- Streamlit sidebar exposes the flag as a selectbox for parliamentary and
  premier-presidential (`streamlit_app/configs.py::SELECT_SPECS`).
- Tests: 68 → 76 (`tests/test_hung_parliament.py`,
  `test_select_specs_reference_valid_config_fields`).
- Paper: new title subtitle, three-finding abstract (1,905 chars, under
  arXiv's 1,920 limit), §2.2 toggle description, §3.6 design subsection,
  §4.2 rewritten around Table `tab:hung` + Figure `fig:hung`, §6.1 rewritten,
  limitations add pipeline-model framing, reproducibility adds the runner.
- Poster rebuilt with Finding 1a/1b split and corrected references.
- Both PDFs rebuild cleanly with tectonic (`tectonic main.tex`,
  `tectonic poster.tex`; poster additionally needed T1 fontenc + lmodern for
  the bundle's missing `aett12`).

Committed run data: `results/phase_h/{hung_parliament_long,hung_parliament_summary}.csv`.
