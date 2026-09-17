"""Falsification pilot: swap issue utilities and relabel representatives independently.

Reuses the original portfolio prompt, budget and resolver without repairing them.
The output is an audit of a prior exploratory interpretation, not confirmation.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper3.audit_runtime import PilotStore, RecordedBackend
from paper3.logrolling import (LinkInstitution, LogrollScenario, complementary_scenario,
                              run_linked_vote_probe)


def transformed(swap_bills: bool, relabel: bool):
    scenario = complementary_scenario()
    labels = {i: (6 - i if relabel else i) for i in range(7)}
    principals = tuple(replace(p, representative_id=labels[p.representative_id],
                               bill_a_gain=p.bill_b_gain if swap_bills else p.bill_a_gain,
                               bill_b_gain=p.bill_a_gain if swap_bills else p.bill_b_gain)
                       for p in scenario.principals)
    return LogrollScenario(f"symmetry-bill{int(swap_bills)}-label{int(relabel)}",
                           principals, tuple(labels[i] for i in scenario.named_members)), labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8013/v1")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    protocol = {"name": "prior-portfolio-symmetry-v1", "purpose": "exploratory falsification",
                "model": args.model, "base_url": args.base_url,
                "factors": {"swap_bill_utilities": [False, True], "reverse_agent_labels": [False, True]},
                "institution": "voluntary_portfolio_link", "max_tokens": 32,
                "expected_calls": 16, "temperature": 0,
                "server": {"enable_thinking": False, "decode_concurrency": 1,
                           "prompt_concurrency": 1, "prompt_cache_size": 1},
                "primary_audit": "signatures by underlying principal before/after bill swap",
                "interpretation_gate": "Any signature reversal under economically equivalent labels invalidates a stable mandate-interpretation claim on these fixtures"}
    store = PilotStore(args.output, protocol, [Path(__file__), ROOT / "paper3/logrolling.py",
                                              ROOT / "paper3/audit_runtime.py"])
    backend = RecordedBackend(args.model, args.base_url, store)
    for swap in (False, True):
        for relabel in (False, True):
            scenario, labels = transformed(swap, relabel)
            key = scenario.scenario_id
            if (args.output / "sessions" / (key + ".json")).exists():
                continue
            backend.call_keys.clear()
            try:
                result = run_linked_vote_probe(scenario=scenario,
                                              institution=LinkInstitution.VOLUNTARY_PORTFOLIO_LINK,
                                              backend=backend)
                result["signatures_underlying_ids"] = {
                    i: result["decision"]["signs"][labels[i]] for i in (0, 1, 3, 4)}
                result["status"] = "completed"
            except (ValueError, TimeoutError, OSError) as exc:
                result = {"status": "failed", "error": str(exc)}
            result.update(swap_bills=swap, relabel=relabel, call_keys=list(backend.call_keys),
                          protocol_hash=store.protocol_hash)
            store.save("sessions", key, result)
            print(key, result.get("signatures_underlying_ids", result.get("error")), flush=True)


if __name__ == "__main__":
    main()
