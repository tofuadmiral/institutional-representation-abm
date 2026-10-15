"""Fabricated transport only: not provider performance or agent findings."""
from copy import deepcopy
from decimal import Decimal
import json
import subprocess
import sys
import time
import zipfile

import pytest

from experiments import paper3_retrospective_serialization_gate_v1 as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic
from tests import test_paper3_retrospective_deepseek_gate as fixtures


def endpoint():
    value = deepcopy(fixtures.endpoint())
    row = value["data"]["endpoints"][0]
    row.update(tag=runner.route.TAG, provider_name=runner.route.PROVIDER,
               name=runner.route.PROVIDER + " | " + runner.route.MODEL_ALIAS,
               quantization="fp8", max_completion_tokens=147456)
    return value


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    (ledger / "entries").mkdir()
    atomic(ledger / "authority.json", dict(budget_id=BUDGET_ID, cap_usd="10.00",
                                           credit_purchases_authorized=False))
    atomic(ledger / "entries/old-pending.json", dict(stage="old", status="reserved", reserved_usd=".01"))
    atomic(ledger / "entries/old-uncertified.json", dict(stage="old", status="settled",
        reserved_usd=".01", accounted_usd=".01", certified=False))
    monkeypatch.setattr(runner, "seed_audit", lambda: dict(planned=[], overlap=[], historical_files=0))
    monkeypatch.setattr(fixtures, "runner", runner)
    root = tmp_path / "run"
    protocol = runner.prepare(root, metadata=endpoint(), ledger_root=ledger)
    return root, ledger, protocol


def fake(prepared, bad_at=None, native=True, certified=True, channel="tool",
         illegal_vote=False, inconsistent_count=False):
    lookup_case = {runner.qualification.SEED_BASE + index: case
                   for index, case in enumerate(runner.qualification.cases())}
    sends = []

    def send(wire, secret):
        request = json.loads(wire)
        sends.append(request)
        case = lookup_case[request["seed"]]
        if case["kind"] == "fact":
            action = (runner.qualification.presence.encode(case["expected"])
                      if runner.qualification.presence.terminal(case) else dict(case["expected"]))
            if len(sends) == bad_at:
                field = next(key for key, value in action.items() if type(value) is int)
                action[field] += 1
        elif case["stage"] in ("draft", "final"):
            action = dict(policy=0, message="fabricated")
        elif case["stage"] == "response":
            action = dict(support=False, counter_policy=0, message="fabricated")
        else:
            action = dict(vote=0 if illegal_vote else False)
        gid = "fabricated-" + str(len(sends))
        frames = [dict(id=gid, model=runner.route.MODEL_ALIAS, provider=runner.route.PROVIDER,
            choices=[dict(index=0, delta=dict(reasoning="fabricated" if native else ""), finish_reason=None)]),
            dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0, id="one", type="function",
                function=dict(name="submit_decision", arguments=json.dumps(action)))]), finish_reason="tool_calls")]),
            dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100, cost=.0001,
                                       completion_tokens_details=dict(reasoning_tokens=101 if inconsistent_count else 80)))]
        if channel != "tool":
            choice = frames[1]["choices"][0]
            content = json.dumps(action)
            if "fenced" in channel:
                content = "```json\n" + content + "\n```"
            choice["delta"]["content"] = ("submit_decision\n" if channel.startswith("labelled_") else "") + content
            if channel != "both":
                choice["delta"].pop("tool_calls")
                choice["finish_reason"] = "stop"
        # Actual provider form: null tool placeholder and repeated finish on usage.
        finish = frames[1]["choices"][0]["finish_reason"]
        frames[1]["choices"][0]["finish_reason"] = None
        frames.insert(2, dict(choices=[dict(index=0, delta=dict(content="", role="assistant",
                            tool_calls=None), finish_reason=finish)]))
        frames[-1]["choices"] = [dict(index=0, delta=dict(content="", role="assistant"),
                                      finish_reason=finish)]
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    lines=[item for frame in frames for item in ("data: " + json.dumps(frame), "")] +
                          ["data: [DONE]", ""], started_unix=time.time(), ended_unix=time.time())

    def lookup(gid, secret):
        if certified == "absent":
            return dict(http_status=404, error_type="HTTPError", secret_redacted=False, data=None)
        if not certified:
            return dict(http_status=503, error_type="HTTPError", secret_redacted=False, data=None)
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    data=dict(id=gid, model=runner.route.MODEL_ALIAS,
                              provider_name=runner.route.PROVIDER, total_cost=.0001))

    runner.execute(*prepared[:2], secret="fixture-secret", send=send, lookup=lookup, sleep=lambda _: None)
    return sends


def replay(prepared, tmp_path):
    root, ledger, protocol = prepared
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    runner.export(root, ledger, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    process = subprocess.run([sys.executable, "-I", "-S",
        str(fresh / "code/experiments/paper3_retrospective_serialization_gate_v1.py"), str(fresh),
        "--replay", "--expected-protocol", protocol], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["portable_replay"]["exact_report_match"]
    return report


def test_complete_all_tasks_and_isolated_replay(prepared, tmp_path):
    assert len(fake(prepared)) == 24
    report = runner.audit(*prepared[:2])
    assert report["gate_passed"] and report["calls"] == 24
    assert len(report["assignments"]) == 24 and not report["publication_evidence"]
    assert Decimal(report["accounted_usd"]) == Decimal(".0024")
    assert replay(prepared, tmp_path)["gate_passed"]
    with pytest.raises(ValueError, match="restart"):
        runner.execute(*prepared[:2], secret="fixture-secret")


@pytest.mark.parametrize("channel", ("json", "labelled_json", "fenced_json", "labelled_fenced_json"))
def test_all_facts_actions_and_isolated_replay_accept_exact_text_contract(prepared, tmp_path, channel):
    assert len(fake(prepared, channel=channel)) == 24
    report = runner.audit(*prepared[:2])
    assert report["gate_passed"] and report["calls"] == 24
    assert all(a["result"]["channel"] == channel for a in report["assignments"])
    assert replay(prepared, tmp_path)["gate_passed"]


def test_dual_channel_stops_even_when_both_actions_agree(prepared, tmp_path):
    assert len(fake(prepared, channel="both")) == 1
    assert not replay(prepared, tmp_path)["gate_passed"]


@pytest.mark.parametrize("options,expected", [(dict(bad_at=2), 24), (dict(native=False), 1),
                                             (dict(certified=False), 1)])
def test_stop_without_retries_and_preserve_reservations(prepared, options, expected):
    root, ledger, _ = prepared
    old = {p.name: p.read_bytes() for p in (ledger / "entries").glob("old-*.json")}
    assert len(fake(prepared, **options)) == expected
    report = runner.audit(root, ledger)
    assert not report["gate_passed"] and report["calls"] == expected
    assert all(a["status"] == "not_started" for a in report["assignments"][expected:])
    if expected == 24:
        assert not report["global_safety_stop"]
        assert report["assignments"][1]["failure_scope"] == "episode_failure"
    assert old == {p.name: p.read_bytes() for p in (ledger / "entries").glob("old-*.json")}


def test_failed_gate_isolated_replay(prepared, tmp_path):
    fake(prepared, bad_at=2)
    assert not replay(prepared, tmp_path)["gate_passed"]


@pytest.mark.parametrize("status", [200, 429])
def test_partial_stream_and_http429_never_reissued(prepared, tmp_path, status):
    sent = []
    def send(wire, secret):
        sent.append(wire)
        head = dict(id="fabricated-partial", model=runner.route.MODEL_ALIAS,
            provider=runner.route.PROVIDER, choices=[dict(index=0,
                delta=dict(reasoning="fabricated"), finish_reason=None)])
        return dict(http_status=status, error_type="HTTPError" if status == 429 else None,
            secret_redacted=False, lines=[] if status == 429 else ["data: " + json.dumps(head), ""],
            started_unix=time.time(), ended_unix=time.time())
    def lookup(gid, secret):
        return dict(http_status=404, error_type="HTTPError", secret_redacted=False, data=None)
    runner.execute(*prepared[:2], secret="fixture-secret", send=send, lookup=lookup, sleep=lambda _: None)
    assert len(sent) == 1
    report = runner.audit(*prepared[:2])
    assert not report["gate_passed"] and report["calls"] == 1
    assert all(a["status"] == "not_started" for a in report["assignments"][1:])
    assert Decimal(report["accounted_usd"]) == Decimal(runner.cases()[0]["reserved_usd"])
    assert not replay(prepared, tmp_path)["gate_passed"]


def test_route_cap_and_no_fallback():
    spec = runner.specification()
    assert Decimal(spec["full_reservation_usd"]) <= runner.CAP == Decimal(".30")
    assert spec["max_calls"] == 24 and spec["workers"] == 1
    assert len(runner.qualification.cases()) == 24
    assert sum(c["kind"] == "fact" for c in runner.qualification.cases()) == 12
    assert all(c["id"].endswith("-terminal") for c in runner.qualification.cases()[:4])
    assert sum("successor_present" in c["request"]["tools"][0]["function"]["parameters"]
               ["properties"] for c in runner.cases()) == 4
    assert all(type(p["type"]) is str for c in runner.cases() for p in
               c["request"]["tools"][0]["function"]["parameters"]["properties"].values())
    assert runner.qualification.FRAME_SEED == 3801001 and runner.qualification.SEED_BASE == 3802000
    for case in runner.cases():
        request = case["request"]
        assert request["provider"]["only"] == ["atlas-cloud/fp8"]
        assert request["provider"]["quantizations"] == ["fp8"]
        assert request["provider"]["require_parameters"]
        assert request["provider"]["allow_fallbacks"] is False
        assert request["reasoning"] == dict(enabled=True, exclude=False)
        assert request["tool_choice"] == "auto" and request["max_tokens"] == 14000


@pytest.mark.parametrize("field,bad", [("status", -2), ("quantization", "fp4"),
                                      ("provider_name", "DeepInfra"), ("supported_parameters", [])])
def test_metadata_rejects_incompatible_route(field, bad):
    metadata = endpoint()
    metadata["data"]["endpoints"][0][field] = bad
    with pytest.raises(ValueError):
        runner.route.check_endpoint(metadata)

def test_factual_failure_remains_failed_and_independent_cases_continue(prepared, tmp_path):
    assert len(fake(prepared, bad_at=1)) == 24
    report = replay(prepared, tmp_path)
    assert not report["gate_passed"] and not report["global_safety_stop"]
    assert report["assignments"][0]["failure_scope"] == "episode_failure"
    assert all(a["failure_scope"] == "passed" for a in report["assignments"][1:])


def test_new_inventory_is_fresh_and_substantive():
    cases = runner.qualification.cases()
    assert len(cases) == 24
    assert sum(c["kind"] == "fact" for c in cases) == 12
    actions = [c for c in cases if c["kind"] == "action"]
    assert {c["stage"] for c in actions} == {"draft", "response", "final", "vote"}
    assert {c["term"] for c in actions} == {0, 1}
    assert {c["arm"] for c in actions} == set(runner.qualification.institution.ARMS)
    assert Decimal(runner.specification()["full_reservation_usd"]) <= runner.CAP == Decimal(".30")
    assert runner.qualification.FRAME_SEED != runner.qualification.original.FRAME_SEED


def test_default_backend_is_actual_transport(prepared):
    from paper3 import hosted_reasoning_calls as base
    call = runner.service.Calls(prepared[0], prepared[1], runner.STAGE, 24,
        lambda: runner.verify(prepared[0]), runner.score, runner.CONFIG, secret="fixture-secret")
    assert call.send is base.transmit
    assert call.lookup is runner.t.receipt_lookup


@pytest.mark.parametrize("mutation", (None, "source", "specification", "approval"))
def test_production_readiness_pins_cannot_be_bypassed(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    source = tmp_path / "source.py"
    source.write_text("original")
    monkeypatch.setattr(runner, "closure", lambda root, roots: [source])
    monkeypatch.setattr(runner, "source_roots", lambda: [source])
    record = dict(sources={"source.py": runner.t.sha(source.read_bytes())},
        specification_sha256=runner.t.sha(runner.t.canonical(runner.specification()).encode()),
        qualification_approved=True, actual_model_calls=0, offline_tests=dict(passed=True))
    if mutation == "source":
        source.write_text("changed")
    elif mutation == "specification":
        record["specification_sha256"] = "wrong"
    elif mutation == "approval":
        record["qualification_approved"] = False
    path = tmp_path / "results/paper3" / (runner.STAGE + "_preflight.json")
    path.parent.mkdir(parents=True)
    atomic(path, record)
    if mutation is None:
        assert runner.readiness_check() == path
    else:
        with pytest.raises(ValueError):
            runner.readiness_check()


def test_legal_instrument_illegal_votes_fail_without_repair_or_global_stop(prepared, tmp_path):
    assert len(fake(prepared, illegal_vote=True)) == 24
    report = replay(prepared, tmp_path)
    assert not report["gate_passed"] and not report["global_safety_stop"]
    failures = [r for r in report["assignments"] if r["failure_scope"] == "episode_failure"]
    assert len(failures) == 4
    assert all(r["result"]["action"] is None for r in failures)


def test_four404_preserve_all_reservations_and_isolated_replay(prepared, tmp_path):
    assert len(fake(prepared, certified="absent")) == 24
    report = replay(prepared, tmp_path)
    assert report["gate_passed"]
    assert Decimal(report["accounted_usd"]) == Decimal(runner.specification()["full_reservation_usd"])
    root, ledger, _ = prepared
    entries = [json.loads(p.read_text()) for p in (ledger / "entries").glob(runner.STAGE + "-*.json")]
    assert len(entries) == 24 and all(e["certified"] is False for e in entries)
    assert all(len(json.loads(p.read_text())["receipts"]) == 4 for p in (root / "calls").glob("*.json"))


def test_inconsistent_native_usage_is_global_even_with_valid_action(prepared, tmp_path):
    assert len(fake(prepared, inconsistent_count=True)) == 1
    report = replay(prepared, tmp_path)
    assert not report["gate_passed"] and report["global_safety_stop"]
    assert report["assignments"][0]["failure_scope"] == "global_stop"


def test_qualification_public_message_prefix_preserves_fields():
    from tests.test_paper3_retrospective_serialization_contract import stream
    case = next(c for c in runner.qualification.cases() if c["kind"] == "action" and c["stage"] == "draft")
    raw = dict(policy=1, message="é" * 140)
    result = runner.qualification.score(case, stream(json.dumps(raw)))
    assert result["valid_action"] and result["exact"]
    assert result["requested_action"] == raw
    assert result["action"] == dict(policy=1, message="é" * 128)
    assert result["execution"]["clipped"]
    bad = dict(policy=1, message="x" * 130 + chr(133))
    assert not runner.qualification.score(case, stream(json.dumps(bad)))["valid_action"]
