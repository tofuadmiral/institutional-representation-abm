# Jev constituent-to-bill choice audit

This standalone study evaluates `jev-1.13.0` on synthetic, explicit preference
mandates. It does not predict real voters or measure real policy welfare.
Research interpretation and planning live in the Obsidian research vault.

## Implementation

- `bill_choice.py`: deterministic task generation and response scoring.
- `run.py`: original 24-seed, four-presentation pilot.
- `replication.py`: 120 semantically distinct held-out profiles, seven conditions.
- `run_replication.py`: sequential, recorded API calls with shared spending cap.
- `audit.py`: raw-response rescoring for either dataset.
- `analyze_replication.py`: source-snapshot checks, session consistency checks,
  paired contrasts, and profile-cluster bootstrap intervals.

The held-out conditions are plain political choice, its identical repeat,
reversed option order, changed bill labels, nonbinding chair endorsement,
isomorphic device selection, and its identical repeat. API request order is
shuffled once with a fixed seed. Semantic duplicates and pilot tasks are excluded.
The nonpolitical comparison changes multiple wording features together; it does
not isolate political framing alone.

## Verification

```sh
.venv/bin/python -m pytest tests/test_jev_*.py -q
.venv/bin/python jev_study/audit.py results/jev/bill_choice_pilot_a2
.venv/bin/python jev_study/analyze_replication.py results/jev/heldout_replication_a2
```

Analysis requires the recorded dataset. The final command rejects incomplete
samples. Invalid probability distributions remain flagged and excluded from
probability metrics, without normalization; their choice labels are separately
scored against the mandate and included in all-response choice accuracy.

## API execution

The runner defaults to freezing only. Executing requires `--execute`, an explicitly
authorized `--max-usd`, and a local `--key-file`. Never put a credential in a command,
source file, archive, or manifest. The study-wide ceiling is $20, or the lower CLI
limit, reserved conservatively across attempts in `results/jev`. It assumes the
documented $0.042/million input tokens and 64,000-token request maximum; verify
pricing before any new study. Existing unresolved attempts are never resent
automatically. Transport failures stop execution.

Do not overwrite frozen directories. `heldout_replication_a1` was freeze-only;
`heldout_replication_a2` corrects tuple/list manifest comparison without changing
the tasks. Old pilot `run.py` predates this resume fix; do not use it to resume an
existing directory. The original pilot is already complete.

Probabilities and the vendor's separate concentration-derived `confidence`
statistic are not interchangeable. The uniform four-option distribution has
Brier score 0.75; the deterministic preference-rule oracle has score 0. The oracle
is available because the benchmark stipulates the rule, not because real human
political preferences are known exactly.

API references: [Choice](https://docs.typesafe.ai/primitives/choice),
[confidence](https://docs.typesafe.ai/confidence),
[models/pricing](https://docs.typesafe.ai/models).
