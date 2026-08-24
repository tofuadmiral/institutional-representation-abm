# ODD Protocol — Institutional Representation ABM

This document follows the ODD (Overview, Design Concepts, Details) protocol
of Grimm et al. (2010), updated per Grimm et al. (2020).

## 1. Purpose and patterns

The model compares four democratic legislative institutions — pure
parliamentary, pure republican (presidential), premier-presidential (France),
and president-parliamentary (Russia) — on their ability to pass legislation,
represent constituencies, and remain operational under political
fragmentation and polarisation.

**Primary patterns the model is designed to reproduce:**

1. **Parliamentary passage advantage at baseline**: parliamentary systems pass
   a higher fraction of bills than presidential systems when political
   fragmentation is low (a well-documented empirical pattern).
2. **Parliamentary fragility under fragmentation**: as the number of parties
   grows, parliamentary passage should degrade sharply because coalition
   formation fails.
3. **Separation-of-powers gridlock**: presidential systems should lose more
   bills to veto and override failure under polarisation.
4. **Semi-presidential middle ground**: semi-presidential systems should fall
   between the two pure types, with variant-dependent behaviour under
   fragmentation.

## 2. Entities, state variables, and scales

### Entities

| Agent | Role | Key state |
|---|---|---|
| `ConstituencyAgent` | Electoral district | `ideology: (float, float)`, `population: int` |
| `PartyAgent` | Political party | `ideology: (float, float)`, `name: str` |
| `LegislatorAgent` | Member of parliament | `ideology: (float, float)`, `constituency_id`, `party_id`, `vote_support_threshold` |
| `CommitteeAgent` | Legislative committee | `jurisdiction`, `members`, `chair`, `gatekeeping_power` |

Bills (`Bill`) are *not* agents — they are ephemeral objects instantiated per
legislative step: `ideology`, `salience`, `bill_id`.

### Environment

A single parliament in a unitary state with one chamber. Ideology space is
`(-1, 1) × (-1, 1)` (economic × social axes). No spatial geography.

### State variables by institution

Parliamentary: `government_party`, `government_coalition`, `prime_minister`,
`confidence_votes_passed/failed`.
Republican: `executive_party`, `president`, `bills_vetoed`, `gridlock_events`.
Semi-presidential: union of both plus `presidential_dismissals`.

### Scales

- **Temporal**: one model "step" is a legislative period (roughly a session).
  Scenarios run for a fixed number of bills rather than a fixed horizon.
- **Spatial**: none.

## 3. Process overview and scheduling

Each institutional model processes bills one at a time through the
institution-specific passage pipeline. Agents are advanced via a Mesa
`RandomActivation` scheduler whenever `step()` is called (for optional
model-driven bill generation inside `step()`). Per-scenario batch runs bypass
`step()` and call `pass_legislation(bill)` directly on `num_bills` bills.

### Parliamentary `pass_legislation(bill)` pipeline
1. **Committee routing** — if any committee's jurisdiction covers the bill,
   the committee considers it. Outcomes: `approve` / `amend` / `kill`.
2. **Confidence-vote dice** — with probability `confidence_matter_rate`
   (default 0.3) the bill is treated as a confidence matter and the vote is
   whipped harder.
3. **Floor vote with party discipline** — each legislator's vote is whipped
   with probability `discipline_strength` (coalition) or
   `discipline_strength × opposition_discipline_multiplier` (opposition).
   Majority passes.
4. **Government collapse check** — if a confidence vote fails, the government
   falls and a new government is formed.

### Republican `pass_legislation(bill)` pipeline
1. Committee routing (as above, with stronger `committee_gatekeeping_power`).
2. Floor vote with weak discipline.
3. **Executive veto check** — veto probability rises with
   `|executive_ideology − bill.ideology|`, capped at `max_veto_probability`.
4. **Override attempt** — if vetoed, the floor vote is checked against the
   `override_threshold_fraction` (default 2/3).

### Semi-presidential `pass_legislation(bill)` pipeline
1. Committee routing.
2. Confidence-vote dice (parliamentary-style).
3. Floor vote with moderate discipline.
4. Executive (presidential) veto + override attempt.
5. Government collapse check if confidence vote failed.
6. Presidential dismissal check in `step()` when
   `president_can_dismiss_pm=True`.

## 4. Design concepts

- **Basic principles**: spatial voting (Downs 1957), gatekeeping committees
  (Shepsle 1978), party discipline as variance-reducer
  (Cox & McCubbins 1993), presidential regime typology (Shugart & Carey 1992).
- **Emergence**: passage rates, coalition instability, gridlock episodes, and
  representation distance emerge from micro-level voting decisions and
  stochastic mechanism triggers.
- **Adaptation, objectives**: legislators do not learn or adapt. Voting is
  based on a static ideology-distance threshold plus party discipline.
- **Sensing**: committees sense bill ideology and member ideology;
  presidents sense bill ideology.
- **Stochasticity**: discipline rolls, confidence-matter rolls, committee
  support rolls, executive veto rolls, and presidential dismissal rolls all
  use the model's seeded `Random` instance.
- **Collectives**: parties, coalitions, governing cabinets, committees.
- **Observation**: `passage_rate`, `bills_vetoed`, `gridlock_events`,
  `committee_kill_rate`, `committee_amendment_rate`,
  `avg_representation_distance`, `representation_inequality`,
  `perfect_representation_rate`, `cohabitation`, `divided_government`.

## 5. Initialisation

At `__init__`:
1. Create `num_constituencies` constituencies with ideologies on a 2D line:
   `(-1 + 2 * i / (n-1), -1 + 2 * i / (n-1))`.
2. Create `num_parties` parties on the same line with fewer points.
3. Create `num_legislators` legislators, each assigned to
   `constituency_id = i % num_constituencies` and
   `party_id = i % num_parties`. Ideology follows the same 2D line.
4. Initialise institution-specific state:
   - Parliamentary: call `_form_government()`.
   - Republican: call `_elect_executive()`.
   - Semi-presidential: call `_elect_president()` then `_form_government()`.
5. Initialise committees: spatial jurisdictions (Finance, Social Affairs,
   Foreign Affairs, Environment, Justice) at fixed ideology centres.

No stochastic initial conditions; the only source of run-to-run variance is
the seed passed to Mesa's `Model.__init__`, which seeds `self.random`.

A robustness variant (`experiments/clustered_robustness.py`) replaces this
spread initialisation with party-clustered legislator ideologies (each
legislator at their party's position plus Gaussian noise, σ = 0.15) and
re-runs the discipline ablation; see §1 pattern 2 and the paper's clustered
robustness section for results.

## 6. Input data

None. The model is not calibrated to empirical data; it is an explanatory
model of institutional mechanics.

## 7. Submodels

### Party discipline (`_get_disciplined_vote` / `_get_weak_disciplined_vote`)

Parliamentary:
```
personal_vote = decide_vote(bill)
if government_coalition is empty and hung_parliament_behavior == "personal_vote":
    return personal_vote          # no whip in play
if party_id in government_coalition and random() < discipline_strength:
    return True
elif party_id not in government_coalition and random() < discipline_strength * opposition_discipline_multiplier:
    return False
else:
    return personal_vote
```

`hung_parliament_behavior` (Phase H) selects between the two readings of a
hung parliament (empty coalition):
- `cohesive_obstruction` (default): the opposition-whip branch applies to
  every MP, so all members vote against bills with probability
  `discipline_strength * opposition_discipline_multiplier`.
- `personal_vote`: every MP reverts to their own preference.

The flag can only bind when the coalition list is empty; it is inert for
republican (no formation gate) and president-parliamentary (always seats at
least a minority cabinet).

Republican uses a weaker form that looks up the party's average ideology
rather than whipping a yes/no. Semi-presidential uses the parliamentary form,
including the hung-parliament toggle.

### Committee consideration (`CommitteeAgent.consider_bill`)

For each member, compute `support_prob = max(min_support_probability, 1 - distance)`.
Sample Bernoulli. The aggregate `support_rate`:
- `> strong_support_threshold` (0.6) → approve.
- `> moderate_support_threshold` (0.4) → amend (move bill `amendment_strength=0.3` toward committee mean).
- Otherwise → kill with probability `gatekeeping_power` (0.3 parliamentary, 0.4 republican, 0.35 semi-presidential), else approve.

### Executive veto (`_executive_veto_check`)

```
distance = ||executive_ideology - bill.ideology||
veto_prob = min(max_veto_probability, distance / veto_distance_scale)
veto_prob = max(veto_prob, executive_opposition_rate)
return random() < veto_prob
```

### Government formation

- **Majority-driven** (parliamentary, premier-presidential): largest party
  alone if it holds a majority, otherwise two-party coalition. Falls back to
  no government if neither succeeds.
- **President-driven** (president-parliamentary): the president's party forms
  the government, adding a second party if needed for majority; otherwise a
  minority cabinet.

Government falls on failed confidence vote. Semi-presidential with
`president_can_dismiss_pm=True` also falls when the president-PM distance
exceeds 0.5 and a `presidential_dismissal_rate` roll succeeds.

## 8. References

- Grimm, V. et al. (2010). *The ODD protocol: A review and first update*.
  Ecological Modelling 221:2760–2768.
- Grimm, V. et al. (2020). *The ODD protocol for describing agent-based and
  other simulation models: A second update*. JASSS 23(2):7.
- Shugart, M. S., & Carey, J. M. (1992). *Presidents and assemblies:
  Constitutional design and electoral dynamics*. Cambridge University Press.
- Cox, G. W., & McCubbins, M. D. (1993). *Legislative leviathan: Party
  government in the House*. University of California Press.
- Shepsle, K. A. (1978). *The giant jigsaw puzzle: Democratic committee
  assignments in the modern House*. University of Chicago Press.
- Downs, A. (1957). *An economic theory of democracy*. Harper.
