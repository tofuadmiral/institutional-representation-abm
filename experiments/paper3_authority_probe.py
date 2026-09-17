"""Bounded exploratory LLM probe; not a frozen or confirmatory experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from agent_exploration.local_models import OpenAICompatibleLocalBackend
from paper3.coalition_probe import cached_backend, collect_private_positions, run_authority_arm
from paper3.institution import AuthorityRule, outcome_metrics
from paper3.scenarios import PreferenceRegime, generate_scenario


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="mlx-community/Qwen3-8B-4bit")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    parser.add_argument(
        "--regimes",
        nargs="+",
        choices=[regime.value for regime in PreferenceRegime],
        default=[PreferenceRegime.FRAGMENTED.value, PreferenceRegime.PROTECTED_MINORITY.value],
    )
    parser.add_argument("--output", type=Path, default=Path("results/paper3/authority_probe_qwen.jsonl"))
    parser.add_argument("--cache-dir", type=Path, default=Path("results/paper3/cache/authority_probe_qwen"))
    args = parser.parse_args()

    backend = cached_backend(
        OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url, timeout_seconds=300),
        args.cache_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    if args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            completed.add((record["scenario_id"], record["authority"]))

    with args.output.open("a", encoding="utf-8") as handle:
        for regime_name in args.regimes:
            regime = PreferenceRegime(regime_name)
            for seed in args.seeds:
                scenario = generate_scenario(seed=seed, regime=regime)
                private_positions, raw_private_positions = collect_private_positions(
                    scenario=scenario, backend=backend
                )
                formateur_id = seed % len(scenario.mandates)
                for authority in AuthorityRule:
                    key = (scenario.scenario_id, authority.value)
                    if key in completed:
                        continue
                    try:
                        result = run_authority_arm(
                            scenario=scenario,
                            private_positions=private_positions,
                            formateur_id=formateur_id,
                            authority=authority,
                            backend=backend,
                        )
                        record = result["record"]
                        result["outcome_metrics"] = outcome_metrics(
                            mandates=scenario.mandates,
                            policies=scenario.policies,
                            record=type("Record", (), record)(),
                        )
                        result["raw_private_positions"] = raw_private_positions
                        result["status"] = "completed"
                    except (ValueError, RuntimeError) as exc:
                        result = {
                            "scenario_id": scenario.scenario_id,
                            "authority": authority.value,
                            "status": "failed",
                            "error": str(exc),
                        }
                    handle.write(json.dumps(result, sort_keys=True) + "\n")
                    handle.flush()
                    completed.add(key)
                    print(f"{result['scenario_id']} {result['authority']}: {result['status']}")


if __name__ == "__main__":
    main()
