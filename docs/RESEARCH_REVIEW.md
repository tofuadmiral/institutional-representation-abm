# Institutional Representation Research

**Repo:** `/Users/fali/projects/institutional-representation-abm`
**Author:** Fuad Ali (2025)
**Last reviewed:** 2026-04-20
**Status:** Phase 1 complete, Phase 2 partial, Phase 3 not started. Roughly 60–70% of PRD scope implemented. Not yet publishable without the additions in §4.

---

## 1. One-paragraph project summary

An agent-based model (Mesa 2.0, Python) that compares how different democratic institutions translate citizen preferences into policy. Two regime types are implemented — **parliamentary** (fused powers, confidence votes, strong party discipline, coalition formation) and **republican/presidential** (separated powers, executive veto with 2/3 override, weak discipline, committee gatekeeping) — plus a shared 2D ideological space, committee routing with amendment, and a comparative experimental harness across four scenarios (baseline, fragmented, polarized, small). The goal is explicitly generative/theoretical in the Kollman–Miller–Page / Laver–Sergenti tradition: *isolate structural tradeoffs* rather than reproduce specific countries. The core finding to date: parliamentary systems are on average ~21 percentage points more efficient at passing bills (63.7% vs 42.8%), but **collapse completely under fragmentation** (5 parties → 0% passage, 6 failed confidence votes), whereas presidential systems remain functional under fragmentation (~57% passage) at the cost of routine gridlock.

---

## 2. Core research question and thesis

**Question.** How do institutional structures mediate the translation of citizen preferences into legislative outcomes, and what are the efficiency–robustness–congruence tradeoffs between institutional designs?

**Operational hypotheses.**
1. Parliamentary systems are more efficient but more fragile to fragmentation.
2. Presidential systems are more deliberative and robust but less efficient.
3. Institutional mechanisms (party discipline, committee gatekeeping, veto points) have *measurable, separable* effects on representation, efficiency, and stability.

**Current empirical support (single-seed, no CIs):**

| Scenario | Parliamentary passage | Republican passage | Signal |
|---|---|---|---|
| Baseline (3 parties) | 80% | 36% | Parliamentary efficient |
| Fragmented (5 parties) | **0%** (6 failed confidence votes) | 56.7% | Parliamentary collapses |
| Polarized (2 parties, wide bills) | 95% | 25% | Parliamentary dominant |
| Small (2 parties, 10 legislators) | 80% | 53% | Parliamentary efficient |

The **fragmented-parliamentary collapse** is the most publishable headline — it's a clean computational analog to Linz's "perils of presidentialism" critique in reverse ("the perils of hyper-fragmented parliamentarism").

---

## 3. What exists today (implementation map)

### Agents (`agents/`)
- `LegislatorAgent` — ideology (2D), party, constituency; Euclidean-distance voting (`dist < 1.0` → support).
- `ConstituencyAgent` — static preference holder.
- `PartyAgent` — aggregate ideology; discipline applied institutionally, not by object.
- `CommitteeAgent` — jurisdiction, gatekeeping, amendment (moves bill 30% toward committee centroid).

### Institutions (`institutions/`)
- `BaseInstitutionModel` — Mesa `Model` with `RandomActivation`, deterministic ideology spread, `DataCollector`.
- `ParliamentaryModel` (382 LOC) — government formation (single-party or largest+second coalition), confidence votes (30% of bills), party discipline 0.8, committee routing.
- `RepublicanModel` (384 LOC) — executive election (70% largest party / 30% other), weak discipline 0.4, executive veto probability `min(0.8, dist/2.0)`, 2/3 override, gridlock tracking.

### Bills, metrics, experiments
- `Bill` dataclass (ideology, salience, votes).
- `metrics/collectors.py` — avg legislator–constituency distance, representation inequality (variance), committee kill/amendment rates.
- `experiments/institutional_comparison.py` — 4 scenarios × 2 institutions; results → `institutional_comparison_results.csv`.

### Gaps (explicit or implicit)
- No unit tests (only integration scripts).
- **Single random seed** across all experiments. No confidence intervals.
- No sensitivity analysis.
- No real-world calibration (by design — but at least stylized-facts check missing).
- Phase 2 only partially done: committees exist, but party whipping, bill prioritization, and legislative calendars from the PRD are not implemented.
- Phase 3 (responsiveness, temporal stability, coalition representativeness as first-class metrics) not started.
- No endogenous elections; preferences static throughout simulation.
- No UI.

---

## 4. What's missing to make this publishable

Ordered by expected reviewer pain.

### 4.1 Statistical rigor (blocker for any serious venue)
- [ ] Run each scenario with **100–1000 replications** across seeds, report mean ± 95% CI.
- [ ] Add hypothesis tests for the parliamentary-vs-republican efficiency gap per scenario (Welch's t or Mann–Whitney on passage rates).
- [ ] Separate burn-in from stationary regime; currently every step is counted.
- [ ] Report distributional results, not just point estimates, for all headline numbers.

### 4.2 Sensitivity and ablation (blocker for JASSS/JTP)
- [ ] One-factor-at-a-time (OFAT) sweep across: `discipline_strength` {0.0…1.0}, `confidence_threshold` {0.4, 0.5, 0.6, 0.67}, `committee_gatekeeping_power` {0.0…0.8}, `executive_opposition_rate`, number of parties, number of constituencies.
- [ ] Morris screening for low-cost global sensitivity; Sobol variance decomposition for final reported parameters. *Reference:* ten Broeke, van Voorn & Ligtenberg 2016, JASSS 19(1):5.
- [ ] Ablation: disable committees; disable discipline; disable veto. Show each mechanism's contribution to the outcome.

### 4.3 Institutional coverage
- [ ] **Semi-presidential** (à la Elgie 2011; Shugart & Carey 1992) — premier-presidential vs president-parliamentary subtypes.
- [ ] **Consensus-democracy variant** (Lijphart) — PR electoral rule, bicameralism, supermajoritarian decision rules.
- [ ] **Westminster subtype** of parliamentary — single-member districts, FPTP, two-party equilibrium.
- [ ] At minimum: a bicameral extension (current model is unicameral; adding a second chamber with a different electoral rule is a first-order institutional feature).

### 4.4 Behavioral realism
- [ ] **Endogenous elections.** Today the composition of the legislature is fixed at `__init__`. Add an electoral cycle: voters' preferences → vote shares under the electoral rule (PR / FPTP / MMP) → seat allocation → government formation. This is what unlocks Phase 3 responsiveness metrics.
- [ ] **Baron–Ferejohn-style bill proposal.** Replace exogenous random bills with a recognition-probability proposal game; let the proposer's identity matter.
- [ ] **Richer legislator utility.** Today voting is a threshold on Euclidean distance. Replace with a quadratic loss `u = -||x_L − x_B||²` and a Luce/softmax choice to avoid knife-edge behavior.
- [ ] **Preference drift / events.** Allow constituency ideologies to shift (e.g., economic shock) so that responsiveness (Powell congruence over time) becomes measurable.
- [ ] **Graduated party discipline.** Whip strength should depend on issue salience and government majority size, not a single parameter.

### 4.5 Metrics aligned with the literature
Current metrics are distance- and count-based. Add:
- [ ] **Powell/Golder–Stramski congruence** (median voter ↔ government position; one-to-many versions).
- [ ] **Responsiveness** (dPolicy / dPreference) over a shocked scenario.
- [ ] **Gilens–Page differential representation** across income/preference groups (requires heterogeneous constituency weights).
- [ ] **Tsebelis winset size** (a natural proxy for the effective policy-maneuver room, computable from veto-player positions).
- [ ] **Effective number of parties (ENP)** and **disproportionality (Gallagher index)** for any electoral module added.
- [ ] **Temporal stability** (policy variance across sessions).

### 4.6 Empirical grounding (even if generative)
- [ ] **Stylized-facts validation**: confirm the model reproduces well-known qualitative regularities — parliamentary systems: more parties in government, faster policy change; presidential systems: lower ENP in government, periodic gridlock, higher veto points. Cite Lijphart 1999 benchmarks directly.
- [ ] Light calibration pass: set committee kill rate and executive veto rate so simulated magnitudes fall within plausible historical ranges from CSES / V-Dem / Comparative Agendas Project. Don't over-calibrate — the model is generative — but ground the parameters.

### 4.7 ODD protocol documentation
- [ ] Write an **ODD (Overview, Design concepts, Details)** description as per Grimm et al. 2020 (JASSS 23(2):7). Required by JASSS, expected by JTP / CMOT reviewers.
- [ ] Add a **TRACE** document (Grimm et al. 2014) for validation steps.
- [ ] Archive on **CoMSES Net / OpenABM** with a Zenodo DOI for replication. Include a pinned `uv.lock` or Dockerfile alongside `requirements.txt`.

### 4.8 Code quality
- [ ] Replace manual scripts in `experiments/` with `pytest` unit tests for each mechanism (confidence vote, veto override, committee amendment).
- [ ] Extract hardcoded magic numbers (0.3 confidence-vote rate, 30% amendment move, 70% executive-election probability) into a typed config.
- [ ] Add GitHub Actions CI for tests.

---

## 5. UI — why it matters and what to build

### Why the UI is a good idea
Two concrete benefits beyond "nice to have":
1. **Reviewer and reader comprehension.** Reviewers at JASSS, JTP, and APSA panels increasingly expect an interactive demo or at minimum high-quality animated visualizations. An exploratory notebook isn't enough for a headline figure.
2. **Parameter exploration.** Interactive sliders across `discipline_strength`, number of parties, veto threshold etc. makes the model's behavior legible far more efficiently than static tables. This accelerates your own research iteration.

### Proposed UI scope

**MVP (2–3 weeks):** Streamlit or Dash app (stays in Python, reuses Mesa directly; avoids a server/client split).

Panels:
- **Parameter controls** — sidebar sliders for all institutional parameters, scenario presets.
- **Ideological space view** — 2D scatter of legislators, constituencies, bills over time; color by party; filled convex hulls for government vs opposition.
- **Bill lifecycle flow** — animated Sankey from Proposal → Committee (approve/amend/kill) → Floor Vote → (Confidence Vote OR Veto → Override) → Pass/Fail.
- **Metrics time series** — passage rate, confidence votes, gridlock events, avg congruence, inequality.
- **Scenario comparison** — side-by-side runs with seeded replication; shaded 95% CI bands.

**Stretch (v2):** React + FastAPI backend exposing a run endpoint. Shareable scenario URLs for reviewers. Mesa already has `mesa.visualization` (SolaraViz in Mesa 3) — worth evaluating first since it costs less.

**Recommendation.** Start with **SolaraViz (Mesa 3)** or **Streamlit**. Do not build a custom React frontend until after submission — it's a distraction from the paper itself.

---

## 6. Roadmap to publication

Suggested ordering, with rough effort estimates. Assumes ~10 hrs/week.

### Phase A — Statistical hardening (2–3 weeks)
Addresses §4.1, §4.2. Unblocks any credible results table.
1. Multi-seed replication infra (200+ seeds per scenario).
2. Bootstrap CIs for all headline metrics.
3. OFAT sweep + Morris screening.
4. Ablation study (disable each mechanism).

### Phase B — Institutional and behavioral richness (3–4 weeks)
Addresses §4.3, §4.4.
1. Add bicameralism as a switch on both models.
2. Add semi-presidential model.
3. Replace random bill generation with Baron–Ferejohn-style proposer recognition.
4. Smooth the voting function (softmax instead of hard threshold).
5. Endogenous elections with a pluggable electoral rule (FPTP / PR).

### Phase C — Metrics and validation (2 weeks)
Addresses §4.5, §4.6.
1. Powell congruence, Gallagher disproportionality, ENP.
2. Responsiveness under a preference-shock scenario.
3. Stylized-facts comparison table against Lijphart's 36-country results.

### Phase D — UI (2 weeks)
Addresses §5. SolaraViz-based dashboard with scenario presets and animated bill lifecycle.

### Phase E — Paper and documentation (3–4 weeks)
Addresses §4.7, §4.8.
1. ODD protocol appendix.
2. Draft paper in JASSS template.
3. CoMSES deposit + Zenodo DOI.
4. Replication notebook.

**Total estimate:** ~3 months of focused part-time work to a submittable JASSS manuscript.

---

## 7. Positioning statement (draft for paper intro)

> Formal models of legislatures (Baron & Ferejohn 1989; Krehbiel 1998; Cox & McCubbins 2005) and comparative-institutions theory (Lijphart 1999; Tsebelis 2002; Powell 2000) offer rich but largely non-computational accounts of how institutional designs translate preferences into policy. The computational tradition launched by Kollman, Miller & Page (1992, 2003) has matured into full ABMs of party competition (Laver & Sergenti 2012) and parliamentary governance cycles (de Marchi & Laver 2023), but a systematic, controlled computational comparison *across* regime types — parliamentary, presidential, and hybrid — using a unified representational-fidelity metric has not yet been undertaken. Recent LLM-agent simulations (Srinivasan & Patapati 2025) have opened the question of institutional design as an alignment lever, but face severe validation problems. This paper fills the gap with a transparent, rule-based, reproducible ABM implemented in Mesa, documented in the ODD protocol, and benchmarked against Lijphart–Powell stylized facts, that isolates the structural tradeoffs of each regime in producing representation, stability, and congruence.

---

## 8. Literature to engage (must-cite list)

### Computational / ABM lineage
- **Kollman, Miller & Page (1992)** — "Adaptive Parties in Spatial Elections," *APSR* 86(4). The founding paper; a direct template.
- **de Marchi & Page (2014)** — "Agent-Based Models," *Annual Review of Political Science* 17. The canonical review; mandatory cite.
- **Laver & Sergenti (2012)** — *Party Competition: An Agent-Based Model*, Princeton. Closest-neighbor work; your institutional extension.
- **de Marchi & Laver (2023)** — *The Governance Cycle in Parliamentary Democracies*, Cambridge. Most important recent book; position your cross-regime contribution against their parliamentary-only work.
- **Axelrod (1997)** — dissemination of culture / complexity of cooperation. Stylistic touchstone.
- **Lustick (2000)** — JASSS 3(1). Exemplar political ABM at your target venue.
- **Epstein (2006)** — *Generative Social Science*. Cite for generative epistemology.

### Comparative institutions canon
- **Lijphart (1999/2012)** — *Patterns of Democracy*. Anchor your stylized-facts validation on this.
- **Linz (1990)** — "The Perils of Presidentialism," *Journal of Democracy* 1(1).
- **Cheibub & Limongi (2002)** — counterpoint to Linz, *Annual Review of Political Science* 5. Required for honest framing.
- **Tsebelis (2002)** — *Veto Players*. Your model operationalizes this; build bridge explicitly.
- **Powell (2000)** — *Elections as Instruments of Democracy*. Your congruence metric should be defined in his terms.
- **Shugart & Carey (1992)** / **Elgie (2011)** — for semi-presidential subtypes.

### Formal legislative theory
- **Downs (1957)**; **Black (1948)** — median voter / spatial models.
- **Baron & Ferejohn (1989)** — legislative bargaining; structural benchmark.
- **Krehbiel (1998)** — pivotal politics.
- **Cox & McCubbins (1993/2007)** — cartel theory / negative agenda control.

### Representation and responsiveness
- **Gilens (2012)** / **Gilens & Page (2014)** — unequal representation.
- **Achen & Bartels (2016)** — *Democracy for Realists*. Pre-empt their critique of "folk-theory" ABMs.
- **Golder & Stramski (2010)** — AJPS; technical congruence measurement.

### Frontier (2023–2025)
- **Srinivasan & Patapati (2025)** — "Democracy-in-Silico," arXiv:2508.19562. LLM-agent comparator — differentiate on validation grounds.
- **"Political Actor Agent"** — AAAI 2025, arXiv:2412.07144.
- **Validation-of-LLM-ABM critique** (PMC 2025). Cite to preempt reviewer skepticism about LLM agents.

### Methodology (must cite for JASSS)
- **Grimm et al. (2020)** — ODD protocol, *JASSS* 23(2):7.
- **Grimm et al. (2014)** — TRACE documentation.
- **ten Broeke, van Voorn & Ligtenberg (2016)** — sensitivity analysis, *JASSS* 19(1):5.
- **Thiele, Kurth & Grimm (2014)** — parameter-estimation cookbook, *JASSS* 17(3):11.
- **Ter Hoeven et al. (2025)** — Mesa 3 in JOSS. Cite the framework.

---

## 9. Target publications — ranked

### Primary target
1. **Journal of Artificial Societies and Social Simulation (JASSS)**. Natural home. Open access, Q1, ABM-welcoming, explicitly expects ODD. Precedents: Lustick 2000, many party-competition pieces. **Recommended first submission.**

### Strong secondaries (submit here if JASSS desk-rejects or as the comparative-politics-framed version)
2. **Journal of Theoretical Politics (SAGE).** Formal/computational-friendly, good for theory-forward framing.
3. **Political Analysis (Cambridge UP).** High prestige; reframe as methods paper ("how to measure representational fidelity in simulated institutions").

### Reach targets (only after Tier-1 referee feedback suggests novelty warrants it)
4. **British Journal of Political Science.** Has published ABM (Kollman–Miller–Page 1998).
5. **American Journal of Political Science (AJPS).** Top generalist; requires external-validity story.
6. **Comparative Political Studies.** Institutional-comparison framing fits.
7. **American Political Science Review (APSR).** Top-of-discipline; KMP 1992 precedent. Reach.

### Interdisciplinary / complexity outlets
8. **PLOS ONE** — fast, broad, open access; diffusion over prestige.
9. **Computational and Mathematical Organization Theory (Springer).**
10. **Advances in Complex Systems.**
11. **Journal of Computational Social Science (Springer).**
12. **PNAS** — only with a striking stylized finding and a general-audience framing.

### Conferences (present before submission)
- **ESSA Social Simulation Conference** — ABM community; natural venue. Good for pre-submission feedback.
- **APSA Annual Meeting** — Formal Political Theory / Political Methodology sections.
- **MPSA Annual Meeting** — broader comparative-politics audience.
- **AAMAS** (MABS workshop) — CS/AI crossover.
- **ECPR Joint Sessions** — comparative-institutions audience.

**Recommended path:** present at **ESSA SSC 2026** summer → revise on feedback → submit to **JASSS** in autumn 2026.

---

## 10. Open questions and decisions to make

- **Endogenous vs exogenous elections?** Endogenous unlocks responsiveness metrics but adds calibration surface; exogenous keeps the comparison crisp. Current code is exogenous. *Suggest: add as an optional mode, keep exogenous as baseline for cleanliness.*
- **Calibrate or stay purely generative?** Your README takes the Laver–Sergenti stance (no calibration). Defend this in the paper with a stylized-facts section instead of numerical calibration.
- **LLM agents — engage or delimit?** Given the 2025 surge (Democracy-in-Silico etc.), cite and differentiate on validation grounds. Do not pivot to LLM agents — your rule-based transparency is a strength.
- **How many institutional types to include in the first paper?** Parliamentary, presidential, and semi-presidential is the natural minimum trio. Consensus/majoritarian subtypes can be a follow-up paper.
- **Single paper or series?** Consider: Paper 1 (JASSS, methods + three regimes); Paper 2 (JTP or CPS, deeper result on fragmentation collapse); Paper 3 (AJPS, responsiveness under shocks).

---

## 11. Immediate next actions (one week)

1. Wrap `institutional_comparison.py` in a multi-seed harness; rerun all four scenarios with 200 seeds; regenerate `institutional_comparison_results.csv` with CIs.
2. Add Morris screening over the six primary institutional parameters.
3. Sketch the SolaraViz dashboard stub with one scenario and the ideological-space plot.
4. Start ODD-protocol draft in `docs/ODD.md` using Grimm 2020 template.
5. Create a `references.bib` seeded with the §8 list.
