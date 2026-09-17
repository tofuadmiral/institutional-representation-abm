"""Selected-history comprehension audit; factual fields, not a welfare treatment."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import RULES, contract_state, parse
from experiments.paper3_memory_pilot import CompleteResponseBackend


def case(shared, actor, release, condition):
    events = copy.deepcopy(shared["events"])
    state = contract_state(events)
    if release:
        events.append(dict(type="mutual_release", offer_id=state["offer_id"],
                           consenting_signers=state["signers"],
                           origin="experimental_intervention_not_agent_generated"))
    state = contract_state(events)
    if condition == "facts_only":
        for e in events:
            e.pop("message", None)
            for response in e.get("responses", []):
                response.pop("message", None)
    utilities = shared["profile"]["utilities"]
    payload = dict(representative=actor, principal=actor, utilities_for_all_principals=utilities,
                   events=events, derived_registry=state)
    system = RULES
    if condition == "identity_header":
        system += f"\nYour representative ID is {actor}; your principal ID is {actor}. Your principal's project utilities are {json.dumps(utilities[str(actor)], sort_keys=True)}. Other speakers describe their own principals, not yours."
    task = "Report facts, without making a vote or giving advice. Return exactly five fields: principal_id (integer), utility_A0 (integer), utility_B0 (integer), package_A0_B0_total (integer), obligation_due (boolean: do YOU currently owe the second yes vote under final-2?). Derive each value from the record; no example answers are supplied."
    messages = [dict(role="system", content=system), dict(role="user", content=json.dumps(payload, sort_keys=True) + "\n" + task)]
    own = utilities[str(actor)]
    expected = dict(principal_id=actor, utility_A0=own["A0"], utility_B0=own["B0"],
                    package_A0_B0_total=own["A0"] + own["B0"],
                    obligation_due=actor in state["signers"] and state["status"] == "second_vote_due")
    return messages, expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8013/v1")
    args = parser.parse_args()
    shared = json.loads(args.source.read_text())
    original = json.loads((args.source.parents[1] / "manifest.json").read_text())["protocol"]
    protocol = dict(name="principal-and-obligation-factual-gate-v1", purpose="instrument diagnosis only",
                    source_hash=digest(shared), actors=[0, 3, 6], release=[False, True],
                    conditions=["full_context", "identity_header", "facts_only"],
                    model=original["model"], model_revision=original["model_revision"], runtime=original["runtime"],
                    temperature=0, max_tokens=128, max_calls=18,
                    primary="exact factual fields: ID, two own utilities, total, active obligation",
                    gate="do not interpret bargaining on an interface that fails factual role/utility checks",
                    limits="selected history, no generalization claim; identity header adds redundant information",
                    exclusions="none; no retries or repairs")
    sources = [Path(__file__), ROOT / "paper3/commitment_memory.py", ROOT / "paper3/audit_runtime.py", ROOT / "experiments/paper3_memory_pilot.py"]
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    backend = CompleteResponseBackend(original["model"], args.base_url, store)
    fields = dict(principal_id=int, utility_A0=int, utility_B0=int, package_A0_B0_total=int, obligation_due=bool)
    for release in protocol["release"]:
        for condition in protocol["conditions"]:
            for actor in protocol["actors"]:
                key = f"release{int(release)}-{condition}-actor{actor}"
                if (args.output / "sessions" / (key + ".json")).exists():
                    continue
                backend.call_keys.clear()
                messages, expected = case(shared, actor, release, condition)
                try:
                    reply = parse(backend.generate(messages, temperature=0, max_tokens=128), fields)
                    result = dict(status="completed", reply=reply, expected=expected,
                                  errors=[field for field in fields if reply[field] != expected[field]])
                except (ValueError, OSError, TimeoutError) as exc:
                    result = dict(status="failed", error=str(exc), expected=expected)
                result.update(actor=actor, condition=condition, release=release,
                              protocol_hash=store.protocol_hash, call_keys=list(backend.call_keys))
                store.save("sessions", key, result)
                print(key, result.get("errors", result.get("error")), flush=True)


if __name__ == "__main__":
    main()
