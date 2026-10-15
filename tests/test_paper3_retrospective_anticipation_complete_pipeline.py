"""Complete PRIVATE institution with scripted controls and fabricated native SSE.

All480 logical actions, both terms, all4arms/2strata/2frames through production
source guards, physical service, journal/controller, stage closure and ACTUAL
isolated export replay. No API, key read, model qualification or empirical finding.
"""

from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import shutil

import pytest

from experiments import paper3_retrospective_anticipation_v1 as runner
from paper3 import retrospective_anticipation_archive as archive
from paper3 import retrospective_anticipation_baselines as baselines
from paper3 import retrospective_anticipation_coordinator as coordinator
from paper3 import retrospective_anticipation_design as design
from paper3 import retrospective_anticipation_freeze as freeze
from paper3 import retrospective_anticipation_operating as operating
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_extended_budget as budget
from paper3.pivot_b_budget import atomic
from tests import test_paper3_retrospective_anticipation_freeze as copied
from tests import test_paper3_retrospective_independent_calls as fabricated

REPO = Path(__file__).resolve().parents[1]
QUALIFIED = REPO / "paper3/data/pivot_b_retrospective_score_ledger_gate_v1"


@pytest.fixture(scope="module")
def complete(tmp_path_factory):
    base = tmp_path_factory.mktemp("anticipation-complete-pipeline")
    # PRIVATE copied checkout, fabricated readiness/consent and fake credential
    # loader. Exercise the actual runner/default bridge without writing any
    # fabricated authorization/readiness into real research results.
    code = base / "code"
    for name in operating.readiness_inventory(REPO):
        target = code / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / name, target)
    ledger = code / "results/paper3/pivot_b_budget"
    root = code / "results/paper3" / runner.STAGE
    (ledger / "entries").mkdir()
    atomic(
        ledger / "entries/older-pending.json",
        dict(stage="older", status="reserved", reserved_usd=".2"),
    )
    prior = (ledger / "entries/older-pending.json").read_bytes()
    sources = operating.readiness_inventory(code)
    readiness = dict(
        format=operating.READINESS_FORMAT,
        sources_before=sources,
        sources_after=sources,
        specification_sha256=journal.physical.t.sha(
            journal.canonical(freeze.specification()).encode()
        ),
        checks={
            name: dict(
                argv=command, returncode=0, stdout="5 passed in 0.01s\n", stderr=""
            )
            for name, command in operating.REQUIRED_CHECKS.items()
        },
        actual_model_calls=0,
    )
    atomic(code / freeze.READINESS_FILE, readiness)
    approval = dict(
        format="paper3-anticipation-authorization-v1",
        human_statement="FABRICATED TEST ONLY",
        source_thread_id="private",
        approved_at="private",
        scope=copied.approved(),
        both_blocks_approved=True,
        credit_purchases_authorized=False,
    )
    atomic(code / freeze.AUTHORIZATION_FILE, approval)
    patch = pytest.MonkeyPatch()
    patch.setattr(runner, "ROOT", code)
    patch.setattr(runner, "__file__", str(code / freeze.RUNNER_FILE))
    patch.setattr(
        operating,
        "__file__",
        str(code / "paper3/retrospective_anticipation_operating.py"),
    )
    default_locations = runner.locations
    patch.setattr(
        runner,
        "locations",
        lambda: dict(
            default_locations(),
            qualified=QUALIFIED,
            qualified_zip=QUALIFIED.with_suffix(".zip"),
        ),
    )
    items = design.assignments()
    scripts = {
        (a["game"].game_id, a["arm"]): baselines.mandate_only(a["game"], a["arm"])
        for a in items
    }
    bases = {(a["game"].game_id, a["arm"]): a["seed_base"] for a in items}
    clock, sent = fabricated.Clock(), []
    delivered = []

    def send(wire, secret):
        assert secret is None
        request = json.loads(wire)
        sent.append(wire)
        if len(sent) == 1:
            return fabricated.answerless(clock)
        payload = json.loads(request["messages"][1]["content"])
        key = payload["game_id"], payload["arm"]
        script = scripts[key]
        index = request["seed"] - bases[key]
        choice = script["requested_choices"][index]
        assert payload["stage"] == choice["stage"] and payload["term"] == choice["term"]
        assert payload["acting_district"] == choice["actor"]
        assert (
            payload["acting_identity"]
            == script["episode"].terms[choice["term"]].occupants[choice["actor"]]
        )
        delivered.append((key, index, deepcopy(payload)))
        identifier = (
            "fake-absent-first" if len(sent) == 2 else f"fake-complete-{len(sent)}"
        )
        trace = fabricated.row(request, identifier, value=choice["action"])["stream"]
        trace["started_unix"] = clock()
        clock.sleep(1)
        trace["ended_unix"] = clock()
        return trace

    def lookup(identifier, secret):
        assert secret is None
        if identifier == "fake-absent-first":
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
                model=coordinator.route.MODEL_ALIAS,
                provider_name=coordinator.route.PROVIDER,
                total_cost=0.0001,
            ),
        )

    patch.setattr(operating.hosted, "transmit", send)
    patch.setattr(operating.diagnostic, "receipt_lookup", lookup)
    patch.setattr(runner, "observe_metadata", lambda: (copied.metadata(), clock()))
    patch.setattr(runner, "read_secret", lambda repo: None)
    default_operating = operating.run_block
    patch.setattr(
        operating,
        "run_block",
        lambda *args, **kwargs: default_operating(
            *args, **kwargs, clock=clock, sleep=clock.sleep
        ),
    )
    try:
        prepared = runner.prepare(
            root,
            readiness_sha256=journal._digest(code / freeze.READINESS_FILE),
            authorization_sha256=journal._digest(code / freeze.AUTHORIZATION_FILE),
        )
        protocol = prepared["protocol"]
        manifest, _ = freeze.verify(root, code, protocol)
        assert manifest["sources"][freeze.RUNNER_FILE] == journal._digest(
            code / freeze.RUNNER_FILE
        )
        assert manifest["operating_readiness"] and manifest["operating_authorization"]
        assert not prepared["actual_model_calls"] and not prepared["launch_authorized"]
    except BaseException:
        patch.undo()
        raise
    reports, certificates = [], []
    try:
        for batch in (0, 1):
            report = runner.run(root, protocol, batch)
            assert report["blocks"][batch]["evidence"]["report"]["completed"] == 8
            assert not report["blocks"][batch]["evidence"]["report"][
                "global_safety_stop"
            ]
            # Closing an unrun block is NOT licensed by a completed other block.
            if not batch:
                with pytest.raises(ValueError, match="unstarted/interrupted"):
                    runner.offline(root, protocol, "close", 1)
            before = budget.ExtendedLedger(ledger).snapshot()
            report = runner.offline(root, protocol, "close", batch)
            after = report["budget"]
            assert before["accounted_usd"] == after["accounted_usd"]
            assert before["uncertified"] == after["uncertified"] == 2
            assert before["pending"] == after["pending"] == 1
            assert (
                after["unspent_active_stage_caps_usd"]
                < before["unspent_active_stage_caps_usd"]
            )
            certificate = runner.offline(root, protocol, "export", batch)
            assert certificate["report_sha256"] == archive.report_sha(report)
            reports.append(report)
            certificates.append(certificate)
        assert (ledger / "entries/older-pending.json").read_bytes() == prior
        # Remaining assertions run after monkeypatch cleanup against untouched real
        # modules, using the fixture's copied checkout explicitly where needed.
        return dict(
            base=base,
            root=root,
            code=code,
            ledger=ledger,
            protocol=protocol,
            scripts=scripts,
            reports=reports,
            certificates=certificates,
            sent=sent,
            delivered=delivered,
        )
    finally:
        patch.undo()


def test_all480_actions_and_both_actual_isolated_archives_match(complete):
    report = complete["reports"][1]
    assert len(complete["sent"]) == 481 and len(complete["delivered"]) == 480
    assert (
        complete["sent"][0] == complete["sent"][1]
    )  # Exact one reissue, not new content.
    assert sum(b["evidence"]["physical_reissues"] for b in report["blocks"]) == 1
    assert (
        report["analysis"]["first_terms_complete"]
        == report["analysis"]["episodes_complete"]
        == 16
    )
    assert all(
        c["isolated_report_matched"]
        and c["genuine_qualification_reproduced"]
        and c["network_guard_self_test"]
        for c in complete["certificates"]
    )
    assert not report["publication_evidence"]


def test_complete_neutral_control_cannot_manufacture_an_institutional_lead(complete):
    analysis = complete["reports"][1]["analysis"]
    assert analysis["candidate_screen"]["status"] == "no_selected_case_lead"
    assert not analysis["candidate_screen"]["selected_case_lead"]
    for horizon in ("first_term", "two_term"):
        assert analysis["readouts"][horizon]["mean_normalized_district_regret"][
            "interaction"
        ]["support_bounds"] == (Fraction(0), Fraction(0))
    for row in analysis["assignments"]:
        for horizon in ("first_term", "two_term"):
            assert len(row[horizon]["district_regret_bounds"]) == 7
            assert all(
                len(district) == 9 for district in row[horizon]["citizen_regret_bounds"]
            )


def test_successor_handover_and_rejected_second_term_use_correct_public_history(
    complete,
):
    second = [p for _, _, p in complete["delivered"] if p["term"] == 1]
    assert len(second) == 240
    assert any(p["acting_identity"].startswith("successor") for p in second)
    assert any(
        script["episode"].terms[1].enacted == 0
        for script in complete["scripts"].values()
    )
    for key, index, payload in complete["delivered"]:
        expected = complete["scripts"][key]["episode"].terms[payload["term"]]
        assert (
            payload["acting_identity"] == expected.occupants[payload["acting_district"]]
        )
        assert len(payload["history"]) == payload["term"]
        assert index // 15 == payload["term"]


def test_terminal_closure_does_not_release_old_pending_or_new_uncertified_costs(
    complete,
):
    report = complete["reports"][1]
    assert report["budget"]["entries"] == 482  # 481 physical + one older pending.
    assert report["budget"]["uncertified"] == 2 and report["budget"]["pending"] == 1
    assert report["budget"]["unspent_active_stage_caps_usd"] == "0"
    costs = [journal.load(p) for p in (complete["ledger"] / "entries").glob("*.json")]
    uncertified = [r for r in costs if r.get("certified") is False]
    assert len(uncertified) == 2 and all(
        r["accounted_usd"] == r["reserved_usd"] for r in uncertified
    )
    with pytest.raises(ValueError, match="already closed"):
        coordinator.close_terminal_block(
            complete["root"],
            complete["code"],
            complete["ledger"],
            complete["protocol"],
            0,
        )


def test_forged_terminal_binding_in_financial_closure_cannot_pass_audit(complete):
    _, blocks = coordinator.layout(
        complete["root"], complete["ledger"], complete["protocol"]
    )
    path = complete["ledger"] / "stage_closures" / (blocks[0]["stage"] + ".json")
    original = journal.load(path)
    changed = dict(original, terminal_evidence_sha256="0" * 64)
    atomic(path, changed)
    try:
        with pytest.raises(ValueError, match="financial closure differs"):
            coordinator.audit(
                complete["root"],
                complete["code"],
                complete["ledger"],
                complete["protocol"],
            )
    finally:
        atomic(path, original)  # PRIVATE fixture only, never actual evidence.
