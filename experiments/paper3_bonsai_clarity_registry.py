"""Frozen 28-decision, selected-history clarity x derived-state diagnostic.

No negotiation is regenerated. Seven simultaneous final ballots are regenerated
in each presentation cell. This is not seven independent institutional episodes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_bonsai_budgeted_episode as old
from experiments import paper3_bonsai_message_reporting as parent_study
from paper3.audit_runtime import PilotStore, digest
from paper3.commitment_memory import PACKAGES, contract_state, parse, project_sequence

NAME = "bonsai-clarity-registry-selected-history-v1"
PARENT_HASH = "cea41c1699df02a050f23bc882ff3b1e8e55ee434f5858ad851067a5f6bb6ed7"
MAX_CALLS = 28
CELLS = ((False, False), (False, True), (True, False), (True, True))
CLARIFICATION = ('Package-menu keys A and B identify project categories, not execution sequence. '
                 'The final_offer.first field specifies which category is voted on first.')


def transform(messages, clear, registry):
    messages = copy.deepcopy(messages)
    if not clear and not registry:
        return messages  # Preserve the original content byte for byte.
    encoded, task = messages[-1]["content"].split("\n", 1)
    record = json.loads(encoded)
    if "derived_registry" in record:
        raise ValueError("parent already contains a registry")
    if clear:
        if record["package_menu"] != {str(i): list(pair) for i, pair in enumerate(PACKAGES)}:
            raise ValueError("unexpected original package menu")
        record["package_menu"] = {key: dict(A=pair[0], B=pair[1])
                                  for key, pair in record["package_menu"].items()}
        messages[0]["content"] += "\n" + CLARIFICATION
    if registry:
        record["derived_registry"] = contract_state(record["events"])
    messages[-1]["content"] = json.dumps(record, sort_keys=True) + "\n" + task
    return messages


def cases_for(records, episode):
    cases = []
    if episode["status"] != "completed" or len(episode["call_keys"]) != 30:
        raise ValueError("requires the completed actual episode")
    for actor in range(7):
        matches = [(key, row) for key, row in records.items() if row["request"]["seed"] == 123023 + actor]
        if len(matches) != 1:
            raise ValueError("missing or duplicated original final vote")
        key, original = matches[0]
        request = original["request"]
        record, task = request["messages"][-1]["content"].split("\n", 1)
        record = json.loads(record)
        if (key != episode["call_keys"][23 + actor] or record["representative"] != actor
                or record["principal"] != actor or record["events"] != episode["events"]
                or record["utilities_for_all_principals"] != episode["profile"]["utilities"]
                or "derived_registry" in record or not task.startswith("Before voting on A0,")):
            raise ValueError("unexpected parent history, actor, utility or task")
        if request != old.request_for(request["model"], request["messages"], 123023 + actor):
            raise ValueError("parent inference settings differ")
        # Predeclared rotation, not randomized independent replicates.
        rotation = actor % 4
        for clear, registry in CELLS[rotation:] + CELLS[:rotation]:
            cell = f"clear{int(clear)}-registry{int(registry)}"
            cases.append(dict(name=f"actor{actor}-{cell}", actor=actor, cell=cell,
                clear=clear, registry=registry, seed=123023 + actor, original_key=key,
                messages=transform(request["messages"], clear, registry)))
    return cases


def score(record, case, original):
    value = dict(status="failed", reply=None, state_correct=None, preference_consistent=None)
    encoded = case["messages"][-1]["content"].split("\n", 1)[0]
    context = json.loads(encoded)
    actor = case["actor"]
    state = contract_state(context["events"])
    _, project = project_sequence(context["events"])
    due = actor in state["signers"] and state["status"] == "second_vote_due"
    utility = context["utilities_for_all_principals"][str(actor)][project]
    value.update(expected_obligation_due=due, project_utility=utility)
    try:
        reply = parse(old.checked_answer(record), dict(obligation_due=bool, vote=bool))
        value.update(status="completed", reply=reply, state_correct=reply["obligation_due"] == due,
            preference_consistent=None if due else utility == 0 or reply["vote"] == (utility > 0))
    except ValueError as exc:
        value["error"] = str(exc)
    if not case["clear"] and not case["registry"]:
        value["control_replay"] = dict(
            request_identical=record["request"] == original["request"],
            generated_tokens_identical=record.get("generated_token_ids") == original.get("generated_token_ids"),
            response_identical=record.get("response") == original.get("response"),
            boundary_identical=record.get("boundary") == original.get("boundary"))
    return value


def aggregate(cases, sessions, episode):
    state = contract_state(episode["events"])
    first, second = project_sequence(episode["events"])
    first_event = next(e for e in episode["events"] if e["type"] == "first_vote")
    utilities = episode["profile"]["utilities"]
    result = {}
    for clear, registry in CELLS:
        label = f"clear{int(clear)}-registry{int(registry)}"
        subset = sorted([c for c in cases if c["cell"] == label], key=lambda c: c["actor"])
        rows = [sessions.get(c["name"], dict(status="missing")) for c in subset]
        valid = [r for r in rows if r["status"] == "completed"]
        cell = dict(valid=len(valid), invalid_or_missing=7 - len(valid),
            state_correct=sum(r["state_correct"] is True for r in valid),
            preference_consistent=sum(r["preference_consistent"] is True for r in valid),
            outcomes_available=len(valid) == 7)
        if len(valid) == 7:
            votes = [r["reply"]["vote"] for r in rows]
            passed = sum(votes) >= 4
            payoffs = [utilities[str(a)][first] * first_event["passed"] +
                       utilities[str(a)][second] * passed for a in range(7)]
            flips = []
            for actor in range(7):
                changed = list(votes)
                changed[actor] = not changed[actor]
                changed_passed = sum(changed) >= 4
                due = actor in state["signers"] and state["status"] == "second_vote_due"
                flips.append(dict(actor=actor, policy_pivotal=changed_passed != passed,
                    own_utility_gain_if_flipped=utilities[str(actor)][second] * (changed_passed - passed),
                    flipped_vote_breaches_obligation=due and not changed[actor]))
            cell.update(votes=votes, second_passed=passed, realized_utilities=payoffs,
                        total_utility=sum(payoffs), ballot_flips=flips)
        result[label] = cell
    return result


def prepare(parent):
    manifest = json.loads((parent / "manifest.json").read_text())
    if digest(manifest) != PARENT_HASH:
        raise ValueError("wrong selected-history predecessor")
    for name, expected in manifest["sources"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("frozen predecessor source changed: " + name)
    previous, sources = parent_study.prepare(Path(manifest["protocol"]["predecessor"]["path"]))
    if previous != manifest["protocol"]:
        raise ValueError("parent protocol no longer reproduces")
    records = {p.stem: json.loads(p.read_text()) for p in (parent / "calls").glob("*.json")}
    episode = json.loads((parent / "sessions/episode.json").read_text())
    if len(records) != 34 or len(list((parent / "sessions").glob("*.json"))) != 5:
        raise ValueError("unexpected predecessor size")
    cases = cases_for(records, episode)
    state = contract_state(episode["events"])
    if state["status"] != "condition_failed" or project_sequence(episode["events"]) != ("B1", "A0"):
        raise ValueError("unexpected selected-history state")
    protocol = {key: previous[key] for key in ("model", "model_revision", "model_file_sha256",
        "base_tokenizer", "base_file_hashes", "runtime", "runtime_source_sha256", "controller", "inference")}
    protocol.update(name=NAME, cases=cases, max_calls=MAX_CALLS, max_output_tokens=MAX_CALLS * old.CAP,
        max_input_tokens=old.MAX_INPUT,
        predecessor=dict(path=str(parent), manifest_hash=PARENT_HASH,
            records={str(p.relative_to(parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                for folder in ("calls", "sessions") for p in sorted((parent / folder).glob("*.json"))}),
        design="one selected actual history; all seven actors x 2 menu presentations x 2 registry conditions",
        execution_order="actor 0..6; rotate [(0,0),(0,1),(1,0),(1,1)] left by actor modulo 4",
        primary="strict validity, obligation report, unbound ballot preference consistency, exact-control replay stability",
        secondary="reaggregate all seven votes per complete cell with fixed first-round result; individual and total payoffs; fixed-other-ballot pivotal errors; input/output tokens and controller closure",
        scoring="native nonempty unique reasoning closure, normal finish, exact boolean schema, no cache; no imputation; no group outcome when any of seven ballots invalid",
        interpretation="if clarity alone removes apparent registry benefit, reject a state-memory interpretation for this case; if neither helps, do not tune further within this diagnostic",
        caveats=["selected on an observed failure; exploratory, not confirmatory or generalizable reliability evidence",
            "one history, not seven independent institutional units; no statistical significance claims",
            "registry adds computed facts and tokens; not compute-matched or a pure authority intervention",
            "same seeds do not guarantee identical tokens after changing prompts",
            "different positive and negative ballot errors can cancel at the policy level",
            "generated reasoning and self-reports do not establish internal causal beliefs"],
        failure_policy="complete all 28 scheduled decisions despite invalid answers; preserve raw errors; no repair, retry, fallback or replacement",
        interruption="started-call markers prohibit regeneration; technical interruption stops pending safe inspection",
        authorization="Fuad: yes approved, 19 September 2026; exactly this 28-call diagnostic, no automatic further inference")
    sources = sorted(set(sources + [Path(__file__).resolve(), ROOT / "analysis/paper3_clarity_registry_audit.py",
                                   ROOT / "tests/test_paper3_clarity_registry.py"]))
    return json.loads(json.dumps(protocol)), sources, records, episode


class DiagnosticBackend(old.BudgetBackend):
    def call(self, messages, seed, base):
        key = digest(dict(request=old.request_for(self.path, messages, seed), protocol=self.store.protocol_hash))
        if not (self.store.root / "calls" / (key + ".json")).exists():
            if len(list((self.store.root / "calls").glob("*.json"))) >= MAX_CALLS:
                raise ValueError("28-call diagnostic limit reached")
        return super().call(messages, seed, base)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    protocol, sources, originals, episode = prepare(args.parent)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(protocol["model"], local_files_only=True)
    base = AutoTokenizer.from_pretrained(protocol["base_tokenizer"], local_files_only=True)
    for case in protocol["cases"]:
        old.render(tokenizer, base, case["messages"])
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    if all((args.output / "sessions" / (c["name"] + ".json")).exists() for c in protocol["cases"]):
        print("Already terminal; no new inference", flush=True)
        return
    native = DiagnosticBackend(Path(protocol["model"]), store)
    for case in protocol["cases"]:
        path = args.output / "sessions" / (case["name"] + ".json")
        if path.exists():
            continue
        key, record = native.call(case["messages"], case["seed"], base)
        result = dict(score(record, case, originals[case["original_key"]]), case=case["name"],
                      actor=case["actor"], cell=case["cell"], call_keys=[key], protocol_hash=store.protocol_hash)
        store.save("sessions", case["name"], result)
        print(case["name"], result["status"], result["reply"], flush=True)
    print("TERMINAL: 28 decisions; no automatic follow-on", flush=True)


if __name__ == "__main__":
    main()
