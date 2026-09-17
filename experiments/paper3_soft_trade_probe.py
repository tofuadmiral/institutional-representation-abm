"""Locked, restartable paired experiment on voluntary soft-preference trades."""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from agent_exploration.local_models import CachedChatBackend, OpenAICompatibleLocalBackend
from paper3.coalition_probe import collect_private_positions
from paper3.scenarios import PreferenceRegime, generate_scenario
from paper3.soft_trade import SoftAuthority, run_soft_contract_response, select_trade_contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="mlx-community/Qwen3-8B-4bit")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0])
    parser.add_argument("--regimes", nargs="+", choices=[item.value for item in PreferenceRegime], default=["polarized_blocs", "fragmented", "protected_minority"])
    parser.add_argument("--output", type=Path, default=Path("results/paper3/soft_trade_qwen.jsonl"))
    parser.add_argument("--cache-dir", type=Path, default=Path("results/paper3/cache/soft_trade_qwen"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    lock = args.output.with_suffix(args.output.suffix + ".lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise SystemExit(f"another soft-trade run is already writing {args.output}") from exc
    backend = CachedChatBackend(OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url, timeout_seconds=300), args.cache_dir)
    completed = set()
    if args.output.exists():
        completed = {(row["scenario_id"], row["authority"]) for row in map(json.loads, args.output.read_text(encoding="utf-8").splitlines())}
    with args.output.open("a", encoding="utf-8") as handle:
        for name in args.regimes:
            for seed in args.seeds:
                scenario = generate_scenario(seed=seed, regime=PreferenceRegime(name))
                contract = select_trade_contract(scenario)
                private, raw_private = collect_private_positions(scenario=scenario, backend=backend)
                for authority in SoftAuthority:
                    key = (scenario.scenario_id, authority.value)
                    if key in completed:
                        continue
                    try:
                        row = run_soft_contract_response(scenario=scenario, contract=contract, private_positions=private, authority=authority, backend=backend)
                        row["raw_private_positions"] = raw_private
                        row["status"] = "completed"
                    except (RuntimeError, ValueError) as exc:
                        row = {"scenario_id": scenario.scenario_id, "authority": authority.value, "status": "failed", "error": str(exc)}
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                    handle.flush()
                    completed.add(key)
                    print(f"{row['scenario_id']} {row['authority']} {row['status']}")


if __name__ == "__main__":
    main()
