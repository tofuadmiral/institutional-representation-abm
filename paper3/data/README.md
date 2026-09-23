# Exploratory pilot archives

`action_format_preflight.json` is a separate **no-model component-test report**,
not another pilot: installed grammar masks/controller, synthetic tokens/zero
logits, six schema shapes, 19 legal paths per closure mode, 17 malformed paths,
and fresh-state checks. It was produced by
`analysis/paper3_action_format_preflight.py`; no weights were loaded and no
inference calls occurred. It does not certify live stream integration. Its
source/runtime hashes are recorded without changing any prior frozen archive.

These are reproducibility records, **not confirmatory or publication evidence**.
Each ZIP contains a frozen manifest, exact source snapshots, request/response
JSON, session records and a read-only audit summary. Nothing is omitted merely
because it failed or produced a null result. API response timestamps, token use
and finish reasons are retained. All task data are synthetic.

Portability limitation: current specialized replay auditors use the original
absolute source paths and earlier run prerequisites in `results/`. These local
audit passes do not yet establish clean-checkout reproduction. Before a Paper 3
release, verify credential-free, offline replay from extracted bundles at a
different path without rewriting the frozen manifests or their hashes.

| Archive | Calls | Purpose |
|---|---:|---|
| `deepseek_disclosure_a3.zip` | 372 | Rerun of the a2 disclosure design on fresh seeds: gate 8/8, 4/4 complete profiles, zero integrity errors, zero transport re-issues. 12/12 locked proposals in scripted own-optimal sets; 16/16 enacted outcomes equal the scripted continuation. Leader-advantage interaction -0.253 and -0.230 (positive information), 0 and 0 (controls). $0.71873538. SHA-256 `9df40a12368e0effc618aec73576b3d0a320bb93ab882927ae14877debfc33b9`; audit `analysis/paper3_deepseek_disclosure_audit.py` |
| `deepseek_disclosure_a2.zip` | 166 | Authority x disclosure-timing pilot (gate a2 8/8 plus four theory-selected profiles). Periodic local network outages; 16 certified re-issues; three shards halted on uncertifiable outages. 0/4 complete profiles, interaction not estimable; 1004007 has 3/4 cells and all five observed locked proposals match scripted own-optimal sets. $0.391410265, zero integrity errors. SHA-256 `a630b560534ea3d6393228f0ec66f2b7929e3c5c1191b1c4295b2b42503028bc`; audit `analysis/paper3_deepseek_disclosure_audit.py`. Gate a1 (6/8, bare-number emission artifact) and the stream smoke call are preserved under `results/paper3/` |
| `deepseek_fresh_profiles_a1.zip` | 233 | Frozen eight-profile fresh batch, terminal: 3/8 complete pairs (two zero-contrast, one D→q/B→p6 with four gains, three losses); four pairs failed on transport/accounting or coordinated safety halt, one never admitted. Missingness bounds straddle zero; feasibility threshold not met; no paired effect. $0.529576863, zero integrity errors. SHA-256 `7cf1bdb391679023fd288fccd04b93e85c9441cdd260aa6588ed0f8fb199a649`; audit `analysis/paper3_deepseek_fresh_batch_audit.py` |
| `deepseek_long_agenda_a1.zip` |50|64K feasibility completed both episodes; D→p3, B→p1, five principals gain and two lose under B. All50 billing records certified, zero integrity errors; cost$0.10243818. Selected-profile discovery only |
| `deepseek_budgeted_agenda_a1.zip` |28|16K output feasibility; D completes25/25 and enacts p3, B fails third call at length cutoff. No paired result; cost$0.06110896, zero integrity errors |
| `deepseek_plain_agenda_a1.zip` | 17 | Fresh plain gate16valid/12objective exact; first legislature opening length-cutoff with no action,4,002reported tokens over4,000cap. Global safety stop; zero complete episodes. Gate$0.00933854 plus failed-call conservative reservation$0.003248163 |
| `deepseek_output_a1.zip` | 16 | Paired strict-schema versus plain output: strict6/8 exact, plain8/8; all16 valid. Two strict reasoning/final JSON mismatches; zero among six available plain observations. Cost$0.01259768; selected instrument diagnostic only |
| `deepseek_agenda_a1.zip` | 16 | Hosted DeepSeek V3.2/AtlasCloud FP8 reasoning screen: all 16 valid normal responses, 10/12 objective checks exact; four other cases format-only. Failed gate; zero legislature calls. Cost $0.01058912 |
| `symmetry_qwen_a1.zip` | 16 | Independent bill-utility swap and representative relabeling |
| `symmetry_mistral_a1.zip` | 16 | Same legacy-prompt audit; tokenizer warning retained as a caveat |
| `memory_qwen_a1.zip` | 204 | Four negotiated histories and 16 execution branches; instrument-validity concerns |
| `interface_qwen_a1.zip` | 42 | Selected-history true/false/neutral response-example diagnostic |
| `state_gate_qwen_a1.zip` | 18 | Selected-history factual role, utility and obligation reports |
| `state_gate_mistral_a1.zip` | 18 | Exact factual-request replay with pinned weights and corrected tokenization |
| `memory_mistral_a1.zip` | 158 | Same collective pilot; three histories completed, one invalid-action failure retained |
| `authorization_mistral_a1.zip` | 24 | Pivotal private choices; failed prerequisite, 14/24 exact, all four harmful offers accepted |
| `minimal_choice_mistral_a1.zip` | 16 | Balanced private-choice diagnostic; all payoffs correct, all losses accepted, no table/encoding contrast |
| `direct_runtime_mistral_a1.zip` | 4 | Unchanged requests through direct unbatched generation with fresh KV caches; all parsed answers matched server outputs |
| `qwen_reasoning_gate_a1.zip` | 32 | Paired reasoning modes: action accuracy 8/16 off, 16/16 on; enabled exactness 13/16 fails gate, so fresh checks were not run |
| `ministral_reasoning_gate_a1.zip` | 16 | Native reasoning screen; strict delimiter parser rejected one response, frozen score 15/16 |
| `ministral_native_validation_a1.zip` | 64 | Private choices 16/16, authorization 24/24, state facts 17/24; collective prerequisite failed |
| `pivotal_memory_ministral_a1.zip` | 72 | Controlled decisive votes; 57 token-limit failures, no defensible institutional effect |
| `pivotal_budget_ministral_a1.zip` | 24 | Unchanged factor-selected requests at 8,192 tokens; 22 valid, 15 fully exact; failed 23/24 completion threshold |
| `bonsai_native_validation_a1.zip` | 41 | Native-reasoning Bonsai: smoke 1/1, private 16/16, pivotal 24/24 exact; all three record views at ceiling |
| `bonsai_negotiated_memory_a2.zip` | 5 | Three negotiated histories all failed at the reasoning-token cap; no complete agreements or execution branches, so no institutional comparison |
| `bonsai_low_effort_a1.zip` | 3 | Selected-failure native-low-effort replay: 2 valid final answers, 1 length cutoff; no full negotiation or institutional comparison |
| `bonsai_budgeted_episode_a1.zip` | 10 | Budgeted reasoning: four private checks exact; sixth legislative decision exceeded the 400-character public-message cap (477), terminating the episode before signatures/votes; no institutional effect estimate |
| `bonsai_message_reporting_a1.zip` | 34 | Four exact private checks and one complete 30-decision episode; one first-round promise breach, all seven second-round state reports correct, and a consequential vote against the leader's own positive-utility project; one exploratory history, no institutional comparison |
| `bonsai_clarity_registry_a1.zip` | 28 | Same selected history: original and registry-only each 5/7 preference-consistent ballots; clarified presentation with or without registry 7/7; all four cells have the same policy/payoffs. Seven exact-control replays identical. No demonstrated registry benefit |
| `bonsai_agenda_a1.zip` | 60 | Eight exact private checks; all four agenda-rights episodes stopped at bare-policy-ID/JSON schema failures during pairwise voting. Both conflict arms locked p3/amended p6; both control arms locked/retained p7. No enacted outcomes or institutional effect estimate |
| `bonsai_format_gate_a1.zip` | 16 | Explicit-schema/constrained-answer screen: 16 valid normal completions; all 12 objectively scored cases exact, four pairwise cases format-only. Native reasoning enabled. Instrument validation only; no legislature rerun or institutional effect |
| `bonsai_structured_agenda_a1.zip` | 100 | All four legislature episodes complete. Conflict: D enacts p5 (5–2), B p6 (7–0); controls both p7 (7–0). Average regret improves but five principals lose relative to D; the predicted anticipatory compromise is absent. Selected discovery cases, not confirmation |

Direct-runtime records explicitly identify their origin: actual streamed
outputs are normalized into the existing response schema; they are not HTTP
responses. Prompt/generated token IDs and original server responses are retained.

The hosted DeepSeek archive SHA-256 is
`86f015ae4a173ee1185672de4976cefb3a2ac17b72a55f01c7985eee68229df5`.
Its verifier is `analysis/paper3_deepseek_agenda_audit.py`: zero integrity errors,
16 certified billing records, exact request/action replay, no retries or repairs.
One error concerns the binding selector; the other concerns an unselected
conditional ballot, not a realized policy outcome. These selected private checks
are not a population accuracy estimate or an institutional-effect result.
Provider internals/weights cannot be independently verified. No credentials are
included. The unused conditional 150-call phase is not represented as completed.

The memory pilot uses only two underlying profiles, each with issue utilities
swapped. Branches and agents are dependent observations, not independent samples.
The interface and state diagnostics deliberately reuse a selected failure case;
they cannot estimate population failure rates.

To inspect an archive, open `manifest.json` first, then `audit.json`, followed by
the referenced session and call files. `sources.json` contains the actual source
version for that run, even if later working-tree code changes.

For an existing unpacked results directory:

```sh
python analysis/paper3_pilot_audit.py results/paper3/memory_qwen_a1
```

Most archives were produced by `experiments/paper3_archive_pilot.py`. It verifies
source hashes, required session counts, referenced calls and ZIP integrity, and
refuses to overwrite an existing archive. It does not certify scientific validity.

The clarity × registry archive SHA-256 is
`71a306453c4236c87169870737526be776977dd0fbdd92a52247d7b10f1b2429`.
Its specialized audit is `analysis/paper3_clarity_registry_audit.py`; restore its
parent `bonsai_message_reporting_a1.zip` at the recorded results path as well.
All 28 raw/tokenization/controller checks passed. The generic `audit.json` inside
the ZIP is an integrity/count summary, not the four-cell scientific readout.

The agenda-rights archive SHA-256 is
`76ca0aec87e79b58bda553e6257136ac1831f39e1438532cd87c403c51d8be15`.
It uses `experiments/paper3_archive_agenda.py`, not the legacy memory-specific
packager. Its `audit.json` is the complete specialized agenda audit: 60 exact
request/tokenization/controller checks, eight gate replays and all four failed
episode replays, with no integrity errors. The prerequisite gate did not cover
the actual one-field ballot schema; gate success did not establish episode
feasibility. All generations terminated normally; failures were not token
cutoffs. No bare policy was silently converted to a valid JSON action.

This archive also includes `packaging/source.py` and `packaging/manifest.json`
with the post-run packager and member hashes. These are explicitly outside the
earlier experiment freeze. The only omitted run-directory file is the empty
process-coordination `writer.lock`; every experimental record is retained.
No further inference or change to the original run is authorized by archiving.

The format-gate archive SHA-256 is
`e0c96daca60203cfe63ce87eda2c0cb6cfab8da4b042440da51b2ab3263d7f48`.
Its `audit.json` contains all sixteen exact request/tokenization, thinking
controller/grammar-phase trace, accepted grammar-token path and scoring checks,
with zero integrity errors. Use `analysis/paper3_format_gate_audit.py` in the
pinned Bonsai environment for read-only replay. Its `--archive` option used the
shared lock-aware packager with this specialized auditor; the ZIP includes the
packaging source and member hashes separately from the experimental freeze.
Cost: 8,493 output tokens, six forced boundary tokens, 9.14 generation minutes,
peak MLX allocation 11.60 GB. The explicit schema text and decoding constraint
were introduced together; this is not a causal ablation of those two changes.

The structured-agenda archive SHA-256 is
`2ffde71583260dc0563b61491df3c38e5910c28ebad967a6a6e9b31491223c98`.
Use `analysis/paper3_structured_agenda_audit_followup.py` for its full read-only
verification. The original frozen auditor remains unchanged and is retained in
the bundle, including its 44 public-message grammar replay failures. Those
failures arise from sorted JSON serialization reordering schema properties;
LLGuidance compiled the original insertion order during generation. The
separately identified post-run verifier replays frozen request construction to
recover exact runtime order, checks semantic schema equality, and verifies all
100 token paths. Zero unresolved integrity errors; all request/action/outcome,
tokenization, controller and phase-trace checks pass. The follow-up verifier and
its tests are embedded in `audit.json` under post-run provenance, not represented
as part of the earlier experiment freeze. No raw response or score was edited.

All 100 generations terminated normally; 33 reasoning closures were forced and
67 natural. There were 60,055 output tokens (66 forced boundary tokens), 231,184
input tokens, and peak MLX allocation 11.74 GB. One 435-character public response
was retained/reported under the frozen overlength rule. `operational_notes.json`
documents the reversible low-battery pause/resume of the same process. Elapsed
call durations include macOS sleep and deliberate suspension: do not equate the
83,427.87-second sum with active computation. The pilot is terminal; no further
inference is authorized by this archive.
