# Frozen Jev data

Both ZIPs contain only synthetic study artifacts. They are complete snapshots,
including invalid probability outputs; nothing has been silently repaired.

| Archive | Calls | SHA-256 |
|---|---:|---|
| `bill_choice_pilot_a2.zip` | 96 | `762722d216df95514caa80f19f3f7838c2a49eb67a3daa09d03e6918dd6d2633` |
| `heldout_replication_a2.zip` | 840 | `79a936017d3baf1f94511644a1371c6413d7655c0eeda89185dbc4b2eba7e3a2` |

Each contains a named root directory with manifest, runner source snapshots,
requests/responses, pre-call attempt records, scored sessions and analysis JSON.
The pilot has 24 seeds but only 23 distinct semantic profiles. The held-out study
has 120 distinct profiles excluded from the pilot, each with seven conditions.
Two held-out probability distributions sum to 0.99; their selected labels remain
correct. See the analyzer's all-response choice counts versus valid-distribution
probability counts.

Extract into a new directory, then pass its named study directory to `audit.py`
or `analyze_replication.py`. No credentials or API calls are needed. Use the
repository Python environment with NumPy. Source snapshots are verified against
the original manifest hashes independently of the current checkout location.

Research interpretation is in the Obsidian note `Jev - Political Choice Report.md`.
Do not equate this synthetic preference-rule task with real voter prediction.
