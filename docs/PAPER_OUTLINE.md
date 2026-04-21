# Paper Outline — JASSS submission

**Working title:** *Why parliamentary systems collapse under fragmentation:
A four-institution agent-based model of legislative passage*

**Target journal:** *Journal of Artificial Societies and Social Simulation*
(JASSS). Format: ODD protocol, reproducibility code link, interactive
demo.

## 1. Abstract (200 words)

Parliamentary systems pass more bills than presidential systems at baseline,
but collapse to near-zero passage rates when the legislature fragments into
many small parties. A competing account attributes this collapse to
coalition-formation mechanics; another points to party discipline; a third to
committee gatekeeping. We present an agent-based model that compares four
democratic institutions — parliamentary, premier-presidential (France),
president-parliamentary (Russia), and republican (presidential) — across
four scenarios (baseline, fragmented, polarised, small-system) at N=200
seeds per cell with bootstrap confidence intervals and hypothesis tests.
Morris and Sobol sensitivity analyses identify the dominant parameters.
Mechanism ablations show that the parliamentary collapse under fragmentation
is caused not by coalition-formation rules alone but by their *interaction
with party discipline*: disabling discipline restores parliamentary passage
from 0.05% to 46.7% under fragmentation. The same ablation shows a monotone
rescue pattern across the four institutions that tracks their
majority-dependence (parliamentary +0.47, premier-presidential +0.31,
president-parliamentary +0.23, republican −0.24). We argue this reframes the
fragmentation-collapse literature: it is a discipline problem amplified by
majority-rule government formation.

## 2. Introduction (~1000 words)

- The parliamentary-vs-presidential passage question has been debated since
  Linz (1990); the empirical pattern of parliamentary passage advantage is
  well-known but its micro-mechanism is contested.
- The three competing mechanisms in the literature: coalition formation
  (Strøm 1990), party discipline (Bowler et al. 1999), committee
  gatekeeping (Tsebelis 2002).
- Why an ABM? Because these mechanisms are intertwined in any real
  political system, only a model allows ablation. Prior ABM work
  (Laver & Kenny 2014; Fowler & Smirnov 2007) modelled one mechanism at a
  time.
- Contribution: (1) four-institution comparison with semi-presidential
  variants made configurable; (2) Morris + Sobol sensitivity and mechanism
  ablations across all four systems; (3) the discipline-mediated mechanism
  for the fragmentation collapse.

## 3. Model description (ODD, see `docs/ODD_PROTOCOL.md`)

Include the ODD protocol as an appendix. Main text just summarises: four
institutions, spatial voting, stochastic party discipline, committees with
gatekeeping, executive veto and override, configurable government formation
for semi-presidential variants.

## 4. Experimental design

- **Statistical harness**: 200 seeds per (scenario × institution) cell.
  Bootstrap 95% CIs, Welch's t, Mann-Whitney U, Cohen's d.
- **Scenarios**: baseline (20 legislators, 3 parties, 6 constituencies),
  fragmented (24/5/8), polarised (16/2/4 with ideology range ±1.5),
  small-system (10/2/3).
- **Sensitivity**: Morris elementary effects (r=20 trajectories) + Sobol
  variance decomposition (N=256) on six primary config parameters per
  institution. Baseline scenario only.
- **Ablations**: disable committees, discipline, or veto (as applicable)
  one at a time, across baseline/fragmented/polarised scenarios, N=200
  seeds per cell.

## 5. Results

### 5.1 Passage rates across scenarios — Figure `forest_passage.png`

Lead figure: per-scenario mean passage rate with 95% CI for all four
institutions. Shows the baseline parliamentary advantage, the fragmented
parliamentary + premier-presidential collapse, the polarised republican
gridlock.

### 5.2 The fragmentation collapse — Figure `violin_passage.png`

Per-seed distributions show the collapse is robust, not a tail event.
Parliamentary passage at fragmented is effectively zero across all 200
seeds. Premier-presidential collapses similarly (majority-driven formation
rule). President-parliamentary partially rescues (president-driven formation
allows minority cabinets).

### 5.3 Sensitivity — Figure `sobol_bars.png`

Parliamentary passage is dominated by `num_parties` (Sobol ST=0.81);
republican by `committee_gatekeeping_power` (ST=0.67). Different bottlenecks
in different systems.

### 5.4 Mechanism attribution via ablation — Figure `ablation_forest.png`

The paper's headline. Disabling party discipline restores parliamentary
passage from 0.05% to 46.7% under fragmentation; the rescue magnitude
decreases monotonically across the four institutions as their dependence
on parliamentary-majority government formation decreases.

| institution | no_discipline Δ @ fragmented |
|---|---|
| parliamentary | +0.466 |
| premier_presidential | +0.312 |
| president_parliamentary | +0.233 |
| republican | −0.242 |

## 6. Discussion

- Why does discipline amplify the fragmentation cost? Because under
  fragmentation, coalition formation fails often; discipline then whips
  opposition MPs to vote against bills a free-vote median would support.
  The two failures stack.
- Why doesn't this happen in republican systems? Because there is no
  coalition-formation gate to fail. The executive is elected separately;
  passage is a floor vote plus a veto check.
- **Policy implication**: reforms that weaken party discipline (free votes,
  open primaries, district-focused incentive structures) may be more
  effective at unblocking fragmented parliaments than electoral reforms
  that reduce fragmentation directly.

## 7. Model limitations and future work

- Static ideology (no learning or updating).
- Fixed electoral geography (no endogenous party emergence or realignment).
- No bicameralism, judicial review, or federalism.
- Bills are ideologically ephemeral; no agenda control beyond committees.
- Only two semi-presidential variants; other hybrids (premier-presidential
  with dismissal, president-parliamentary without) are reachable via
  non-canonical config combinations but not studied here.

## 8. Reproducibility

- **Code**: <https://github.com/tofuadmiral/institutional-representation-abm>
- **CoMSES deposit**: pending (see `docs/COMSES_METADATA.md`).
- **Interactive app**: `streamlit run streamlit_app/app.py` gives sliders
  over every config parameter plus sweep, comparison, and ablation tabs.
- **CLI**: every figure in the paper is reproducible via
  `python -m experiments.multiseed_comparison`,
  `python -m experiments.sensitivity`, and
  `python -m experiments.ablation` with the flags documented in the phase
  notes.

## 9. Candidate figures (all in `docs/figures/`)

1. `forest_passage.png` — lead figure, per-scenario passage rates.
2. `violin_passage.png` — distributions, shows the fragmentation collapse
   is robust.
3. `sobol_bars.png` — sensitivity analysis.
4. `ablation_forest.png` — mechanism attribution, the paper's key finding.
5. `morris_scatter.png` — appendix, sensitivity screening.
6. `heatmap_metrics.png` — appendix, secondary metrics summary.

## 10. References (selected)

- Bowler, S., Farrell, D. M., & Katz, R. S. (eds.) (1999). *Party discipline
  and parliamentary government*. Ohio State University Press.
- Fowler, J. H., & Smirnov, O. (2007). *Mandates, parties, and voters*.
  Temple University Press.
- Laver, M., & Kenny, M. (2014). *Party competition in government
  formation*. Oxford University Press.
- Linz, J. J. (1990). *The perils of presidentialism*. Journal of Democracy,
  1(1).
- Shugart, M. S., & Carey, J. M. (1992). *Presidents and assemblies*.
  Cambridge University Press.
- Strøm, K. (1990). *Minority government and majority rule*. Cambridge
  University Press.
- Tsebelis, G. (2002). *Veto players: How political institutions work*.
  Princeton University Press.
