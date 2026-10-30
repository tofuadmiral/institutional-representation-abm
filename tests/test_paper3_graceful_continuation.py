"""End-to-end fabricated continuation; never paid or real research results."""

from contextlib import contextmanager
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments import paper3_graceful_continuation as runner
from paper3 import retrospective_graceful_recovery as recover
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_episode_journal as journal
from paper3.pivot_b_budget import atomic
from tests.test_paper3_retrospective_deepinfra_core_v1 import evidence
from tests.test_paper3_retrospective_independent_calls import Clock
from tests.test_paper3_graceful_recovery import overload_with_id


class FakeLedger:
    """Private transactional charge fixture, not a readiness/authority record."""

    def __init__(self, root):
        self.root = Path(root)

    @contextmanager
    def locked(self):
        yield

    def _stage(self, stage):
        assert stage in ("private-stage-0", "private-stage-1")

    def reserve(self, stage, key, amount, sha):
        path = self.root / "entries" / (key + ".json")
        assert not path.exists()
        atomic(
            path,
            dict(
                stage=stage,
                request_id=key,
                request_sha256=sha,
                reserved_usd=str(amount),
                status="reserved",
            ),
        )

    def settle(self, key, cost, certified, sha):
        path = self.root / "entries" / (key + ".json")
        row = recover.load(path)
        assert row["status"] == "reserved"
        assert certified or Decimal(cost) >= Decimal(row["reserved_usd"])
        row.update(
            status="settled",
            accounted_usd=cost,
            certified=certified,
            evidence_sha256=sha,
        )
        atomic(path, row)

    def snapshot(self):
        rows = [recover.load(p) for p in (self.root / "entries").glob("*.json")]
        return dict(
            accounted_usd=str(
                sum(
                    (Decimal(r.get("accounted_usd", r["reserved_usd"])) for r in rows),
                    Decimal(0),
                )
            ),
            entries=len(rows),
            uncertified=sum(r.get("certified") is False for r in rows),
        )


def private_runner(tmp_path, monkeypatch, *, pause_at=None):
    root = tmp_path / "run"
    root.mkdir()
    ledgerroot = tmp_path / "ledger"
    ledgerroot.mkdir()
    (ledgerroot / "entries").mkdir()
    atomic(
        ledgerroot / "authority.json",
        dict(
            budget_id="paper3-pivot-b-2026-09-24",
            cap_usd="10.00",
            credit_purchases_authorized=False,
        ),
    )
    book = FakeLedger(ledgerroot)
    clock = Clock()
    monkeypatch.setattr(runner, "REPO", tmp_path)
    monkeypatch.setattr(runner, "LEDGER", "ledger")
    monkeypatch.setattr(
        runner,
        "time",
        SimpleNamespace(
            time=clock, sleep=clock.sleep, time_ns=lambda: int(clock() * 1e9)
        ),
    )
    m = dict(
        prior_entries={},
        baseline=dict(
            prefix={},
            failures={},
            references={},
            bounds=[
                dict(frame=f, maximum_new_physical=280, cap_usd="5")
                for f in runner.design.FRAME_SEEDS
            ],
        ),
    )
    protocol = "e" * 64
    pins = dict(
        protocol=protocol, stages=["private-stage-0", "private-stage-1"], stage_pins={}
    )
    monkeypatch.setattr(runner, "verify", lambda root, p: (m, protocol))
    monkeypatch.setattr(runner, "allocate", lambda *a: pins)
    monkeypatch.setattr(runner, "ledger", lambda *a, **k: book)
    atomic(root / "allocation.json", pins)
    sent = []

    def send(wire, secret):
        assert secret is None
        sent.append((wire, clock()))
        request = json.loads(wire)
        if len(sent) == 1:
            s = overload_with_id(request)["stream"]
        else:
            if pause_at is not None and len(sent) == pause_at:
                raise KeyboardInterrupt()
            s = evidence(request, "gen-private-" + str(len(sent)))["stream"]
        s.update(started_unix=clock(), ended_unix=clock())
        return s

    def lookup(identifier, secret):
        if identifier == "gen-fabricated-overload":
            return dict(
                http_status=404,
                error_type="HTTPError",
                data=None,
                secret_redacted=False,
            )
        return dict(
            http_status=200,
            error_type=None,
            secret_redacted=False,
            data=dict(
                id=identifier,
                model=route.MODEL_ALIAS,
                provider_name=route.PROVIDER,
                total_cost=0.0001,
            ),
        )

    return root, protocol, sent, send, lookup, book


def test_full480_action_institution_recovers_busy_header_then_replays_exact_report(
    tmp_path, monkeypatch
):
    root, p, sent, send, lookup, book = private_runner(tmp_path, monkeypatch)
    result = runner.run(root, p, send=send, lookup=lookup)
    assert result["status"] == "complete"
    assert len(sent) == 481 and sent[0][0] == sent[1][0]
    assert sent[1][1] - sent[0][1] >= 300
    report = journal.decode(recover.load(root / "report.json"))
    assert (
        len(report["assignments"]) == 16
        and report["analysis"]["episodes_complete"] == 16
    )
    assert all(len(a["terms"]) == 2 for a in report["assignments"])
    assert all(
        len(a["outcome"].cumulative_citizen_utilities) == 7
        for a in report["assignments"]
    )
    assert book.snapshot()["entries"] == 481 and book.snapshot()["uncertified"] == 1
    audit = runner.audit(root, p)
    assert audit["entire_report_matched"] and len(sent) == 481
    with pytest.raises(ValueError, match="already terminal"):
        runner.run(root, p, send=send, lookup=lookup)
    assert len(sent) == 481


def test_uncertain_inflight_post_pauses_on_restart_without_duplicate_send(
    tmp_path, monkeypatch
):
    root, p, sent, send, lookup, book = private_runner(
        tmp_path, monkeypatch, pause_at=10
    )
    with pytest.raises(KeyboardInterrupt):
        runner.run(root, p, send=send, lookup=lookup)
    before = len(sent)
    result = runner.run(root, p, send=send, lookup=lookup)
    assert result["status"] == "paused" and len(sent) == before
    assert not (root / "report.json").exists()
    assert len(list((root / "block-0/accepted").glob("*.json"))) == 8
    assert any(
        recover.load(f)["status"] == "reserved"
        for f in (book.root / "entries").glob("*.json")
    )


def test_real111_prefix_replays_byte_exactly_without_hosted_calls():
    # Read-only regression against the actual stopped run, not a new model gate.
    repo = Path(__file__).resolve().parents[1]
    old = repo / runner.OLD_ROOT / "block-0"
    saved = {}
    for p in (old / "logicals").glob("*.json"):
        d = recover.load(p)
        if d["status"] == "recorded_valid":
            saved[d["case"]["id"]] = recover.load(
                old / "calls" / (d["selected_id"] + ".json")
            )
    failed = "overload-r2-0-conflict-binding_majority-21"
    count = []

    class Pending(BaseException):
        pass

    def respond(request, key):
        if key == failed:
            row = recover.load(old / "calls" / (key + "-a1.json"))
            assert route.reservation(request)["request_text"] == row["request_text"]
            raise Pending()
        row = saved[key]
        assert route.reservation(request)["request_text"] == row["request_text"]
        count.append(key)
        return dict(row, id=key)

    with pytest.raises(Pending):
        runner.execution.execute(
            runner.items(), respond=respond, verify=lambda: None, persist=lambda e: None
        )
    assert len(count) == len(saved) == 111


def test_crash_after_response_before_settlement_finishes_old_transaction_without_resend(
    tmp_path, monkeypatch
):
    root, p, sent, send, lookup, book = private_runner(
        tmp_path, monkeypatch, pause_at=3
    )
    settle = book.settle
    interrupted = []

    def crash_once(*args):
        if not interrupted:
            interrupted.append(True)
            raise KeyboardInterrupt()
        return settle(*args)

    monkeypatch.setattr(book, "settle", crash_once)
    with pytest.raises(KeyboardInterrupt):
        runner.run(root, p, send=send, lookup=lookup)
    assert len(sent) == 1
    with pytest.raises(KeyboardInterrupt):
        runner.run(root, p, send=send, lookup=lookup)
    assert len(sent) == 3  # Original failed physical request was not sent twice.
    first = next((book.root / "entries").glob("*-a1.json"))
    assert recover.load(first)["status"] == "settled"
    assert len(list((root / "block-0/accepted").glob("*.json"))) == 1


def test_real_budget_adapter_private_copy_preserves_old_costs_and_reuses_same_block_allocation(
    tmp_path, monkeypatch
):
    import shutil
    from paper3 import retrospective_deepinfra_budget_v2 as actual_budget
    from paper3 import retrospective_deepinfra_freeze_v2 as old_freeze

    repo = Path(__file__).resolve().parents[1]
    target = tmp_path / runner.LEDGER
    shutil.copytree(repo / runner.LEDGER, target)
    before = {p.name: recover.digest(p) for p in (target / "entries").glob("*.json")}
    old_alloc = recover.load(repo / runner.OLD_ROOT / "sessions/allocation.json")
    old_stage = old_alloc["group"] + "-1"
    monkeypatch.setattr(runner, "REPO", tmp_path)
    root = tmp_path / "run"
    root.mkdir()
    m = dict(
        prior_entries=before,
        baseline=dict(
            bounds=[dict(cap_usd=".10"), dict(cap_usd="4.39135184")],
            reused_stage=old_stage,
            reused_stage_sha=old_alloc["stage_pins"][old_stage],
        ),
    )
    pins = runner.allocate(root, "a" * 64, m)
    assert runner.allocate(root, "a" * 64, m) == pins
    book = actual_budget.RecoveryLedger(
        target,
        stage_pins=pins["stage_pins"],
        retirement_pins=old_freeze.RETIREMENT_PINS,
    )
    stage = pins["stages"][0]
    e = book.reserve(stage, stage + "-private", Decimal(".01"), "c" * 64)
    book.settle(e["request_id"], ".01", False, "b" * 64)
    assert book.snapshot()["cap_usd"] == "19.30"
    assert {
        p.name: recover.digest(p)
        for p in (target / "entries").glob("*.json")
        if p.name in before
    } == before
    assert (
        recover.digest(target / actual_budget.STAGES / (old_stage + ".json"))
        == old_alloc["stage_pins"][old_stage]
    )
    with pytest.raises(ValueError, match="total/stage admission"):
        book.reserve(stage, stage + "-too-large", Decimal(".11"), "d" * 64)
