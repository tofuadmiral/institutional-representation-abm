from decimal import Decimal
import json
import subprocess
import sys
import time
import zipfile

import pytest

from experiments import paper3_retrospective_keyed_gate as runner
from paper3.pivot_b_budget import BUDGET_ID, atomic
from tests.test_paper3_retrospective_deepseek_gate import endpoint


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
    root = tmp_path / "run"
    protocol = runner.prepare(root, metadata=endpoint(), ledger_root=ledger)
    return root, ledger, protocol


def fake(prepared, failures=(), failure="eof", wrong_at=None, native=True, certified=True):
    now = [time.time()]
    contexts = {runner.qualification.SEED_BASE + i: c for i, c in enumerate(runner.qualification.cases())}
    sends, failed_gids, attempts = [], set(), {}

    def sleep(seconds):
        now[0] += seconds

    def send(wire, secret):
        request = json.loads(wire)
        sends.append(request)
        seed = request["seed"]
        index = seed - runner.qualification.SEED_BASE
        attempts[seed] = attempts.get(seed, 0) + 1
        broken = index in failures and attempts[seed] == 1
        case = contexts[seed]
        if case["kind"] == "fact":
            action = dict(case["expected"])
            if len(sends) == wrong_at:
                key = next(k for k, v in action.items() if type(v) is int)
                action[key] += 1
        elif case["stage"] in ("draft", "final"):
            action = dict(policy=0, message="fabricated")
        elif case["stage"] == "response":
            action = dict(support=False, counter_policy=0, message="fabricated")
        else:
            action = dict(vote=False)
        gid = "fabricated-" + str(len(sends))
        head = dict(id=gid, model=runner.route.MODEL_ALIAS, provider=runner.route.PROVIDER,
            choices=[dict(index=0, delta=dict(reasoning="fabricated" if native else ""), finish_reason=None)])
        frames = [head, dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(index=0,
            id="one", type="function", function=dict(name="submit_decision", arguments=json.dumps(action)))]),
            finish_reason="tool_calls")]),
            dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100, cost=.0001,
                                       completion_tokens_details=dict(reasoning_tokens=80)))]
        if broken:
            if failure == "eof":
                frames = [head]
                failed_gids.add(gid)
            elif failure == "length":
                frames[1]["choices"][0]["finish_reason"] = "length"
            elif failure == "identity":
                head["model"] = "wrong-model"
            elif failure == "illegal_action":
                frames[1]["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] = "not-json"
            else:
                raise ValueError("unknown fixture failure")
        lines = [line for frame in frames for line in ("data: " + json.dumps(frame), "")]
        if not (broken and failure == "eof"):
            lines += ["data: [DONE]", ""]
        return dict(http_status=200, error_type=None, secret_redacted=False, lines=lines,
                    started_unix=now[0], ended_unix=now[0])

    def lookup(gid, secret):
        if gid in failed_gids or not certified:
            return dict(http_status=404, error_type="HTTPError", secret_redacted=False, data=None)
        return dict(http_status=200, error_type=None, secret_redacted=False,
                    data=dict(id=gid, model=runner.route.MODEL_ALIAS,
                              provider_name=runner.route.PROVIDER, total_cost=.0001))

    runner.execute(*prepared[:2], secret="fixture-secret", send=send, lookup=lookup,
                   clock=lambda: now[0], sleep=sleep)
    return sends


def isolated_replay(prepared, tmp_path):
    root, ledger, protocol = prepared
    target, archive = tmp_path / "portable", tmp_path / "archive.zip"
    runner.export(root, ledger, target, archive)
    fresh = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(fresh)
    process = subprocess.run([sys.executable, "-I", "-S",
        str(fresh / "code/experiments/paper3_retrospective_keyed_gate.py"), str(fresh),
        "--replay", "--expected-protocol", protocol], capture_output=True, text=True, timeout=120)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["portable_replay"]["exact_report_match"]
    return report


def test_all_eighteen_primary_and_fresh_isolated_replay(prepared, tmp_path):
    assert len(fake(prepared)) == 18
    report = runner.audit(*prepared[:2])
    assert report["gate_passed"] and report["recovery_count"] == 0
    assert report["passed_logical_cases"] == 18 and len(report["assignments"]) == 36
    assert Decimal(report["accounted_usd"]) == Decimal(".0018")
    assert not report["publication_evidence"] and not (prepared[0] / "episodes").exists()
    assert isolated_replay(prepared, tmp_path)["gate_passed"]


def test_two_identical_transport_recoveries_preserve_reservations_and_replay(prepared, tmp_path):
    root, ledger, _ = prepared
    before = {p.name: p.read_bytes() for p in (ledger / "entries").glob("old-*.json")}
    sent = fake(prepared, failures=(0, 1))
    assert len(sent) == 20 and sent[0] == sent[1] and sent[2] == sent[3]
    report = runner.audit(root, ledger)
    assert report["gate_passed"] and report["recovery_count"] == 2
    expected = Decimal(".0018") + sum(Decimal(runner.cases()[i]["reserved_usd"]) for i in (0, 2))
    assert Decimal(report["accounted_usd"]) == expected
    assert before == {p.name: p.read_bytes() for p in (ledger / "entries").glob("old-*.json")}
    entries = [runner.t.load(p) for p in (ledger / "entries").glob("*.json")]
    assert sum(row.get("certified") is False for row in entries) == 3
    assert sum(row["status"] != "settled" for row in entries) == 1
    assert isolated_replay(prepared, tmp_path)["recovery_count"] == 2
    with pytest.raises(ValueError, match="restart"):
        runner.execute(root, ledger, secret="fixture-secret")


def test_third_transport_failure_exhausts_global_recovery_cap(prepared):
    sent = fake(prepared, failures=(0, 1, 2))
    assert len(sent) == 5
    report = runner.audit(*prepared[:2])
    assert not report["gate_passed"] and report["recovery_count"] == 2
    assert report["passed_logical_cases"] == 2
    assert all(row["status"] == "not_started" for row in report["assignments"][5:])


@pytest.mark.parametrize("options", [dict(wrong_at=2), dict(native=False), dict(certified=False),
    dict(failures=(0,), failure="length"), dict(failures=(0,), failure="identity"),
    dict(failures=(0,), failure="illegal_action")])
def test_no_recovery_of_content_native_billing_length_identity_failures(prepared, options):
    sent = fake(prepared, **options)
    assert len(sent) == (2 if "wrong_at" in options else 1)
    report = runner.audit(*prepared[:2])
    assert not report["gate_passed"] and report["recovery_count"] == 0


def test_wrong_recovery_answer_stops_without_third_attempt(prepared, tmp_path):
    sent = fake(prepared, failures=(0,), wrong_at=2)
    assert len(sent) == 2 and sent[0] == sent[1]
    report = runner.audit(*prepared[:2])
    assert not report["gate_passed"] and report["recovery_count"] == 1
    assert report["passed_logical_cases"] == 0
    assert not isolated_replay(prepared, tmp_path)["gate_passed"]


def test_recovery_event_tampering_rejected(prepared):
    fake(prepared, failures=(0,))
    path = prepared[0] / "sessions/recovery-001.json"
    event = runner.t.load(path)
    event["eligibility"]["reason"] = "different"
    atomic(path, event)
    with pytest.raises(ValueError, match="recovery eligibility"):
        runner.audit(*prepared[:2])


def test_recovery_request_tampering_rejected(prepared):
    fake(prepared, failures=(0,))
    path = prepared[0] / "calls" / (runner.cases()[1]["id"] + ".json")
    value = runner.t.load(path)
    value["request"]["seed"] += 1
    atomic(path, value)
    with pytest.raises(ValueError, match="provenance"):
        runner.audit(*prepared[:2])


def test_early_recovery_rejected_even_with_self_consistent_evidence_hash(prepared):
    fake(prepared, failures=(0,))
    root, ledger, _ = prepared
    case = runner.cases()[1]
    path = root / "calls" / (case["id"] + ".json")
    value = runner.t.load(path)
    event = runner.t.load(root / "sessions/recovery-001.json")
    value["admitted_unix"] = event["not_before_unix"] - 1
    atomic(path, value)
    entry_path = ledger / "entries" / (runner.STAGE + "-" + case["id"] + ".json")
    entry = runner.t.load(entry_path)
    entry["evidence_sha256"] = runner.t.sha(path.read_bytes())
    atomic(entry_path, entry)
    with pytest.raises(ValueError, match="early reissue"):
        runner.audit(root, ledger)


def test_fresh_frame_exact_facts_common_interface_and_full_path_bound():
    from paper3 import retrospective_labeled_qualification as older
    from paper3 import retrospective_deepseek_route as route
    spec = runner.specification()
    assert runner.qualification.FRAME_SEED != older.FRAME_SEED
    assert not set(range(runner.qualification.SEED_BASE, runner.qualification.SEED_BASE + 18)) & (
        set(range(older.SEED_BASE, older.SEED_BASE + 18)) | set(range(route.SEED_BASE, route.SEED_BASE + 18)))
    assert spec["logical_cases"] == 18 and spec["max_calls"] == 20
    assert Decimal(spec["full_reservation_usd"]) == Decimal(".21799616") < runner.CAP
    for first, second in zip(runner.cases()[::2], runner.cases()[1::2], strict=True):
        assert first["request_text"] == second["request_text"]
        assert first["request_sha256"] == second["request_sha256"]
        prompt = json.loads(first["request"]["messages"][1]["content"])
        assert prompt["data_layout"]["payoff_keys"] == ["term_t", "district_d", "policy_p"]
        assert first["request"]["max_tokens"] == 14000
        assert first["request"]["reasoning"] == dict(enabled=True, exclude=False)
    for case in runner.qualification.cases():
        if case["kind"] == "fact" and "counterfactual" in case["id"]:
            prompt = json.loads(case["messages"][1]["content"])
            assumptions = prompt["hypothetical_assumptions"]
            game, actor, arm = case["game"], case["actor"], case["arm"]
            policy = prompt["final"]["policy"]
            for vote in (True, False):
                enacted = policy if sum(assumptions["other_six_ballots"]) + vote >= 4 else 0
                values = [row[enacted] for row in game.utilities[0][actor]]
                majority = sum(v >= 0 for v in values) >= 5
                total = sum(values)
                retain = arm.startswith("advisory") or (majority if arm.endswith("majority") else total >= 0)
                future = sum(row[assumptions["second_term_enacted_policy"]] for row in game.utilities[1][actor])
                assert case["expected"]["score_if_yes" if vote else "score_if_no"] == (
                    total + future + (game.office_value if retain else 0))


def test_stale_metadata_and_cumulative_authority_block_before_admission(prepared):
    root, ledger, _ = prepared
    with pytest.raises(ValueError, match="stale"):
        runner.execute(root, ledger, secret="fixture-secret", clock=lambda: time.time() + 3601)
    assert not (root / "sessions/start.json").exists()
    assert len(list((ledger / "entries").glob("*.json"))) == 2


def test_shared_eight_dollar_limit_blocks_a_fresh_allocation(prepared, tmp_path):
    _, ledger, _ = prepared
    atomic(ledger / "entries/another-old-pending.json", dict(stage="old", status="reserved", reserved_usd="7.9"))
    root = tmp_path / "second-run"
    with pytest.raises(ValueError, match="eight-dollar authority"):
        runner.prepare(root, metadata=endpoint(), ledger_root=ledger)
    assert not root.exists() and not (ledger / "stages").exists()


def test_known_overcharge_or_conflicting_receipt_not_recoverable():
    from tests.test_paper3_retrospective_transport_recovery import row
    value = row()
    # Convert the fixture's pinned identities to this runner's route.
    frame = json.loads(value["stream"]["lines"][0][6:])
    frame.update(model=runner.route.MODEL_ALIAS, provider=runner.route.PROVIDER)
    value["stream"]["lines"][0] = "data: " + json.dumps(frame)
    value.update(reserved_usd=".01", input_token_bound=1000,
                 assessment=dict(accounted_usd=".02", receipt_certified=False), receipts=[])
    assert not runner.recoverable(value, 0)["eligible"]
    value["assessment"]["accounted_usd"] = ".01"
    assert runner.recoverable(value, 0)["eligible"]
    value["receipts"] = [dict(http_status=200)]
    assert not runner.recoverable(value, 0)["eligible"]
