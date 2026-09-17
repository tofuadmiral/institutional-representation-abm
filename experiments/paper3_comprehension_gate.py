"""Run the Paper 3 single-agent mandate-action gate on a local cached model."""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from agent_exploration.local_models import CachedChatBackend, OpenAICompatibleLocalBackend
from paper3.comprehension import evaluate_representative
from paper3.scenarios import PreferenceRegime, generate_scenario


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="mlx-community/Qwen3-8B-4bit")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--output", type=Path, default=Path("results/paper3/comprehension_gate_qwen.jsonl"))
    parser.add_argument("--cache-dir", type=Path, default=Path("results/paper3/cache/comprehension_gate_qwen"))
    args = parser.parse_args()
    lock_path = args.output.with_suffix(args.output.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise SystemExit(f"another comprehension gate is already writing {args.output}") from exc
    backend = CachedChatBackend(
        backend=OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url, timeout_seconds=300),
        cache_dir=args.cache_dir,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = set()
    if args.output.exists():
        completed = {
            (row["scenario_id"], row["representative_id"], row["order_block"])
            for row in map(json.loads, args.output.read_text(encoding="utf-8").splitlines())
        }
    with args.output.open("a", encoding="utf-8") as handle:
        for regime in PreferenceRegime:
            for seed in args.seeds:
                scenario = generate_scenario(seed=seed, regime=regime)
                for representative_id, mandate in enumerate(scenario.mandates):
                    for order_block in (0, 1):
                        key = (scenario.scenario_id, representative_id, order_block)
                        if key in completed:
                            continue
                        result = evaluate_representative(
                            scenario_id=scenario.scenario_id,
                            representative_id=representative_id,
                            mandate=mandate,
                            policies=scenario.policies,
                            order_block=order_block,
                            backend=backend,
                        )
                        row = {"regime": regime.value, **asdict(result)}
                        handle.write(json.dumps(row, sort_keys=True) + "\n")
                        handle.flush()
                        completed.add(key)
                        print(f"{scenario.scenario_id} representative={representative_id} order={order_block} exact={result.exact}")
    rows = [json.loads(line) for line in args.output.read_text(encoding="utf-8").splitlines()]
    counts = Counter(row["regime"] for row in rows)
    exact = Counter(row["regime"] for row in rows if row["exact"])
    valid = Counter(row["regime"] for row in rows if row["valid_json"])
    print("summary")
    for regime in PreferenceRegime:
        name = regime.value
        print(f"{name}: exact={exact[name]}/{counts[name]} valid={valid[name]}/{counts[name]}")
    by_case: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_case[(row["scenario_id"], row["representative_id"])].append(row)
    order_disagreements = sum(
        len({item["response_policy_id"] for item in values}) > 1
        for values in by_case.values()
        if len(values) == 2
    )
    print(f"option-order disagreements={order_disagreements}/{len(by_case)}")


if __name__ == "__main__":
    main()
