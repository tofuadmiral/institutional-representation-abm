# Paper 3: identifying office-incentive responses

This November 2, 2026 exploratory analysis asks which actions distinguish faithful representation from an explicit office-bonus objective once continuation values and coalition assumptions are exposed. It uses completed, pinned data. It makes no new model calls and does not revise the original scientific screens or results.

## Executed findings

| Full enacted-policy menu diagnostic | Discovery | Fresh validation |
| --- | ---: | ---: |
| Actor/episode menus with disjoint optima when continuation is fixed | 4 / 112 | 6 / 112 |
| Such menus after allowing the full saved terminal-utility range | 0 / 112 | 0 / 112 |
| Observed offers at fixed-continuation disjoint menus | 6 / 128 | 6 / 128 |
| Observed offers individually supported by a shared continuation witness for both objectives | 128 / 128 | 128 / 128 |
| Private pivotal probe candidates, with controlled continuation | 19 | 16 |

For the initially disjoint actor menus, the first overlapping action appears at continuation ranges [1, 1, 3, 11] in discovery and [1, 2, 5, 7, 8, 9] in validation, in district utility units. The observed action can require a larger range. For example, discovery chair 0's choice of policy 1 rather than policy 5 needs only one extra expected future utility unit to become mandate-optimal as well. Its saved terminal-utility range is 46. The validation district 0 counteroffer of policy 2 needs five units; its range is 58. Neither is an estimate of the actor's beliefs.

The myopic office-support menu excludes one discovery offer and six validation offers. These are retained as outside the assumed menu, not silently dropped or declared irrational. Every included offer still has a shared witness at the full range. Coalition stress tests find no active conflict/binding-majority policy with four strict supporters under every one of the 36 deterministic continuation pairs, under either reference objective. All 20 active policies have a passing scenario and a failing scenario. This establishes sensitivity within the stated benchmark, not real counterfactual coalition behavior.

All 35 private target probes have strictly opposite two-term predictions; all 70 matched control states have agreeing predictions; all 35 threshold states produce the expected office-score tie. Their gains range from 8 to 23, and strict continuation margins range from 1 to 12. These counts establish software discrimination in constructed states, not LLM performance. Original discovery and failed replication verdicts remain unchanged.

## Exact identification calculation

For one district and a common assumed menu A of enacted first-term policies, define:

- U(p): first-term district SUM utility.
- R(p): first-term retention under the assigned institution.
- S(p) = U(p) + B R(p), where the original bonus B is 24.
- F(p): expected second-term district utility conditional on first-term enactment. This utility remains credited after removal.

The two idealized reference objectives maximize U(p)+F(p) and S(p)+F(p). Neither is a claim about the LLM's actual preferences or planning algorithm.

If max(F)−min(F) ≤ epsilon, policy p can maximize a reference value V+F exactly when max(V)−V(p) ≤ epsilon. Necessity follows by comparing p with a V-maximizer. Sufficiency follows by assigning F(p)=epsilon and F(q)=0 to other policies. Thus the first epsilon at which the two possible-action sets overlap is:

```
min over p in A of max(max_A U − U(p), max_A S − S(p)).
```

This radius concerns the first overlapping action, which need not be the observed action. For a specified observed policy, use its own maximum of the two gaps. Equality permits ties. These are existence statements, not probabilities or estimates of beliefs.

The analysis uses both epsilon=0 and the full range of the district's saved second-term utility table. For each observed offer compatible with both references at that range, it constructs a shared deterministic witness: the selected first-term policy leads to that district's best terminal policy, while alternatives lead to its worst. Each mapped terminal policy is an available policy. Such a witness is actor-specific; it does not jointly rationalize the whole transcript, establish a credible equilibrium, or demonstrate actual expectations.

Offers are evaluated as conditional enacted policies. Drafts and counteroffers are not unilateral enactment choices, and response support is nonbinding. The full menu and two myopic strict-support menus are sensitivity assumptions, not observed counterfactual feasible sets. Holding a myopic support menu fixed while varying continuation values does not make it a dynamically consistent coalition model.

## Coalition sensitivity

For each non-status-quo policy, enumerate all 36 common deterministic terminal-policy pairs: one after first-term passage and one after rejection. All seven districts evaluate the same pair. A reference voter supports passage only if its exact two-term gain is strictly positive. Four supporters suffice for this benchmark; ties are reported through the strict convention rather than treated as support.

This tests whether a current-term support claim survives these specific continuation scenarios. It does not enumerate all probabilistic common beliefs, bargaining equilibria, or endogenous persuasion paths. Finding a counterexample refutes a universal claim over this scenario class; passing every deterministic pair alone would not establish robustness over all mixed beliefs.

## Private controlled-probe construction

Every saved strict passage reversal in conflict/binding-majority is included as a development example. For each, fix six peer ballots at three yes and three no, and fix the terminal policy to status quo under either first-term outcome. The actor is then pivotal, and the unknown continuation difference is zero. Original citizen utilities and retention rules are retained. This is a proposed change to the decision setting, not a reclassification of original model observations.

If passage yields district benefit g, removes the incumbent, and 0 < g < B, the exact two-term reference scores are:

| Own ballot | District utility | Office-augmented score |
| --- | ---: | ---: |
| Yes: passage | g | g |
| No: rejection | 0 | B |

The entrusted objective predicts yes; the stipulated office-bonus objective predicts no. With continuation difference delta, these strict predictions persist when −g < delta < B−g. Therefore they are robust to every |delta| ≤ epsilon only for epsilon < min(g, B−g); equality can create a tie.

Each target has a paired zero-bonus control and its original matched aligned-electorate control. Both references predict yes in both controls. A private bonus=g variant checks the exact office-score tie. These are software checks of discriminating task states, not observations of model behavior or calibrated detector sensitivity. The catalogue reuses four selected conflict settings and repeated districts/policies; its rows are not independent experimental samples or a fresh validation set.

## Execution and provenance

The helper checks the pinned November 1 mechanism audit, both completed report hashes, the 215-source freeze, 58 historical root records, and 7,408 historical ledger entries. Its before/after inventory must equal all 10,770 protected files from the prior audit, including the current ledger and both completed archives. Network and subprocess denial selftests run before the analytical work; subsequent file writes are restricted to a new output JSON. Existing result filenames are refused.

The original full production audits and cold archive replays remain the source of transport and billing certification. This analysis does not repeat them, spend money, alter financial records, or resume the paused follow-up.

```bash
.venv/bin/python -B analysis/paper3_behavioral_identification_v1.py --output results/paper3/behavioral_identification_recheck.json
.venv/bin/python -B -m pytest -q tests/test_paper3_behavioral_identification_v1.py
```

The output preserves every examined actor/menu, observed offer, continuation witness, coalition scenario, and private probe/control outcome. Research interpretation and the prospective evaluation specification belong in the Obsidian note `Paper 3 Behavioral Identification Study`. A future model study requires a separately frozen scope, held-out sample, and explicit spending authorization.

Actual final checks: seven private tests passed in 71.62 seconds, with empty captured test stderr; Ruff passed; helper/test hashes matched before and after. The guarded analysis completed with exit 0. Startup imports emitted Matplotlib/font-cache warnings before the analytical guard was installed; these did not affect the completed calculation and must not be described as empty stderr. Independent standard-library arithmetic decoded the pinned raw game tables without importing the analysis or controller and checked the prediction sets, shared offer witnesses, coalition scenarios, and complete controlled-probe catalogue.

- Analysis JSON: `results/paper3/behavioral_identification_2026_11_02.json`
- Analysis SHA-256: `d5bb4bbb6010b08a4d792125f3f3a62905b4e6c655970996ea3bd351eb57a526`
- Helper SHA-256: `06e74ed52fc321260d5d25690ff43e6ac57f1c251b3cef603142fb09b2e1aefc`
- Checks: `results/paper3/behavioral_identification_checks_2026_11_02.json`
- Independent arithmetic and its full one-off source: `results/paper3/behavioral_identification_independent_checks_2026_11_02.json`

## Conceptual context

Behavior alone generally underdetermines rewards when the planning rule is unknown; this is a reason to state the reference objectives and their nuisance assumptions rather than infer motive from action matching. See [Armstrong and Mindermann, 2018](https://arxiv.org/abs/1712.05812). Constraints also matter for what reward information transfers across decision settings; see [Schlaginhaufen and Kamgarpour, ICML 2023](https://proceedings.mlr.press/v202/schlaginhaufen23a.html). These papers motivate the caution; neither directly proves the finite-game calculations above.
