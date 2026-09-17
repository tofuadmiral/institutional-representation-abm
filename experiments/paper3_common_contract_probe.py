"""Paired, bounded response probe with an identical exogenous contract per profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from agent_exploration.local_models import OpenAICompatibleLocalBackend
from paper3.coalition_probe import cached_backend, collect_private_positions, run_common_contract_response
from paper3.institution import AuthorityRule, CoalitionContract, outcome_metrics
from paper3.scenarios import PreferenceRegime, generate_scenario


def exogenous_contract(scenario, seed: int) -> CoalitionContract:
    """Frozen catalog rule: rotating four-member coalition and policy index.

    It is intentionally independent of model statements and authority arm.  The
    catalog should be expanded and frozen before any confirmatory use.
    """
    size = len(scenario.mandates)
    members = tuple((seed + offset) % size for offset in range(4))
    policy = scenario.policies[(seed + 2) % len(scenario.policies)].policy_id
    return CoalitionContract(formateur_id=members[0], members=members, policy_id=policy)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="mlx-community/Qwen3-8B-4bit")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument(
        "--regimes", nargs="+", choices=[item.value for item in PreferenceRegime], default=[PreferenceRegime.FRAGMENTED.value]
    )
    parser.add_argument("--output", type=Path, default=Path("results/paper3/common_contract_probe_qwen.jsonl"))
    parser.add_argument("--cache-dir", type=Path, default=Path("results/paper3/cache/common_contract_probe_qwen"))
    args = parser.parse_args()
    backend = cached_backend(OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url, timeout_seconds=300), args.cache_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    if args.output.exists():
        completed = {(item["scenario_id"], item["authority"]) for item in map(json.loads, args.output.read_text(encoding="utf-8").splitlines())}
    with args.output.open("a", encoding="utf-8") as handle:
        for name in args.regimes:
            for seed in args.seeds:
                scenario = generate_scenario(seed=seed, regime=PreferenceRegime(name))
                private, raw_private = collect_private_positions(scenario=scenario, backend=backend)
                contract = exogenous_contract(scenario, seed)
                for authority in AuthorityRule:
                    key = (scenario.scenario_id, authority.value)
                    if key in completed:
                        continue
                    try:
                        result = run_common_contract_response(scenario=scenario, private_positions=private, contract=contract, authority=authority, backend=backend)
                        result["outcome_metrics"] = outcome_metrics(mandates=scenario.mandates, policies=scenario.policies, record=type("Record", (), result["record"])())
                        result["raw_private_positions"] = raw_private
                        result["status"] = "completed"
                    except (RuntimeError, ValueError) as exc:
                        result = {"scenario_id": scenario.scenario_id, "authority": authority.value, "status": "failed", "error": str(exc)}
                    handle.write(json.dumps(result, sort_keys=True) + "\n")
                    handle.flush()
                    completed.add(key)
                    print(f"{result['scenario_id']} {result['authority']}: {result['status']}")


if __name__ == "__main__":
    main()
