"""Small locked local-model probe of portfolio vs issue-by-issue authority."""

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
from paper3.logrolling import (
    LinkInstitution,
    complementary_scenario,
    extraction_scenario,
    independent_majorities_scenario,
    run_linked_vote_probe,
    unilateral_loss_scenario,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="mlx-community/Qwen3-8B-4bit")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--output", type=Path, default=Path("results/paper3/logroll_probe_qwen.jsonl"))
    parser.add_argument("--cache-dir", type=Path, default=Path("results/paper3/cache/logroll_probe_qwen"))
    parser.add_argument("--institutions", nargs="+", choices=[item.value for item in LinkInstitution], default=[item.value for item in LinkInstitution])
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    lock = args.output.with_suffix(args.output.suffix + ".lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise SystemExit(f"another logroll probe is already writing {args.output}") from exc
    backend = CachedChatBackend(OpenAICompatibleLocalBackend(model=args.model, base_url=args.base_url, timeout_seconds=300), args.cache_dir)
    completed = set()
    if args.output.exists():
        completed = {
            (row["scenario_id"], row["institution"])
            for row in map(json.loads, args.output.read_text(encoding="utf-8").splitlines())
            if row.get("status") == "completed"
        }
    with args.output.open("a", encoding="utf-8") as handle:
        for scenario in (
            complementary_scenario(),
            unilateral_loss_scenario(),
            independent_majorities_scenario(),
            extraction_scenario(),
        ):
            for institution_name in args.institutions:
                institution = LinkInstitution(institution_name)
                key = (scenario.scenario_id, institution.value)
                if key in completed:
                    continue
                try:
                    row = run_linked_vote_probe(scenario=scenario, institution=institution, backend=backend)
                    row["status"] = "completed"
                except (RuntimeError, ValueError) as exc:
                    row = {"scenario_id": scenario.scenario_id, "institution": institution.value, "status": "failed", "error": str(exc)}
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()
                print(f"{row['scenario_id']} {row['institution']} {row['status']}")


if __name__ == "__main__":
    main()
