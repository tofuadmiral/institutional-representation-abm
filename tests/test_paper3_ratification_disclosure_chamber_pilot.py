"""Offline disclosure-design and fabricated transport tests; no model evidence."""
import json
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from experiments import paper3_ratification_disclosure_chamber_pilot as runner
from paper3 import direct_ratification as base
from paper3 import ratification_disclosure_chamber_design as design
from paper3.pivot_b_budget import BUDGET_ID, atomic


def metadata():
    c = runner.gate.channel
    return dict(data=dict(id=c.MODEL, endpoints=[dict(
        tag=c.TAG, provider_name=c.PROVIDER, model_id=c.MODEL,
        quantization="fp8", name=c.PROVIDER + " | " + c.MODELS[1],
        status=0, max_completion_tokens=16384, context_length=40960,
        uptime_last_30m=100, uptime_last_5m=100,
        supported_parameters=["reasoning", "max_tokens", "temperature",
                              "top_p", "top_k", "min_p", "seed",
                              "presence_penalty", "repetition_penalty",
                              "response_format"],
        pricing=dict(prompt="0.00000008", completion="0.00000028"))]))


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    budget = tmp_path / "budget"
    budget.mkdir()
    atomic(budget / "authority.json", dict(
        budget_id=BUDGET_ID, cap_usd="10.00",
        credit_purchases_authorized=False))
    report = dict(gate_passed=True, calls=10)
    prerequisite = dict(protocol=runner.GATE_PROTOCOL,
                        report_sha256=runner.t.sha(runner.t.canonical(report).encode()),
                        native_template=runner.request([], 0))
    monkeypatch.setattr(runner, "prerequisite",
                        lambda gate_root=runner.GATE_ROOT,
                        archive_root=runner.GATE_ARCHIVE: prerequisite)
    monkeypatch.setattr(runner, "prerequisite_paths", lambda *args: [])
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(
        planned_unique=sorted({a["seed_base"] + i for a in runner.assignments()
                               for i in range(16)}), overlap=[]))
    root = tmp_path / "run"
    runner.prepare(root, metadata=metadata(), ledger_root=budget)
    return root, budget


def trace(answer, gid, mode="valid"):
    frames = [dict(id=gid, model=runner.gate.channel.MODELS[1],
                   provider=runner.gate.channel.PROVIDER,
                   choices=[dict(index=0, delta=dict(reasoning="fabricated reasoning"),
                                 finish_reason=None)]),
              dict(choices=[dict(index=0, delta=dict(content=answer),
                                 finish_reason="stop")]),
              dict(choices=[], usage=dict(prompt_tokens=100,
                                          completion_tokens=100,
                                          cost=.0001,
                                          completion_tokens_details=dict(
                                              reasoning_tokens=80)))]
    if mode == "missing_reasoning":
        frames[0]["choices"][0]["delta"] = {}
    lines = [part for frame in frames
             for part in ("data: " + json.dumps(frame), "")]
    lines += ["data: [DONE]", ""]
    return dict(started_unix=time.time(), ended_unix=time.time(),
                http_status=200, generation_header=None, lines=lines,
                line_count=len(lines), byte_count=sum(map(len, lines)),
                error_type=None, secret_redacted=False)


def fake(prepared, mode="valid"):
    root, budget = prepared
    sent = []
    lock = threading.Lock()
    assignments = runner.assignments()
    seed_map = {a["seed_base"] + i: a for a in assignments for i in range(16)}
    first_seeds = {a["seed_base"] for a in assignments}

    def send(wire, secret):
        request = json.loads(wire)
        seed = request["seed"]
        assignment = seed_map[seed]
        with lock:
            gid = "fabricated-" + str(len(sent) + 1)
            sent.append(seed)
        if mode == "invalid_first_action" and seed in first_seeds:
            answer = '{"policy":"INVALID","message":""}'
        else:
            item = runner.profiles()[assignment["profile_id"]]
            favorite = item["favorite"]
            chosen = ("C" if mode == "all_c" or
                      (assignment["arm"] == "binding_ratification" and
                       item["distribution"] == "veto" and
                       not (mode == "private_misses" and
                            assignment["information"] == "private")) else favorite)
            task = request["messages"][-1]["content"].split("\n", 1)[1]
            if task.startswith("Choose an opening") or task.startswith("Choose the final"):
                answer = json.dumps(dict(policy=chosen, message="x" * 600))
            elif task.startswith("Respond"):
                answer = json.dumps(dict(support=True, preferred_policy=chosen,
                                         message="x" * 600))
            else:
                answer = '{"vote":true}'
        return trace(answer, gid, mode)

    def lookup(gid, secret):
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    started_unix=time.time(), ended_unix=time.time(),
                    data=dict(id=gid, model=runner.gate.channel.MODELS[1],
                              provider_name=runner.gate.channel.PROVIDER,
                              total_cost=.0001))

    terminal = runner.execute(root, budget, secret="fixture-secret",
                              send=send, lookup=lookup, sleep=lambda _: None)
    return terminal, sent


def test_distribution_match_and_chamber_opportunity():
    for game_id, (favorite_support, compromise_support) in enumerate(design.SUPPORT_TARGETS):
        pair = design.game_pair(game_id)
        yes, veto = pair["approve"], pair["veto"]
        favorite = pair["favorite"]
        outsider = f'r{pair["outsider"]}'
        totals = base.district_totals(yes)
        assert totals == base.district_totals(veto)
        assert base.poll(yes, favorite)["yes_counts"][outsider] == 5
        assert base.poll(veto, favorite)["yes_counts"][outsider] == 4
        assert not base.poll(veto, favorite)["approved"]
        assert base.poll(veto, "C")["approved"]
        assert len(pair["favorite_support"]) == favorite_support
        assert len(pair["compromise_support"]) == compromise_support
        assert any(totals[f"r{actor}"]["C"] < 0 for actor in base.ACTORS)
        assert all(yes["districts"][d] == veto["districts"][d]
                   for d in yes["districts"] if d != outsider)

def test_new_action_interface_and_prompt_pairing():
    assert runner.game.parse_action(
        json.dumps(dict(policy="C", message="x" * 600)), "final")["policy"] == "C"
    assert runner.game.parse_action(
        json.dumps(dict(policy="C", message="x" * 1500)), "final")["policy"] == "C"
    with pytest.raises(ValueError, match="proposal action"):
        runner.game.parse_action(
            json.dumps(dict(policy="C", message="x" * 1501)), "final")
    pair = design.game_pair(0)
    for distribution in ("approve", "veto"):
        profile = pair[distribution]
        messages = {arm: runner.game.messages(profile, arm, "private",
                                               profile["proposer"], "draft", [])
                    for arm in base.ARMS}
        assert messages["advisory_poll"][1] == messages["binding_ratification"][1]
        content = json.loads(messages["advisory_poll"][1]["content"].split("\n", 1)[0])
        own = f'r{profile["proposer"]}'
        assert content["exact_visible_district_utility_sums"] == {
            own: base.district_totals(profile)[own]}
        assert set(content["visible_individual_citizen_preferences"]) == {own}
    assert len(runner.assignments()) == 54
    assert runner.scripted_preflight()["intended_calls"] == 864
    assert float(runner.scripted_preflight()["full_output_scripted_reservations_usd"]) < float(runner.CAP)


def test_distribution_prompt_and_certified_bulletin():
    for game_id in range(6):
        pair = design.game_pair(game_id)
        for arm in base.ARMS:
            prompts = {variant: runner.game.messages(
                pair[variant], arm, "public", pair["proposer"], "draft", [])
                for variant in ("approve", "veto")}
            assert prompts["approve"][0] == prompts["veto"][0]
            records = {variant: json.loads(prompts[variant][1]["content"].split("\n", 1)[0])
                       for variant in prompts}
            left, right = records["approve"], records["veto"]
            assert left["exact_visible_district_utility_sums"] == right["exact_visible_district_utility_sums"]
            assert {k: v for k, v in left.items() if k != "visible_individual_citizen_preferences"} == {
                k: v for k, v in right.items() if k != "visible_individual_citizen_preferences"}
            outsider = f'r{pair["outsider"]}'
            assert all(left["visible_individual_citizen_preferences"][district] ==
                       right["visible_individual_citizen_preferences"][district]
                       for district in left["visible_individual_citizen_preferences"]
                       if district != outsider)
            private = runner.game.messages(pair["veto"], arm, "private",
                                            pair["proposer"], "response", [])
            certified = runner.game.messages(pair["veto"], arm, "certified",
                                              pair["proposer"], "response", [])
            assert private == certified
            # A valid final-stage context must contain the public response
            # event; compare the information regime with that event fixed.
            event = dict(type="responses", responses=[])
            private_final = runner.game.messages(pair["veto"], arm, "private",
                                                  pair["proposer"], "final", [event])
            certified_final = runner.game.messages(pair["veto"], arm, "certified",
                                                    pair["proposer"], "final", [event])
            private_record = json.loads(private_final[1]["content"].split("\n", 1)[0])
            certified_record = json.loads(certified_final[1]["content"].split("\n", 1)[0])
            assert private_record["certified_yes_counts"] is None
            assert certified_record["certified_yes_counts"] == runner.game.certified_counts(pair["veto"])


def test_prerequisite_inventory():
    paths = runner.prerequisite_paths()
    assert runner.GATE_ARCHIVE / "bundle.json" in paths
    assert runner.GATE_ARCHIVE / "expected_report.json" in paths
    assert all(path.is_file() for path in paths)


def test_endpoint_uptime_gate():
    healthy = metadata()
    assert runner.check_endpoint(healthy)["uptime_last_5m"] == 100
    degraded = metadata()
    degraded["data"]["endpoints"][0]["uptime_last_5m"] = 80
    with pytest.raises(ValueError, match="uptime"):
        runner.check_endpoint(degraded)


def test_fabricated_full_path_archive_and_replay(prepared, tmp_path):
    terminal, sent = fake(prepared)
    report = runner.audit(*prepared)
    assert not terminal["global_safety_stop"]
    assert report["feasibility_passed"]
    assert report["completed_episodes"] == 54
    assert report["usable_actions"] == len(sent) == 864
    assert report["discovery_triage"]["interpretable_selected_cases"]
    assert report["discovery_triage"]["pathway"] == "both_sufficient_on_hard_games"
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    info = runner.export(*prepared, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    result = subprocess.run([sys.executable, "-I", "-S",
                             str(fresh / "code/experiments/paper3_ratification_disclosure_chamber_pilot.py"),
                             str(fresh), "--replay", "--expected-protocol",
                             info["protocol"]], env={}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    replay = json.loads(result.stdout)
    assert replay.pop("portable_replay")["exact_report_match"]
    assert replay == report


def test_control_shift_fails_screen(prepared):
    fake(prepared, "all_c")
    report = runner.audit(*prepared)
    assert report["feasibility_passed"]
    assert not report["discovery_triage"]["interpretable_selected_cases"]
    assert report["discovery_triage"]["pathway"] == "not_identified"


def test_discordant_information_path_is_predefined(prepared):
    fake(prepared, "private_misses")
    report = runner.audit(*prepared)
    assert report["feasibility_passed"]
    assert report["discovery_triage"]["interpretable_selected_cases"]
    assert report["discovery_triage"]["pathway"] == "discordant_information_on_hard_games"


def test_invalid_first_actions_retained(prepared):
    terminal, sent = fake(prepared, "invalid_first_action")
    report = runner.audit(*prepared)
    assert not report["feasibility_passed"]
    assert report["completed_episodes"] == 0
    assert len(sent) == 54
    assert not report["discovery_triage"]["coverage"]
    assert report["discovery_triage"]["pathway"] == "not_identified"
    assert not terminal["global_safety_stop"]


def test_reasoning_channel_failure_preserves_inventory(prepared):
    terminal, sent = fake(prepared, "missing_reasoning")
    report = runner.audit(*prepared)
    assert terminal["global_safety_stop"]
    assert not report["feasibility_passed"]
    assert report["completed_episodes"] == 0
    assert report["readout"]["assignments"] == 54
    assert 0 < len(sent) <= 4


def test_budget_and_source_tamper_guard(prepared):
    root, budget = prepared
    ledger = runner.Ledger(budget)
    ledger.allocate("earlier", "10")
    ledger.reserve("earlier", "old", "9.99", "0" * 64)
    with pytest.raises(ValueError, match="pre-stage budget changed"):
        runner.execute(root, budget)
    source = runner.t.load(root / "sources.json")
    source[next(iter(source))] += "\n# tampered\n"
    atomic(root / "sources.json", source)
    with pytest.raises(ValueError, match="source changed"):
        runner.verify(root)
