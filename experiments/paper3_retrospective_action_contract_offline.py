"""Read-only freeze verification and isolated offline controller equivalence.

No hosted runner, ledger writes or qualification inheritance. This is not an
institutional experiment or a replay that changes any historical verdict.
"""
# ruff: noqa: E402
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import socket
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def no_network(*args, **kwargs):
    raise RuntimeError("offline verification forbids network access")


socket.socket = socket.create_connection = no_network

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_action_contract as contract
from paper3 import retrospective_electorates as design
from paper3 import retrospective_keyed_interface as keyed


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(freeze_path):
    freeze = json.loads(freeze_path.read_text())
    if freeze["contract_version"] != contract.VERSION or freeze["paid_calls_authorized"] != 0:
        raise ValueError("offline contract freeze required")
    for name, expected in freeze["sources"].items():
        path = ROOT / name
        if path.resolve().is_relative_to(ROOT) is False or path.is_symlink() or digest(path) != expected:
            raise ValueError("changed frozen source: " + name)
    for name, expected in freeze["prior_manifests"].items():
        path = ROOT / name
        if digest(path) != expected:
            raise ValueError("changed historical manifest: " + name)
        for source, wanted in json.loads(path.read_text())["sources"].items():
            if digest(ROOT / source) != wanted:
                raise ValueError("changed historical source: " + source)
    for name, expected in freeze["historical_archives"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("changed historical archive")
    actions = episodes = 0
    for alignment in ("aligned", "conflict"):
        game = getattr(design.generate(3601002), alignment)
        for arm in institution.ARMS:
            def action(stage):
                if stage in ("draft", "final"):
                    return dict(policy=4, message="fixture é\n\t")
                if stage == "response":
                    return dict(support=True, counter_policy=1, message="fixture")
                return dict(vote=True)

            expected = institution.episode(game, arm, lambda a, i, t, s, c, n: action(s))
            for channel in ("tool", "json", "labelled_json"):
                def ask(actor, identity, term, stage, context, index):
                    nonlocal actions
                    old = keyed.messages(game, arm, actor, identity, term, stage, context)
                    new = contract.messages(game, arm, actor, identity, term, stage, context)
                    if (old[1] != new[1] or new[0]["content"].replace(contract.NEW, contract.OLD)
                            != old[0]["content"] or contract.structured(new, game, stage)["tools"]
                            != keyed.structured(old, game, stage)["tools"]):
                        raise ValueError("institution information/schema changed")
                    raw = json.dumps(action(stage))
                    delta = (dict(tool_calls=[dict(index=0, id="one", type="function", function=dict(
                        name="submit_decision", arguments=raw))]) if channel == "tool" else dict(
                            content=("submit_decision\n" if channel == "labelled_json" else "") + raw))
                    frame = dict(choices=[dict(index=0, delta=delta,
                                              finish_reason="tool_calls" if channel == "tool" else "stop")])
                    trace = dict(lines=["data: " + json.dumps(frame), "", "data: [DONE]", ""])
                    actions += 1
                    return contract.decode(game, stage, trace)

                actual = institution.episode(game, arm, ask)
                if asdict(actual) != asdict(expected):
                    raise ValueError("channel changed controller outcomes")
                episodes += 1
    return dict(verdict="offline_equivalence_pass", simulated_actions=actions,
                simulated_episodes=episodes, frozen_sources=len(freeze["sources"]),
                historical_closures=len(freeze["prior_manifests"]),
                freeze_sha256=digest(freeze_path), model_calls=0,
                limitation="Not fresh model qualification, reliability or scientific evidence.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("freeze", type=Path)
    print(json.dumps(verify(parser.parse_args().freeze), sort_keys=True))
