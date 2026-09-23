# Paper 3 implementation — exploratory, not publication evidence

This directory contains experimental institution engines, not a finished paper.
Paper 1 remains frozen at `v1.0.2`; Paper 2 is separate in `paper2/`.

## Current instrumentation

- `../experiments/paper3_deepseek_disclosure_a3.py`: **rerun of the a2 disclosure design,
  frozen and terminal 2026-09-22; 4/4 complete profiles.** Same instrument and four
  theory-selected profiles, fresh seeds 261000+1000*index+position, after a clean 7-minute
  connectivity probe (81/81). Gate 8/8 (protocol `61f89ab2…`). 372 calls, zero integrity
  errors, zero transport re-issues, $0.71873538; cumulative additional $1.834646191 of $10.
  **Readout (descriptive discovery, four profiles):**
  - All 12 locked proposals lie in the scripted own-optimal sets; all 16 enacted outcomes
    equal the scripted continuation given the observed locks, so every observed interaction
    equals its theory prediction exactly.
  - Frozen interaction (late B - late D) - (early B - early D), leader advantage:
    positive-information 1004003 -0.253 and 1004007 -0.230; zero-information controls 0
    and 0. Mean regret: -0.035, +0.071, 0, 0. Worst regret: +0.072, +0.268, 0, 0.
  - 1004007 reproduces a2's locks (p4 when the ballot rule is known, p6 under the leader rule
    and under the lottery) on different seeds.
  - Reading: in these LLM legislatures, when authority is disclosed only after the leader
    commits, the leader loses exactly the value of information the scripted model assigns;
    the group-level effect has no consistent sign. Four profiles, one model/provider,
    ties retained; not confirmation, not equilibrium or motive evidence.
  Archive `data/deepseek_disclosure_a3.zip`, SHA-256
  `9df40a12368e0effc618aec73576b3d0a320bb93ab882927ae14877debfc33b9`.

- `../experiments/paper3_deepseek_disclosure_a2.py`: **authority x disclosure-timing
  pilot, frozen; terminal 2026-09-22, no complete profile** (Fuad chose option b). Per profile: early D
  and early B episodes plus a late condition whose nine-decision prefix runs under a
  public 1/2 rule lottery (`paper3/agenda_disclosure.py`), then clones into fresh D and B
  continuations: 91 decisions, every path 25, shared seeds 251000+1000*index+position.
  Four theory-selected profiles, chosen before any call by `select_profiles()`:
  positive-information 1004003 and 1004007, zero-information controls 1004000 and 1004005.
  Estimand: (late B - late D) - (early B - early D) in enacted mean regret, leader
  advantage and every principal's utility. The shared-prefix zero is true by construction.
  Transport (declared): streamed requests; an incomplete stream's charge is certified
  through the generation endpoint and the identical request re-issued once; failures stay
  episode-local except routing mismatch. A single live smoke call validated the stream
  fields (`results/paper3/deepseek_stream_smoke_a1/`, $0.00008954, instrument only).
  **a1 gate failed 6/8** (protocol `162e359b…`, preserved): both invalid answers had stray
  CJK tokens exactly where an unquoted number followed the colon; strings were clean.
  **a2** changes only that field to a string, same 8/8 standard: **passed 8/8**, gate
  protocol `80c19114a1b5e20646f3f5773f7fb3bfd747859a2ba19e10a49db516d962830d`, $0.005783.
  Caps $0.10 gate plus 4x$0.60/120 calls; cumulative additional spend stays under $10.
  Audit `../analysis/paper3_deepseek_disclosure_audit.py`. Discovery, not confirmation.
  **Terminal readout:** 166 calls, zero integrity errors, $0.391410265 (cumulative
  additional $1.115910811 of $10), 16 certified transport re-issues. Local network
  outages reset every open stream at the same second roughly every 5-6 minutes; provider
  records show those generations finished normally in 23-49 s. Shards 0, 2 and 3 halted
  on uncertifiable outages (URLError, nothing received; reservations retained).
  **Complete profiles 0/4; frozen interaction not estimable.** Profile 1004007 has 3/4
  cells: early D enacted p6, late D p6, late B p3, early B failed after its locked
  proposal. All five observed locked proposals match the scripted own-optimal sets:
  1004007 early D p6, early B p4, lottery p6; 1004003 early D q; 1004000 lottery p5.
  In 1004007 the leader under the lottery gambled on its favourite p6 (utility 15) and
  lost to amendment p3 (-92) when the draw was the ballot rule, while early knowledge of
  that rule produced the pre-emptive compromise p4 (-59). Descriptive, one profile,
  mean-regret interaction bounds [-0.442, 0.071]. Archive `data/deepseek_disclosure_a2.zip`,
  SHA-256 `a630b560534ea3d6393228f0ec66f2b7929e3c5c1191b1c4295b2b42503028bc`.

- `agenda_objective_benchmarks.py`: set-valued proposal benchmarks under the
  declared scripted continuation. Retains all primary-payoff ties and contrasts
  the leader's own objective with terminal mean normalized regret using exact
  rational arithmetic. Secondary compatibility checks, not equilibria, observed
  counterfactuals, mental-state inference or a replacement for primary outcomes.

- `agenda_invariance.py`: offline-only prospective robustness transformations.
  Role/policy bijections, catalog order and coherent positive principal-specific
  utility scaling; eleven tests verify payoff/rule isomorphisms, not LLM robustness.
  No control inference yet; this is outside all existing frozen protocols.

- `agenda_disclosure_benchmarks.py`: offline-only expected-utility benchmark
  for choosing a proposal before a rule lottery. Retains ties and reports raw
  and normalized information value under explicitly scripted continuations.
  Eleven tests; not an equilibrium or LLM finding. No disclosure experiment
  has been implemented, frozen or launched.

- `../experiments/paper3_deepseek_fresh_batch.py`: **frozen; terminal (feasibility not met)**,
  protocol `4081b8ca133752ceb81fd9513216e05598be81d0c933e8f2ccc679c33523e9af`,
  output `results/paper3/deepseek_fresh_profiles_a1/`;373 tests passed before freeze.
  Coordinates eight assigned fresh-profile pairs, at most four
  independent processes, serial calls within each pair;400calls/$3 maximum in
  eight non-transferable$0.375 allocations. Requires both64K predecessor episodes
  complete with a clean provenance audit. All eight shards freeze before calls.
  Runner `../experiments/paper3_deepseek_fresh_profiles.py`; aggregate audit
  `../analysis/paper3_deepseek_fresh_batch_audit.py`. Preserves unstarted/failed
  pairs, reports finite-menu missing-outcome bounds, and stops admission on safety
  failures. Offline tests use fabricated responses only; not research evidence.
  **Terminal 2026-09-22:** 233 calls, accounted $0.529576863 (cumulative
  additional $0.718308386 of $10); zero integrity errors; max call overlap 4.
  Complete pairs 3/8 (1002001-1002003): 1002001 and 1002002 enacted the same
  policy in both arms (zero contrast); 1002003 D->q, B->p6, mean regret
  -0.0604, four principals gained, three lost. Incomplete: 1002000 and 1002004
  (B failed, transport/accounting), 1002005 (B failed, coordinated safety
  halt), 1002006 (D failed), 1002007 never admitted. Complete-pair means
  (descriptive only): leader advantage B-D -0.0559, mean regret -0.0201.
  All-eight finite-menu missingness bounds straddle zero: leader advantage
  [-0.490, 0.270], regret [-0.211, 0.309]. No paired effect is established;
  failed pairs are not imputed or rerun. Archive
  `data/deepseek_fresh_profiles_a1.zip`, SHA-256
  `7cf1bdb391679023fd288fccd04b93e85c9441cdd260aa6588ed0f8fb199a649`.

- `../analysis/paper3_agenda_adaptation.py`: no-model descriptive paired stage
  and principal-utility readouts, with selector-only replays on each fixed
  history. Three synthetic tests distinguish mechanical outcome changes from
  proposal changes and expose distributional losses hidden by a better mean.
  Failed pairs have no imputed outcomes. Not a provenance audit, seed check,
  causal-mediation analysis or a replacement for frozen primary endpoints.

- `../experiments/paper3_deepseek_long_agenda.py`: final output-cap feasibility
  escalation, fresh conflict39 seed232000 B then D,50calls/$2 maximum.
  Requested65,536 combined tokens,65,552 accounting bound, reasoning enabled;
  same institution and plain-output interface, inherited4K private gate.
  No retries, repairs or automatic follow-on. Frozen protocol
  `7ec40f9d2058dba502634d7c07e713eaac59276b8697e76d8bb07ee5e220d38d`,
  output `results/paper3/deepseek_long_agenda_a1/`;353 tests passed before
  inference. **Complete:**50/50 valid decisions, both episodes complete,
  zero audit errors; cost$0.10243818. D proposed/enactedp3; B proposed/enactedp1.
  B−D locked leader advantage−0.451515 and mean regret−0.228134;
  five principals gained, two lost. One selected profile, not confirmation.
  Archive `data/deepseek_long_agenda_a1.zip`, SHA-256
  `a2041f67eb9ad88641f72b6c17777af40f8c27b95cd11a79ff306e22a451e7cf`.
  Audit `../analysis/paper3_deepseek_long_agenda_audit.py`.
  Earlier failed configurations stay separate; feasibility is not paper evidence.

- `../analysis/paper3_agenda_fidelity.py`: secondary, no-model final-vote
  analysis separating majority-imposed principal losses from strictly harmful
  own votes. Exact one-vote deviations hold the recorded history and others'
  ballots fixed; off-path cards remain separate. Not motive inference or an
  alternative interaction trajectory. Unit tests include nonpivotal inconsistent
  votes, pivotal harmful votes and minority losses without an agent error.

- `../experiments/paper3_deepseek_budgeted_agenda.py`: two fresh conflict39
  episodes, D/B seed231000,50calls/$1 cap; plain output,16,384 requested output
  tokens with16-token provider-accounting tolerance reserved in advance.
  Reuses the completed4K plain private gate (not retested at16K). No retries,
  repairs or automatic follow-on; length failures never become valid actions.
  Protocol `5d2c17ece2c3630b98802955098ece8e12bfcebd774cbd892f2c62097dd33abd`,
  output `results/paper3/deepseek_budgeted_agenda_a1/`;344 tests passed before
  freeze. **Terminal:**28 calls, D completed25/25, B failed on its third call
  (length,16,386 completion tokens,no final action). No paired result.
  Cost$0.06110896; zero integrity errors and28 certified billing records.
  Archive `data/deepseek_budgeted_agenda_a1.zip`, SHA-256
  `015bb3c7fb714efd173e693e1358dc40106994483a08672af5abd7ee854dea8b`.
  Audit: `../analysis/paper3_deepseek_budgeted_agenda_audit.py`.
  Separate exploratory feasibility, not a continuation or rescore of failed4K calls.

- `../experiments/paper3_deepseek_plain_agenda.py`: plain-output successor,
  separately frozen after diagnostic comparison. Fresh labels/payoff magnitudes
  and seeds220000–220015 for the16-check prerequisite; conditional six25-call
  conflict39 episodes, paired seeds221000 D/B,222000 B/D,223000 D/B. Gate$0.10,
  episodes$0.36; reasoning on, no API response_format, strict local parser and no
  retries/repair/fallbacks. Protocol
  `38c87f0c5a30aba67152ed7a74089ac7364ecc342b0f02b91374eb37b2e2332d`,
  output `results/paper3/deepseek_plain_agenda_a1/`; all334 tests passed before
  freeze. **Terminal: gate passed, first episode failed at output cap.** All16 gate responses valid and
  normally terminated, all12 objective checks exact, four pairwise format-only.
  Gate cost$0.00933854. First opening returned no final action, length finish,
  4,002 reported completion tokens versus4,000 requested; frozen accounting guard
  halted globally.17 total calls, zero complete episodes. Failed-call reported
  cost$0.00194768, conservative reservation$0.003248163. Zero audit integrity errors.
  Archive `data/deepseek_plain_agenda_a1.zip`, SHA-256
  `1d80462f1bf27fa078fdfe68de1c200414094d4ef1385b819e5265ae5c35ecf4`.
  Audit: `../analysis/paper3_deepseek_plain_agenda_audit.py`.
  Same selected profile, not fresh-profile confirmation or a publication result.

- `agenda_benchmarks.py`: no-model, finite-menu lookahead and myopic benchmarks,
  sincere ratification and continuation-outcome pairwise voting, explicit tie
  conventions, majority/viability/Pareto certificates, and a deterministic spatial
  profile generator. Tests reproduce the prior analytical conflict/control cases.
  These are declared heuristics, not equilibria or observed LLM results. The
  generator alone is not a frozen confirmatory sample.

- `../experiments/paper3_deepseek_output_diagnostic.py`: 16-call hosted
  strict-schema versus plain-output diagnostic on all eight selector fixtures,
  paired seeds 200000–200007 with counterbalanced order. Only API response_format
  differs; messages and reasoning settings remain identical. Cap $0.10, no
  retries/fallbacks/repair or automatic legislature. Protocol
  `bb70215c45df0fd409b3e3186787593797e28f428707ae42bc9ac101ee42cfc6`,
  output `results/paper3/deepseek_output_a1/`; all315 tests passed before freeze.
  **Completed:** strict6/8 exact, plain8/8; all16 valid normal responses. Cost
  $0.01259768. Strict reasoning/final JSON mismatch2/8; plain0/6 available,
  with two unavailable observations. Audit zero integrity errors. Archive
  `data/deepseek_output_a1.zip`, SHA-256
  `1619eebd545cfb33dec74b4d8dbe2c7a9dbd141bca485c5fec616e2f3abe384d`.
  Verifier: `../analysis/paper3_deepseek_output_audit.py`.
  Returned reasoning JSON is described separately and never replaces final actions.
  This is selected instrument diagnosis, not a new competence gate or paper result.

- `../experiments/paper3_deepseek_agenda.py`: separately frozen OpenRouter
  DeepSeek V3.2 discovery, pinned AtlasCloud FP8, reasoning enabled and
  4,000 combined output tokens per call. Protocol
  `6e9e0c93a6327d217e762b04da3754fc6cbde0856dfec0ffa5336e965661c8c6`;
  output `results/paper3/deepseek_agenda_a1/`. Sixteen private checks must
  pass before three paired-seed conflict39 comparisons (six 25-call episodes).
  Separate $0.10/$0.36 spending ceilings; no retries, fallback models/providers
  or repaired answers. All 304 tests passed before freeze. **Completed: gate failed.**
  All 16 responses were valid, normally terminated and reasoning-evidenced;
  10/12 objectively scored checks were exact (four others were format-only).
  One binding-selector error and one off-path conditional-ballot error;
  no 150-call legislature phase was started. Actual charge: **$0.01058912**.
  Read-only audit: zero integrity errors. Archive: `data/deepseek_agenda_a1.zip`,
  SHA-256 `86f015ae4a173ee1185672de4976cefb3a2ac17b72a55f01c7985eee68229df5`.
  Do not restart this terminal experiment or relax its gate retrospectively.
  Audit: `../analysis/paper3_deepseek_agenda_audit.py`. Provider-reported
  usage/cost and exact request/action replay are checked; hidden provider
  tokenization/grammar internals and weight bytes cannot be independently checked.
  No credentials enter frozen sources or result artifacts. This is not a
  continuation of Bonsai or a matched-compute comparison between models.

- `../experiments/paper3_bonsai_agenda_seed_stability.py`: approved six-episode
  stochastic repeatability check on unchanged conflict39. Frozen protocol
  `42da6ce2a109699617673f4ed2fcdb7e14832def7d5f1b0bc6fca531395599cf`;
  output `results/paper3/bonsai_agenda_seed_stability_a1/`. Seed blocks
  181000 D/B, 182000 B/D, 183000 D/B; each uses decision offsets 0–24.
  Maximum 150 calls / 230,400 output tokens, one native-reasoning worker.
  No new controls, gate calls, repairs, retries or automatic follow-on.
  Exact serialized schema and compiled grammar are saved before inference;
  prompts and decoding are unchanged. Audit:
  `../analysis/paper3_agenda_seed_stability_audit.py`. All 290 tests passed
  before freeze. **Interrupted after an earlier low-battery suspension:** 32 calls
  recorded without generation errors, one interrupted call marker; first D episode
  passed p3 5–2, paired B incomplete. No paired result or final audit yet.
  The old process is no longer present; do not regenerate its started call. These are paired
  stochastic replicates on one selected profile, not independent-profile evidence.

- `../experiments/paper3_bonsai_structured_agenda.py`: four-episode successor
  using explicit schemas and constrained final answers at every stage, with
  native reasoning unchanged. Protocol
  `b6865f2f21cec52970c6a80af4ffe7e2648c11b2f506d722d1914736568c58cb`;
  output `results/paper3/bonsai_structured_agenda_a1/`. Maximum 100 calls,
  153,600 output tokens, one worker; no extra gate calls, retries or follow-on.
  Preserves the original selected profiles and authority comparison, with fresh
  paired seeds. Public messages retain the original 400-character instruction
  and overlength reporting. All legal action choices remain permitted.
  `../analysis/paper3_structured_agenda_audit.py` replays complete requests,
  actions, outcomes, tokenization, thinking boundaries and grammar paths.
  The full suite passed 283 tests before freeze. **Completed:** 100 normally
  terminated calls, all four episodes complete, no generation errors or repairs.
  Conflict-D enacted p5 (5–2), conflict-B p6 (7–0), both controls p7 (7–0).
  Mean conflict regret fell 0.37636 → 0.30273, but five of seven principals
  preferred D's outcome. B's locked proposal was more leader-favoring, not the
  predicted anticipatory compromise. These are selected discovery cases.
  Archive: `data/bonsai_structured_agenda_a1.zip`, SHA-256
  `2ffde71583260dc0563b61491df3c38e5910c28ebad967a6a6e9b31491223c98`.
  Use `../analysis/paper3_structured_agenda_audit_followup.py` for full replay:
  the unchanged frozen auditor reconstructs public grammars in saved sorted-key
  order rather than runtime property order. The separately labeled post-run
  verifier recovers the exact schema order from frozen request construction,
  preserves the original 44 failures, and verifies all 100 runtime token paths
  with zero unresolved errors. Its source/tests are included in the archive;
  the full suite now passes 285 tests. No experimental record was changed.
  Output: 60,055 tokens including 66 forced boundary tokens; peak MLX 11.74 GB.
  Recorded wall durations include sleep and a reversible battery pause and must
  not be reported as active compute time. The worker exited; no follow-on run.
- `../experiments/paper3_bonsai_format_gate.py`: bounded sixteen-call successor
  for final-answer-constrained decoding, not a legislature run. Frozen protocol
  `25977965de8b0f19e0e6ecd1b7e89f2913600c3a64de12a59c3ac76d9073935c`;
  output `results/paper3/bonsai_format_gate_a1/`. Eight selector/pivotal checks
  plus eight actual one-field schema checks. Requires all sixteen valid normally
  terminated answers and all twelve objectively scored answers exact; four
  pairwise checks score format only. Grammar allows all legal choices and both
  booleans; native reasoning remains unconstrained until closure. Maximum 16
  calls/24,576 output tokens, one worker, no retries and no automatic follow-on.
  `../analysis/paper3_format_gate_audit.py` replays prompts, tokens, grammar paths,
  recorded phase transitions, controller overrides and scoring without inference.
  `../analysis/paper3_format_stream_preflight.py` separately checks the actual
  native decode loop with synthetic logits and no LLM weights. The full suite
  passed 278 tests before this protocol was frozen.
  **Completed:** all 16 answers valid, all 12 objectively scored cases exact;
  four pairwise cases are format-only, not four extra decision-accuracy successes.
  All generations terminated normally. All 16 exact request/tokenization,
  controller/phase-trace and grammar-path checks passed with zero integrity
  errors. Cost: 8,493 output tokens including six forced boundary tokens,
  9.14 generation minutes, peak MLX allocation 11.60 GB. Archive
  `data/bonsai_format_gate_a1.zip`, SHA-256
  `e0c96daca60203cfe63ce87eda2c0cb6cfab8da4b042440da51b2ab3263d7f48`.
  The worker exited. This validates the tested private action interface, not
  full negotiated episodes or an institutional effect. Explicit schema text
  and constrained decoding changed together; their separate effects were not
  identified. No legislature rerun follows automatically.
- `agenda_rights.py`: seven-principal finite-policy legislature with leader
  discretion versus binding majority amendment, matched speaking opportunities,
  simultaneous ballots and policy-specific conditional ratification. The final
  locked proposal is distinct from the revisable opening offer. Each episode has
  25 decisions. Invalid actions stop an episode without fabricated payoffs.
- `../experiments/paper3_bonsai_agenda.py`: approved eight-check gate followed
  conditionally by four episodes (108 calls maximum), native-reasoning Bonsai,
  1,536 output tokens per call. Frozen protocol
  `5c71e4272fbac0b9f2e8a1076925504cc7cfbebeb6a8f69d91f43d664046d581`.
  Two selected spatial-preference profiles are discovery fixtures, not a
  confirmatory sample. `../analysis/paper3_agenda_audit.py` replays exact requests,
  actions, resolution and token/controller accounting without model calls.
  Output: `results/paper3/bonsai_agenda_a1/`; the run is terminal and the worker
  exited. Sixty calls were recorded: all eight private checks were exact, but
  all four episodes stopped at pairwise ballots after a bare legal policy ID
  was returned instead of the required JSON object. No enacted outcome or
  payoff was imputed. The gate did not cover this exact one-field schema.
  Both conflict arms locked p3 and proposed amendment p6; both common-interest
  arms locked and retained p7. Thus the valid prefixes show no locked-proposal
  adaptation on these two selected profiles, not a precise population null.
  All 60 request/tokenization/controller checks and complete failure replays
  passed. Cost: 51,367 output tokens (62 forced boundary tokens), 59.37 minutes
  generation, peak MLX allocation 11.85 GB. One overlong public message was
  retained/reported under the frozen rule; it did not terminate its episode.
  Archive: `data/bonsai_agenda_a1.zip`, SHA-256
  `76ca0aec87e79b58bda553e6257136ac1831f39e1438532cd87c403c51d8be15`.
  No institutional outcome contrast, confirmation or automatic follow-on run.
- `../experiments/paper3_archive_agenda.py`: post-run packaging utility, outside
  the experiment freeze. Acquires the writer lock, requires a terminal run,
  invokes the unchanged specialized audit with full tokenization checks,
  preserves every raw record/source snapshot, refuses overwrites and verifies
  ZIP membership and bytes. Its namespace import bypasses only unrelated
  plotting imports in `analysis/__init__.py` in the pinned minimal runtime.
  Six packaging tests pass; with the later no-model fixture checks, the full
  suite contains 273 passing tests.
- `commitment_memory.py`: seven representatives, draft offers, simultaneous
  responses, a final offer, ratification, and two actual majority votes.
- `../analysis/paper3_action_format_preflight.py`: no-model component check for
  a possible structured-action successor. Exercises the installed grammar masks
  and native thinking controller using synthetic tokens and zero logits; no
  weights or model calls. Six schema shapes pass 19 legal answer paths under
  each of natural and forced closure, reject 17 malformed paths, and pass reset
  and clone checks. Report: `data/action_format_preflight.json`. This is not a
  live-generation integration test or evidence of model decision competence.
  The frozen agenda pilot and its archive remain unchanged; further inference
  still requires a new authorization and protocol.
- `audit_runtime.py`: single-writer output stores, immutable protocol/source
  hashes, and exact model request/response records.
- `../experiments/paper3_memory_pilot.py`: four shared negotiated histories,
  branched into transcript/registry and active/released-obligation conditions.
- `../experiments/paper3_interface_audit.py`: a selected-history diagnostic of
  boolean response examples, separate from the memory pilot.
- `../analysis/paper3_pilot_audit.py`: read-only count, provenance, failure,
  obligation-state and realized-utility checks. No significance testing on
  these small, dependent histories.
- `../experiments/paper3_bonsai_budgeted_episode.py`: separately frozen local
  feasibility pilot, four exact private checks followed conditionally by one
  30-decision transcript-only episode. Native reasoning stays on, with a disclosed
  1,024-token thinking counter within a 1,536-token total cap. Controller-forced
  boundary tokens are recorded separately; no answer repairs or retries.
  `../analysis/paper3_budgeted_episode_audit.py` replays raw requests, actions,
  payoffs and controller accounting. Completion is not institutional evidence.
- `../experiments/paper3_bonsai_message_reporting.py`: fresh successor using the
  same hard token limits and strict action checks. It records violations of the
  requested 400-character prose limit and preserves full messages instead of
  aborting. Four exact private checks condition one 30-decision episode. Prior
  frozen results are unchanged; no automatic institutional comparison follows.
- `../experiments/paper3_bonsai_clarity_registry.py`: frozen 28-call diagnostic
  branching the completed episode's seven final-vote requests into original or
  category-keyed menu presentation, each without or with a derived state summary.
  Exact original controls are newly generated; seeds, history, payoffs, action
  schema and reasoning budget are fixed. Protocol hash
  `acbc435e6402622896d5699bbc0660ad353741acb05f3fda6a4edcbf009d057c`.
  `../analysis/paper3_clarity_registry_audit.py` verifies requests, source snapshots,
  tokenization, controller accounting and scoring. No group outcome is imputed
  when a ballot is invalid. One selected history is not independent replication;
  the registry adds derived facts and tokens, not an isolated authority treatment.

The budgeted episode pilot finished with four exact private checks followed by
six legislative decisions. All ten generations terminated normally; the sixth
legislative decision had a 477-character public message, exceeding the frozen
400-character limit. The episode therefore failed before signatures or votes.
No missing choices or payoffs were imputed. All six legislative calls used the
disclosed forced thinking closure. Raw request, output-token/text, controller and
failure replay checks passed. Archive: `data/bonsai_budgeted_episode_a1.zip`,
SHA-256 `ecb7635df60b8c0bc3c227cfd1e37191d0ef6502a4f5b278cf1f6c87539038ef`.

The fresh message-reporting successor completed all 34 calls: four private checks
and one full episode. Signers were 0/1/2/4. B1 passed 6–1, but signer 2 voted no,
causing the remaining conditional promise to lapse. All seven agents correctly
reported no second-round obligation. A0 then failed with three yes votes (1/2/4).
Leader 0 voted no despite its +11 utility from A0; holding other recorded ballots
fixed, changing that vote would have passed A0. This is a descriptive single-case
counterfactual, not an institutional treatment effect or proof of intent. The
generated output suggests possible package-order/execution-order confusion.
No public message exceeded 400 characters, so completion cannot be attributed
to the relaxed prose-admission rule. All raw replay/tokenization checks passed.
Archive `data/bonsai_message_reporting_a1.zip`, SHA-256
`fe4b25a6b901120ee300af95084653826081d2c21d2e249146d82ddf7535a156`.
`../analysis/paper3_episode_readout.py` provides post-hoc payoff, policy-pivotality
and rule-state-pivotality diagnostics without generating counterfactual agents.

The 28-call clarity × registry diagnostic completed with all answers valid and
all seven original-control replays token-for-token identical. Preference-consistent
final ballots were 5/7 for the original presentation, 5/7 with registry alone,
7/7 with clarification alone and 7/7 with both. Registry alone corrected actor 4
but introduced an unbound negative-utility yes from actor 6, and a false obligation
report from actor 2. Clarification corrected both original ballot errors without
a registry. Every cell still rejected A0 with three yes votes and produced the
same realized utilities. These results disqualify this selected episode as
evidence of a registry benefit; they do not establish a general memory harm or
the model's internal causal process. The clarification bundles category-keyed
encoding and explanatory text; it is not an isolated syntax effect.
All 28 raw request/token/controller/scoring checks passed. Cost: 28,230 output
tokens, including 44 forced boundary tokens; 32.76 minutes generation; peak
MLX allocation 11.60 GB. Archive `data/bonsai_clarity_registry_a1.zip`, SHA-256
`71a306453c4236c87169870737526be776977dd0fbdd92a52247d7b10f1b2429`.
The model worker exited; no further runs follow automatically.

```sh
results/paper3/runtimes/bonsai2/bin/python analysis/paper3_clarity_registry_audit.py results/paper3/bonsai_clarity_registry_a1 --check-tokenization
```

The specialized audit also requires the parent records restored at
`results/paper3/bonsai_message_reporting_a1/` from their separate archive.

`../analysis/paper3_incentive_audit.py` is a separate post-hoc, no-model audit of
the menu's material incentives. It compares perfect agreement delivery with
positive-utility independent voting on the same agenda, not with zero utility.
For the completed episode, signer 4 receives 7 under full delivery versus 9 in
that no-agreement benchmark. A0/B0 permits a strictly improving majority coalition
relative to this benchmark; A0/B1 and A1/B0 cannot do so without a member losing;
A1/B1 already passes both projects under independent voting. These are analytic
properties, not measured new agent behavior, verified outside options in actual
LLM play, or equilibrium findings. The existing generator fixes these qualitative
support patterns across seeds. This helper does not alter frozen scoring.

The current memory pilot has instrument-validity concerns, including incorrect
principal-payoff statements. A 42-call selected-history audit changed literal
boolean examples to false or neutral schemas without changing the outputs; simple
example copying therefore did not explain the observed release-state error there.
A separate factual gate distinguishes utility extraction from state reports.
The subsequent 24-call private authorization gate failed (14/24 fully correct):
all four negative-payoff offers were accepted. The grounded collective runner
requires 24/24 and has not been run. A separate 16-call minimal-choice diagnostic
tests table scope and boolean versus labeled actions; it cannot replace this gate.
That diagnostic completed with all 16 utilities correct but all eight harmful
offers accepted, invariant to both factors. These fixtures cannot identify why
the model fails or establish a general model property. Four unchanged requests
were subsequently replayed through direct unbatched generation with fresh KV
caches; all parsed answers matched the server. This rules out a server-only
explanation on those requests, not shared tokenizer/weight/backend issues.
No institutional mechanism follows from this.

The subsequent paired Qwen reasoning check (`qwen_reasoning_gate_a1`) completed
32 calls. Disabled mode chose correctly in 8/16 cases and accepted all eight
harmful offers; enabled mode chose correctly in 16/16 but reported three
counterfactual payoffs incorrectly (13/16 fully exact). The frozen exactness
gate therefore failed and its conditional fresh checks were not run. No
collective experiment follows automatically. All 32 generations ended normally.
The same 2,048-token cap allowed very different realized output costs: 264 tokens
disabled versus 7,549 enabled. This is not a compute-matched institutional effect.

The native Ministral reasoning screen (`ministral_reasoning_gate_a1`) completed
16 generations with normal termination. Its strict gate failed 15/16: one
response emitted three opening reasoning markers and one closing marker, which
the frozen parser rejected. All 15 parsed responses had correct decisions and
payoffs. Secondary inspection of the rejected final JSON also found the correct
decision and payoff; this does not change its failed status. Conditional fresh
cases were not run. The archive preserves all calls, sources and the failure:
`data/ministral_reasoning_gate_a1.zip` (SHA-256
`afbfb2caba3939f506b7a530a69276288d5e276232418ce2587043eb54ebbc1b`).
Actual generation used 9,401 tokens and approximately 202.6 seconds, excluding
initial loading. This is an interface/capability check, not institutional evidence.

The subsequent native validation (`ministral_native_validation_a1`) completed
64 calls: fresh private choices 16/16 exact, authorization 24/24 exact, and
commitment-state facts 17/24 exact. Four completed state responses reported a
false obligation; three other responses reached the token limit. The planned
negotiated native pilot requires 64/64 and remains unrun. These failures are
preserved in `data/ministral_native_validation_a1.zip` (SHA-256
`1bf954632716541ac22386a28b423585351759dca99fbe18add7cd51aa2b4a10`).

`../experiments/paper3_pivotal_memory_diagnostic.py` instead measures state and
decision failures in a controlled diagnostic, without relabeling that gate.
Its 72-call protocol uses two new payoff profiles, four commitment states,
three focal representatives and transcript/event-index/registry views. Other
votes are scripted 3–3, making the focal ballot decisive. **These are not
seven-agent negotiations.** All views use native reasoning and the same
2,048-token output cap; records differ in input size and derived information.
`../analysis/paper3_pivotal_memory_audit.py` reports paired action errors, state
errors, harmful valid choices and failures without imputing missing payoffs.
The diagnostic completed with 57/72 token-limit failures and 15 valid final
answers; it does not establish an institutional effect. Frozen records are in
`data/pivotal_memory_ministral_a1.zip` (SHA-256
`37b84193d1d90cfd6fb9b0c7e5b6952d0d61f8eed35bdfd5783bb3d9250f3d27`).

`../experiments/paper3_pivotal_budget.py` replays a factor-selected 24-request
subset with an 8,192-token cap, unchanged prompts/seeds/runtime and recorded
token-prefix checks. It is a separate frozen feasibility diagnostic, not a
repair of the old results or a negotiated collective experiment.
Its eight underlying cases include only one costly live-obligation decision;
the two release cases are a positive-payoff signer and a never-bound outsider.
The subset cannot establish costly-release recognition by a former signer.
The replay completed: 22/24 schema-valid, 15/24 fully exact, with one token-limit
failure and one malformed final object. It failed the frozen feasibility threshold
of 23/24 valid answers. All 24 prompt/token-prefix replay checks passed. Among
valid answers, three votes and six obligation reports were wrong; three wrong
state reports nevertheless accompanied correct votes. These distinctions do not
identify internal beliefs. Generation used 84,051 output tokens and approximately
32.2 minutes, excluding loading. Preserved in `data/pivotal_budget_ministral_a1.zip`
(SHA-256 `160e36594d0a3de5040295f56eab0b1cc47afa7fbd622d849615f1b9da8d0af3`).

`../experiments/paper3_bonsai_validation.py` uses the pinned Bonsai 2 27B MLX
checkpoint (`3f926b415992eaa2ae9dd7b573706494d6bbf787`) and its bundled
rotation-aware loader in a separate environment. It freezes native medium
reasoning, an 8,192-token cap, one installation check, 16 gated private-choice
checks and 24 conditional pivotal probes. It does not replace earlier failed
gates or authorize a negotiated run. Audit raw outputs with
`../analysis/paper3_native_diagnostic_audit.py`; this is descriptive analysis,
not confirmatory inference. Jev is excluded from the current work.
The run completed 41/41 normally terminated, schema-valid and fully exact
responses. Transcript, event-index and registry views each scored 8/8: no
accuracy benefit from the registry on these fixtures. Raw rechecking found no
score/provenance discrepancies. All stages used 32,192 generated tokens and
approximately 31.6 minutes excluding loading; peak MLX allocation was 11.39 GB,
not total system memory. Archive `data/bonsai_native_validation_a1.zip` (SHA-256
`1f22f25bc29ac86c52a28177a1cd1bd8fb2531cab6e4608dad279f333f8e9e69`).

The publisher's Bonsai tokenizer loader emits a Mistral-regex warning under its
pinned Transformers version. The no-inference comparison in
`../experiments/paper3_bonsai_tokenizer_audit.py` found byte-identical tokenizer
files to official Qwen3.8-27B and identical token IDs for all 41 frozen prompts,
despite differing loaded tokenizer classes/regexes. No Mistral regex patch was
applied. This is prompt-specific validation, not general tokenizer equivalence.

`../experiments/paper3_bonsai_memory_pilot.py` is a separately frozen bounded
negotiation follow-up, not part of the current 41-call validation. It requires
that validation to finish, raw-verifies the private-choice gate and at least
23/24 schema-valid pivotal outputs, and rejects changed model/runtime/source
artifacts. It does not demand perfect state reports: these are outcomes.
Three agent-generated histories (profiles 503/601/709, assigned leaders 0/3/6)
would branch into three record views and two imposed-release conditions, at most
195 calls. This covers leadership types; it is not a causal comparison between
leaders, because profiles also differ. Native reasoning
and sampling are unchanged. New public messages are capped at 400 characters,
stated in the prompt; oversized outputs are rejected, never truncated/retried.
Every dynamic prompt is checked against the pinned official base tokenizer,
with an 8,192-input-token safety cap. Exact unsubmitted requests are retained on
preflight failure. Earlier frozen collective prerequisites remain unchanged.
This runner is adaptive discovery, not confirmation or evidence of a memory effect.
Protocol hash: `a8fd7b6bc96ed14523c5ef5e9c201b3a33826e6577b9c7e04c0d232277c2946c`.
Output: `results/paper3/bonsai_negotiated_memory_a2/`. No automatic larger run follows.
This batch completed with **zero of three negotiated histories completed**.
Five actual calls were made: two drafts finished normally; the other draft and
two first responses reached the 8,192-token cap without a final answer. All
execution branches were consequently skipped, not scored as successful or failed
votes. The mechanism-opportunity threshold failed; no institutional effect was
measured. All three failure paths were read-only replayed through their saved
requests/seeds to the recorded length cutoff. Generation used 27,683 tokens and
approximately 27.2 minutes, excluding loading; peak recorded MLX allocation was
11.27 GB. The worker exited normally. Frozen archive:
`data/bonsai_negotiated_memory_a2.zip` (SHA-256
`d1a073f2cf8bd130948d94164192079cd3e60701c424c489b6c5853de6a30ab7`).
The preserved `a1` directory contains only a zero-call freeze attempt: strict
reload rejected integer versus JSON-string utility keys before inference.
The new runner normalizes protocol metadata before freezing; a regression test
and a real freeze/reload check passed. No existing manifest was overwritten.

`../analysis/paper3_bonsai_memory_audit.py` read-only replays completed histories
and branches from the saved responses. It checks exact requests/seeds, frozen
source hashes, call provenance, token/cache accounting, and recomputed votes,
agreement state and per-principal payoffs. It never calls a model or supplies a
missing vote. Failed and incomplete histories remain explicit; failed sessions
are not fully replayed, and tokenization/hardware execution is not independently
certified by this audit. Unit fixtures verify that altered saved payoffs are detected.

`../experiments/paper3_bonsai_low_effort.py` is a separate three-call feasibility
diagnostic on the three recorded negotiation truncations. It changes only the
native template's reasoning effort from medium to low, keeping reasoning enabled,
task messages, seeds, sampling, output cap and message bounds unchanged. Before
inference it verifies exact medium prompt/token replay and that the low prompt
adds only the publisher's brief-thinking instruction, with matching base-tokenizer
IDs. It retains the rotation-aware loader and pinned runtime. This is selected-
failure diagnosis, not a negotiation-success estimate or institutional result;
passing does not authorize a larger run. Output:
`results/paper3/bonsai_low_effort_a1/`; protocol hash:
`8f6b51e1920342c6804539b1f20285ef2f393f1089a4d9ffc71759273b4c37be`.
The fixed diagnostic completed: **2/3 feasible final answers**, versus three
length cutoffs in the selected medium-effort source requests. Profile 503's first
response still exhausted 8,192 tokens; profile 601's draft finished in 5,559;
profile 709's first response finished in 8,114, only 78 below the cap. No complete
negotiation was attempted. Generation used 21,865 tokens and approximately 20.3
minutes, excluding loading. Source/request/prompt/token-accounting and raw-score
checks passed for all three, with zero cached tokens. Results do not estimate
general reliability, validate optimal bargaining or establish a memory effect.
Archive `data/bonsai_low_effort_a1.zip` (SHA-256
`ae0f836fca7372a9f7135e4e40e61c8db2ac807256f120e95b7ce76a5ccc0072`).

Do not interpret all-yes
votes as successful representation, or a zero registry effect as evidence that
institutional memory is generally unhelpful. Release interventions are imposed
by the experiment, not endogenous agent renegotiation. A registry adds derived
information and input tokens; it is not a perfectly token-matched treatment.
Likewise, a principal's loss or a negative-package signature does not by itself
demonstrate mandate abandonment: an individual vote may be non-pivotal.

## Local checks

### Reasoning-model setup

The new local second-model candidate is
`mlx-community/Ministral-3-8B-Reasoning-2512-4bit`, revision
`0b6f067915514745478c14fd55698fbb2d2863cc` (approximately 5.6 GB).
All 14 downloaded files passed `hf cache verify --fail-on-missing-files`.
This is **Ministral Reasoning**, not legacy Mistral Small 3 or Magistral.
Installation does not establish research-task competence.

A single installation smoke check loaded it with MLX-LM and
`tokenizer_config={"fix_mistral_regex": True}`, seed 42, temperature 0.7,
512-token cap and fresh KV cache. The native reasoning delimiters were present,
generation ended normally after 463 tokens, and the final response gave
17 × 19 = 323. MLX reported 5.06 GB peak memory for this short check, not total
system memory. It returned prose despite the single-integer request: this is
not a schema-compliance or capability gate. The process exited after the check.

```sh
.venv/bin/hf download mlx-community/Ministral-3-8B-Reasoning-2512-4bit \
  --revision 0b6f067915514745478c14fd55698fbb2d2863cc --max-workers 2
```

The supplied template uses native `[THINK]` / `[/THINK]` delimiters and inserts
the publisher's reasoning system instruction when no custom system message is
provided. A custom research system message must preserve that reasoning setup;
passing Qwen's `enable_thinking` flag alone is not equivalent. Score final answers
separately from reasoning and preserve the actual template/configuration.

The legacy `mlx-community/Mistral-Small-24B-Instruct-2501-4bit` weight cache was
removed to reclaim disk space; frozen outputs and source snapshots remain.
Exact historical weights can be restored with:

```sh
.venv/bin/hf download mlx-community/Mistral-Small-24B-Instruct-2501-4bit \
  --revision 51ed0c6d2f98a25d8a60f19994f0e86c944995e0
```

### Native Ministral capability runner

`../experiments/paper3_ministral_reasoning_gate.py` freezes 16 balanced private
choices plus 16 conditional fresh cases before generation. Both decisions and
counterfactual payoff reports must be exact in every first-stage case before
the fresh stage runs. It uses native reasoning, temperature 0.7, a fixed
per-case seed, a 2,048-token output cap and fresh KV caches. There is no
non-reasoning arm, output repair or automatic collective follow-on. Its native
system and final-answer formatting differ from the previous Qwen setup;
cross-run differences are not attributable to weights alone.

```sh
.venv/bin/python experiments/paper3_ministral_reasoning_gate.py \
  --model /Users/fali/.cache/huggingface/hub/models--mlx-community--Ministral-3-8B-Reasoning-2512-4bit/snapshots/0b6f067915514745478c14fd55698fbb2d2863cc \
  --output results/paper3/ministral_reasoning_gate_a1
```

Use `--freeze-only` to record the manifest without loading weights. For a new
replication, choose a new output directory; an unchanged directory resumes
completed records and rejects source/protocol changes.

### Tests and audits

```sh
python -m pytest -q tests/
python analysis/paper3_pilot_audit.py results/paper3/memory_qwen_a1
```

The runner freezes its manifest before calls, including exact profiles, model
revision, package versions, source hashes, and budgets. It saves a source snapshot.
Each session records the exact call keys. Responses ending for a reason other
than `stop` fail the affected branch; there are no parser repairs or model retries.
Failures remain recorded. Do not edit the manifest to resume changed code.

Run only one local model worker at a time. Before resuming, inspect the process
and output state: an interrupted task can leave its server or runner alive.
Use the original model/backend configuration and source version for exact resume.

The initial Qwen memory pilot command was:

```sh
python experiments/paper3_memory_pilot.py \
  --model mlx-community/Qwen3-8B-4bit \
  --model-revision 545dc4251c05440727734bcd94334791f6ab0192 \
  --output results/paper3/memory_qwen_a1
```

It expects a local OpenAI-compatible endpoint at `http://127.0.0.1:8013/v1`.
The server used thinking disabled, one decode/prompt worker, one cached sequence,
and a 512 MiB prompt-cache cap. A model revision in the manifest is provenance,
not a substitute for pinning the server's actual weights.

## Preserved audits

`../experiments/paper3_symmetry_audit.py` retains the earlier logrolling prompt
and 32-token budget. Qwen's four signatures were invariant across the four tested
conditions. Mistral's signatures reversed when bill utilities swapped but not
when agent identities were relabeled. This rejects the earlier symmetry-invariant
mandate interpretation on those fixtures. Mistral's server emitted a tokenizer
regex warning; the audit is tied to that runtime, not a clean new-model benchmark.

Legacy coalition, comprehension, soft-trade and logrolling modules are retained
for provenance. Their pilot outputs must not be pooled with the new protocol.
Research planning and interpretation live in Fuad's Obsidian research folder,
not here.
