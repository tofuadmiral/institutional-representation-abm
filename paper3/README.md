# Paper 3 implementation — exploratory, not publication evidence

This directory contains experimental institution engines, not a finished paper.
Paper 1 remains frozen at `v1.0.2`; Paper 2 is separate in `paper2/`.

## Current instrumentation

- `commitment_memory.py`: seven representatives, draft offers, simultaneous
  responses, a final offer, ratification, and two actual majority votes.
- `audit_runtime.py`: single-writer output stores, immutable protocol/source
  hashes, and exact model request/response records.
- `../experiments/paper3_memory_pilot.py`: four shared negotiated histories,
  branched into transcript/registry and active/released-obligation conditions.
- `../experiments/paper3_interface_audit.py`: a selected-history diagnostic of
  boolean response examples, separate from the memory pilot.
- `../analysis/paper3_pilot_audit.py`: read-only count, provenance, failure,
  obligation-state and realized-utility checks. No significance testing on
  these small, dependent histories.

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
