"""Deterministic design check for Paper 3 authority rules.

This does not call an LLM and must never be reported as a behavioural result.
It verifies that rule variants have distinct, non-degenerate feasible regions before
we spend local-model compute.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from paper3.institution import AuthorityRule, contract_space, outcome_metrics, resolve_contract
from paper3.scenarios import PreferenceRegime, generate_scenario


def _nearest_policy_id(mandate, policies):
    return min(policies, key=mandate.loss).policy_id


def run_design_space(*, output_path: Path, seeds: range = range(8)) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for regime in PreferenceRegime:
        for seed in seeds:
            scenario = generate_scenario(seed=seed, regime=regime)
            majority = len(scenario.mandates) // 2 + 1
            for contract in contract_space(range(len(scenario.mandates)), scenario.policies, majority):
                vote_profiles = {
                    # The counterfactual where all named members support the deal is
                    # a rule sanity check. It should not be treated as behaviour.
                    "contract_support": {
                        mandate.principal_id: (
                            contract.policy_id
                            if mandate.principal_id in contract.members
                            else scenario.status_quo_id
                        )
                        for mandate in scenario.mandates
                    },
                    # The critical reference profile: every representative casts the
                    # individually nearest policy. Any later divergence caused by
                    # discipline is therefore attributable to the rule, not an
                    # assumed social vote.
                    "private_mandate_choice": {
                        mandate.principal_id: _nearest_policy_id(mandate, scenario.policies)
                        for mandate in scenario.mandates
                    },
                }
                for vote_source, requested in vote_profiles.items():
                    for authority in AuthorityRule:
                        record = resolve_contract(
                            mandates=scenario.mandates,
                            policies=scenario.policies,
                            status_quo_id=scenario.status_quo_id,
                            contract=contract,
                            requested_votes=requested,
                            authority=authority,
                        )
                        rows.append({
                            "scenario_id": scenario.scenario_id,
                            "regime": regime.value,
                            "vote_source": vote_source,
                            "authority": authority.value,
                            "contract_policy": contract.policy_id,
                            "accepted": record.accepted,
                            "reason": record.reason,
                            **outcome_metrics(mandates=scenario.mandates, policies=scenario.policies, record=record),
                        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    output = Path("results/paper3/design_space.csv")
    records = run_design_space(output_path=output)
    for authority in AuthorityRule:
        for source in ("contract_support", "private_mandate_choice"):
            subset = [
                row for row in records
                if row["authority"] == authority.value and row["vote_source"] == source
            ]
            accepted = sum(bool(row["accepted"]) for row in subset)
            overrides = sum(int(row["overridden_members"]) for row in subset)
            print(f"{authority.value}, {source}: {accepted}/{len(subset)} accepted; {overrides} overrides")
    print(f"wrote {output}")
