# Exploratory pilot archives

These are reproducibility records, **not confirmatory or publication evidence**.
Each ZIP contains a frozen manifest, exact source snapshots, request/response
JSON, session records and a read-only audit summary. Nothing is omitted merely
because it failed or produced a null result. API response timestamps, token use
and finish reasons are retained. All task data are synthetic.

| Archive | Calls | Purpose |
|---|---:|---|
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

Direct-runtime records explicitly identify their origin: actual streamed
outputs are normalized into the existing response schema; they are not HTTP
responses. Prompt/generated token IDs and original server responses are retained.

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

Archives were produced by `experiments/paper3_archive_pilot.py`. It verifies
source hashes, required session counts, referenced calls and ZIP integrity, and
refuses to overwrite an existing archive. It does not certify scientific validity.
