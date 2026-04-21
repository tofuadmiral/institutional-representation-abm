# institutional-representation-abm

# Goal

institutional-representation-abm is an agent-based modeling framework for studying how democratic institutions mediate political representation. The project simulates parliamentary and republican systems using individual agents representing legislators, constituencies, parties, and policy proposals. Legislators exhibit bias and imperfect responsiveness to constituent preferences, while institutional rules shape agenda control, party discipline, and electoral incentives. By comparing legislative outcomes to underlying constituency beliefs, the model evaluates representational fidelity, inequality of representation, and policy stability across systems. The goal is not to reproduce specific countries, but to isolate structural tradeoffs inherent in different democratic designs through reproducible, parameterized simulation experiments.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
python -m experiments.multiseed_comparison --scenarios all --seeds 200 --output results/phase_a
```

Entry points:
- `experiments/multiseed_comparison.py` — N-seed parallel runner (joblib), writes long-form CSV, summary CSV with bootstrap 95% CIs, and hypothesis-test CSV (Welch's t, Mann-Whitney U, Cohen's d).
- `experiments/scenarios.py` — canonical `ComparisonScenario` definitions.
- `config/institutions.py` — typed, frozen dataclasses (`ParliamentaryConfig`, `RepublicanConfig`, `CommitteeConfig`, `LegislatorConfig`). All mechanism knobs live here.
- `analysis/aggregate.py`, `analysis/plots.py` — aggregation and figure rendering.
- `docs/PHASE_A_NOTES.md` — reviewer notes for the statistical-hardening PR.

### Author
Ahmed Fuad Ali, 2025, all rights reserved.
