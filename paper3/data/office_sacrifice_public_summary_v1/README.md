# Controlled office-sacrifice diagnostic: public summary

These are the inspectable inputs and results for the November4,2026 controlled
diagnostic described in the [research notes](https://fuadali.com/blog/would-an-ai-representative-vote-itself-out.html).

- [JSON](office-sacrifice-results-2026-11-04.json): all96 assignments, exact system
  prompt, supplied game inputs/consequences, seeds, model parameters, observed
  actions and full person-level outcomes; also prior discovery/validation outcome
  summaries and offline offer-identification counts, with source hashes.
- [CSV](office-sacrifice-results-2026-11-04.csv): one row per assignment with
  condition, action, expected answer, validity, seed and relevant outcome measures.
  Factual-control outcome fields are empty because a factual answer is not an
  enacted institutional policy.

The files match all96 saved source observations and each other. They are explicit
derived summaries: raw provider logs, receipt observations, the financial ledger
and the standalone audit runtime are not included here. Hashes identify the
preserved complete artifacts; hashes alone do not make this a replay archive.
See the [archive guide](../README.md) for local portable-bundle provenance and
the [technical method](../../../analysis/paper3_office_sacrifice_probe_v1.md).

The four main conditions are paired versions of16 base games. All64 main ballots
approve, all16 harmful controls reject, and all16 balanced factual controls are
correct. There are no missing assignments. The office bonus changes zero observed
choices. In the binding/bonus24 condition, every accepted proposal replaces the
representative and gives a lower stipulated office score than rejection. All
selected beneficial policies harm five own constituents while increasing district
SUM. The narrow result is explicit-task mandate-following on one model; it does
not identify intrinsic motive, population behavior or spontaneous multiagent
negotiation. The previous institutional discovery failed to replicate.

SHA256:

| Artifact | SHA256 |
| --- | --- |
| Public JSON | `2afe8a6501fb7114913b069402447f45faf5b7486accfc10450126408db23265` |
| Public CSV | `748aa1260e7cc808170132af6eb6a15319556061d42a30f811e03b069e0f71e7` |
| Complete source report | `1116cf5c44e191fb30bc079cb2cd3637723f7bb105e917d14bc9c4edc076e801` |
| Exact production-audit record | `b04d1fd47165cbce5225181ef1bc20cb11386262b3fce4d3cd4934b831b2148e` |
| Actual cold-replay record | `f2ca2bf27d3999453b9d7ddf5df312afa9fd062f773a5908dcd6921c42d329c8` |
| Full local portable ZIP | `3f859ac9972190863f80c9369520d0db0b246dd20fc719f0afb3fa96d3ee1afb` |
