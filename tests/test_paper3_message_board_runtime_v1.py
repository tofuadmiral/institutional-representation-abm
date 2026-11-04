"""Scripted transport/accounting checks only; no provider or model calls."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import shutil

import pytest

from paper3 import message_board_runtime_v1 as w
from paper3 import message_board_budget_v1 as budget
from tests.test_paper3_graceful_continuation import FakeLedger
from tests.test_paper3_graceful_recovery import overload_with_id
from tests.test_paper3_retrospective_independent_calls import Clock
from tests.test_paper3_retrospective_deepinfra_core_v1 import evidence

REPO = Path(__file__).resolve().parents[1]


def response(request, identifier, *, value=None, raw=None, **options):
    schema = request["tools"][0]["function"]["name"]
    if value is None:
        context = json.loads(request["messages"][1]["content"])
        record = context["trusted_case"]
        if schema == "post_message":
            value = dict(message="PRIVATE scripted public post " + identifier)
        elif schema == "report_fact":
            claim = context["claim"]
            value = dict(answer=record["options"][claim["plan"]]["district_sum"] == claim["district_sum"])
        else:
            score = request["messages"][0]["content"] == w.design.SCORE_SYSTEM
            choice = max(record["options"], key=lambda k: record["options"][k]["district_sum"] +
                         (48 * record["options"][k]["incumbent_retained"] if score else 0))
            value = dict(decision=choice)
    provider = options.pop("provider", None)
    row = evidence(request, identifier, value=value, raw=raw, **options)
    row["stream"]["lines"] = [line.replace('"submit_decision"', json.dumps(schema))
                              for line in row["stream"]["lines"]]
    if provider is not None:
        for i, line in enumerate(row["stream"]["lines"]):
            if line.startswith("data: {"):
                frame = json.loads(line[5:])
                if "provider" in frame:
                    frame["provider"] = provider
                    row["stream"]["lines"][i] = "data: " + json.dumps(frame)
    row["assessment"] = w.billing.assess(row, w.native.CONFIG)
    return row


def test_native_billing_channel_payload_and_resource_boundaries():
    call = w.design.Episode(w.design.cases(4)[0], "self_board").next_call()
    assert w.classify(response(call["request"], "private-good"), call)["status"] == "recorded_valid"
    for options in (dict(raw="not JSON"), dict(value={"message": "🧪" * 301}),
                    dict(value={"message": "", "extra": True}), dict(channel="text")):
        assert w.classify(response(call["request"], "private-local", **options), call)["status"] == "content_failed"
    for options in (dict(native=False), dict(bad_count=True), dict(channel="both"),
                    dict(provider="wrong-route")):
        assert w.classify(response(call["request"], "private-unsafe", **options), call)["status"] == "unsafe_failed"
    row = response(call["request"], "private-tamper")
    row["request_sha256"] = "0" * 64
    assert w.classify(row, call)["status"] == "unsafe_failed"
    row = response(call["request"], "private-length")
    row["stream"]["lines"] = [s.replace('"finish_reason": "tool_calls"', '"finish_reason": "length"')
        .replace('"completion_tokens": 100', '"completion_tokens": 14000') for s in row["stream"]["lines"]]
    row["assessment"] = w.billing.assess(row, w.native.CONFIG)
    result = w.classify(row, call)
    assert result["status"] == "resource_failed" and result["action"] is None
    for complete in (row, response(call["request"], "private-unknown")):
        changed = deepcopy(complete)
        frame = json.loads(changed["stream"]["lines"][0][5:])
        frame["choices"][0]["delta"]["unknown_action_channel"] = "do not silently discard"
        changed["stream"]["lines"][0] = "data: " + json.dumps(frame)
        changed["assessment"] = w.billing.assess(changed, w.native.CONFIG)
        assert w.classify(changed, call)["status"] == "unsafe_failed"
    # Known receipt transients retain the whole reservation; unknown auth never passes.
    row = response(call["request"], "private-billing")
    row["receipts"] = [dict(http_status=None, error_type="TimeoutError", data=None,
        secret_redacted=False, scheduled_offset_seconds=t) for t in w.billing.OFFSETS]
    row["assessment"] = w.billing.assess(row, w.native.CONFIG)
    assert w.classify(row, call)["status"] == "recorded_valid"
    assert row["assessment"]["accounted_usd"] == row["reserved_usd"]
    row["receipts"][0].update(http_status=401, error_type="HTTPError")
    row["assessment"] = w.billing.assess(row, w.native.CONFIG)
    assert w.classify(row, call)["status"] == "unsafe_failed"


def setup(tmp_path, n=16):
    root, ledger = tmp_path / "run", tmp_path / "ledger"
    root.mkdir()
    (ledger / "entries").mkdir(parents=True)
    w.atomic(ledger / "authority.json", dict(budget_id="paper3-pivot-b-2026-09-24",
        cap_usd="10.00", credit_purchases_authorized=False))
    book, clock, sent = FakeLedger(ledger), Clock(), []
    book._entries = lambda: [w.load(p) for p in (ledger / "entries").glob("*.json")]
    cases, protocol, stage = w.design.cases(n), "e" * 64, "private-board-stage"
    unique, counts = [], {}

    def send(wire, secret):
        assert secret is None
        sent.append((wire, clock()))
        if wire not in unique:
            unique.append(wire)
        counts[wire] = counts.get(wire, 0) + 1
        request = json.loads(wire)
        if (unique.index(wire) == 0 and counts[wire] == 1) or unique.index(wire) == 1:
            s = deepcopy(overload_with_id(request)["stream"])
        else:
            s = response(request, "gen-private-" + str(len(sent)),
                         raw="not JSON" if unique.index(wire) == 2 else None)["stream"]
        s.update(started_unix=clock(), ended_unix=clock())
        return s

    def lookup(identifier, secret):
        if identifier == "gen-fabricated-overload":
            return dict(http_status=404, error_type="HTTPError", data=None, secret_redacted=False)
        return dict(http_status=200, error_type=None, secret_redacted=False,
            data=dict(id=identifier, model=w.route.MODEL_ALIAS, provider_name=w.route.PROVIDER, total_cost=.0001))

    def admit(root, protocol, book, stage, secret):
        old = w.load(REPO / "results/paper3/pivot_b_independent_validation_v1/admissions/1793205286757644000.json")
        w.atomic(root / "admissions" / (str(clock()) + ".json"), dict(protocol=protocol,
            metadata_observed_unix=clock(), metadata=old["metadata"],
            account=dict(account_funded=True, research_authority_extended=False)))
        return clock()

    args = (root, tmp_path, protocol, cases, book, stage, lambda: ({}, protocol))
    deps = dict(send=send, lookup=lookup, admit=admit, clock=clock, sleep=clock.sleep)
    return args, deps, sent


def test_entire352_call_dynamic_cohort_crash_settlement_missingness_and_replay(tmp_path, monkeypatch):
    args, deps, sent = setup(tmp_path)
    root, _, protocol, _, book, stage, _ = args
    original_check, original_settle = w.check_record, book.settle
    index_crashed = settlement_crashed = False

    def interrupt_index(*a, **kw):
        nonlocal index_crashed
        original_check(*a, **kw)
        if len(sent) == 2 and not index_crashed:
            index_crashed = True
            raise KeyboardInterrupt()

    def interrupt_settlement(*a, **kw):
        nonlocal settlement_crashed
        if len(sent) == 7 and not settlement_crashed:
            settlement_crashed = True
            raise KeyboardInterrupt()
        original_settle(*a, **kw)

    monkeypatch.setattr(w, "check_record", interrupt_index)
    monkeypatch.setattr(book, "settle", interrupt_settlement)
    for count in (2, 7):
        with pytest.raises(KeyboardInterrupt):
            w.run(*args, **deps)
        assert len(sent) == count and not list((root / "invocations").glob("*terminal*"))
    before = {p: p.read_bytes() for p in (root / "calls").glob("*.json")}
    assert any(r["status"] == "reserved" for r in book._entries())
    assert w.run(*args, **deps)["status"] == "complete"
    assert all(p.read_bytes() == value for p, value in before.items())
    assert index_crashed and settlement_crashed and len(sent) == 356
    assert sent[0][0] == sent[1][0] and sent[1][1] - sent[0][1] >= 300
    report = w.load(root / "report.json")
    assert len(report["logicals"]) == 352 and report["assigned_episodes"] == 64
    assert sum(r["result"]["status"] == "retry_exhausted" for r in report["logicals"]) == 1
    assert sum(r["result"]["status"] == "content_failed" for r in report["logicals"]) == 1
    # All fixed remaining episodes/controls execute despite exhausted/bad content.
    assert sum(v["assigned"] for v in report["control_summary"].values()) == 32
    assert not report["controls_used_for_exclusion"]
    audit = w.audit(*args)
    assert audit["entire_report_matched"] and audit["entire_ledger_matched"]
    assert len(sent) == 356 and audit["physical"] == 356
    assert all(r["status"] == "settled" for r in book._entries())
    assert sum(r["certified"] is False for r in book._entries()) == 5
    # Editing a later saved history cannot be hidden by a self-consistent report.
    event = sorted((root / "events").glob("*.json"))[-1]
    old = event.read_bytes()
    value = w.load(event)
    value["request_sha256"] = "0" * 64
    w.atomic(event, value)
    with pytest.raises(ValueError, match="saved events"):
        w.audit(*args)
    event.write_bytes(old)
    with pytest.raises(ValueError, match="complete root"):
        w.run(*args, **deps)
    assert protocol == "e" * 64 and all(r["stage"] == stage for r in book._entries())


def test_uncertain_sent_post_preserved_and_no_repeat_after_terminal(tmp_path):
    args, deps, sent = setup(tmp_path, 4)
    root, _, _, _, book, _, _ = args

    def interrupted(wire, secret):
        sent.append((wire, deps["clock"]()))
        raise KeyboardInterrupt()

    deps["send"] = interrupted
    with pytest.raises(KeyboardInterrupt):
        w.run(*args, **deps)
    assert len(sent) == 1 and book._entries()[0]["status"] == "reserved"
    raw = next((root / "calls").glob("*.json"))
    original = raw.read_bytes()
    assert w.run(*args, **deps)["status"] == "paused"
    assert len(sent) == 1 and raw.read_bytes() == original
    with pytest.raises(ValueError, match="latest terminal"):
        w.run(*args, **deps)
    assert len(sent) == 1 and not (root / "report.json").exists()


def test_board_budget_private_real_history_preserves_every_older_charge(tmp_path):
    target = tmp_path / "ledger"
    shutil.copytree(REPO / "results/paper3/pivot_b_budget", target)
    before = {p.name: p.read_bytes() for p in (target / "entries").glob("*.json")}
    book = budget.BoardLedger(target)
    baseline = book.snapshot()
    assert baseline["cap_usd"] == "21.31"
    pins = book.allocate_group("private-board-group", {"private-board-stage": ".02"})["stage_pins"]
    book = budget.BoardLedger(target, stage_pins=pins)
    assert Decimal(book.snapshot()["available_for_new_stages_usd"]) == Decimal(baseline["available_for_new_stages_usd"]) - Decimal(".02")
    book.reserve("private-board-stage", "private-board-call", ".01", "a" * 64)
    book.settle("private-board-call", ".01", False, "b" * 64)
    book.close("private-board-stage", "c" * 64)
    after = book.snapshot()
    assert Decimal(after["accounted_usd"]) == Decimal(baseline["accounted_usd"]) + Decimal(".01")
    assert after["pending"] == baseline["pending"] and after["uncertified"] == baseline["uncertified"] + 1
    assert after["unspent_active_stage_caps_usd"] == baseline["unspent_active_stage_caps_usd"]
    assert all((target / "entries" / name).read_bytes() == b for name, b in before.items())
