"""Offline integration only: no API, actual ledger allocation or real run."""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from fractions import Fraction
import json

import pytest

from paper3 import retrospective_recovery_science_v2 as audit
from paper3 import retrospective_recovery_design_v2 as design
from paper3 import retrospective_anticipation_baselines as baselines
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_recovery_journal_v2 as replay
from paper3 import retrospective_recovery_calls_v2 as physical
from paper3 import retrospective_independent_execution as execution
from tests import test_paper3_retrospective_recovery_budget_v2 as copied
from tests import test_paper3_retrospective_independent_calls as fabricated

PROTOCOL = "f" * 64


def blocks(tmp_path, present=True):
    return tuple(dict(seed=seed, root=tmp_path / str(i) if present else None,
        ledger=tmp_path / "ledger", stage=f"block-{i}")
        for i, seed in enumerate(design.FRAME_SEEDS))


def options():
    return dict(verify=lambda: ({}, PROTOCOL), minimum_effect=Fraction(1, 25),
                aligned_fraction=Fraction(1, 2))


def simulated_report(items):
    rows = []
    for item in items:
        result = baselines.mandate_only(item["game"], item["arm"])["episode"]
        rows.append(dict(id=item["id"], arm=item["arm"], seed_base=item["seed_base"],
            game=asdict(item["game"]), terms=list(result.terms)))
    return dict(protocol=PROTOCOL, report=dict(assignments=tuple(rows), assigned=8),
                physical_accounted_usd="0.024", publication_evidence=False)


def test_both_unrun_blocks_remain_sixteen_missing_assignments_without_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "audit", lambda *a, **k: pytest.fail("unrun block has no evidence"))
    result = audit.audit(design.assignments(), blocks(tmp_path, False), PROTOCOL, **options())
    assert result["assigned"] == len(result["analysis"]["assignments"]) == 16
    assert result["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"
    assert result["full_physical_accounted_usd"] == "0"
    assert not result["allocation_authorized"] and not result["publication_evidence"]


def test_join_uses_public_physical_first_audit_for_each_entire_block(tmp_path, monkeypatch):
    seen = []
    def reconstruct(root, ledger, stage, items, protocol, **kwargs):
        seen.append((root, ledger, stage, items, protocol, kwargs["verify"]))
        return simulated_report(items)
    monkeypatch.setattr(replay, "audit", reconstruct)
    result = audit.audit(design.assignments(), blocks(tmp_path), PROTOCOL, **options())
    assert len(seen) == 2 and all(len(r[3]) == 8 for r in seen)
    assert result["analysis"]["episodes_complete"] == result["analysis"]["first_terms_complete"] == 16
    assert result["analysis"]["candidate_screen"]["status"] == "no_selected_case_lead"
    assert result["full_physical_accounted_usd"] == "0.048"


def test_one_unrun_block_cannot_be_filtered_into_a_complete_scientific_screen(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "audit", lambda root, ledger, stage, items, protocol, **k: simulated_report(items))
    inventory = list(blocks(tmp_path))
    inventory[1]["root"] = None
    result = audit.audit(design.assignments(), tuple(inventory), PROTOCOL, **options())
    assert result["analysis"]["episodes_complete"] == 8
    assert result["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"
    assert len(result["analysis"]["assignments"]) == 16


@pytest.mark.parametrize("mutation", ("missing", "repeat_frame", "same_root", "same_stage"))
def test_missing_duplicate_or_reused_blocks_are_rejected(tmp_path, mutation):
    inventory = list(blocks(tmp_path))
    if mutation == "missing":
        inventory.pop()
    elif mutation == "repeat_frame":
        inventory[1]["seed"] = inventory[0]["seed"]
    elif mutation == "same_root":
        inventory[1]["root"] = inventory[0]["root"]
    else:
        inventory[1]["stage"] = inventory[0]["stage"]
    with pytest.raises(ValueError):
        audit.audit(design.assignments(), tuple(inventory), PROTOCOL, **options())


@pytest.mark.parametrize("mutation", ("filtered", "order", "game", "arm", "seed_bool"))
def test_a_cached_selected_or_changed_report_cannot_supply_observations(tmp_path, monkeypatch, mutation):
    def altered(root, ledger, stage, items, protocol, **k):
        value = deepcopy(simulated_report(items))
        rows = list(value["report"]["assignments"])
        if mutation == "filtered":
            rows.pop()
        elif mutation == "order":
            rows.reverse()
        elif mutation == "game":
            rows[0]["game"]["office_value"] += 1
        elif mutation == "arm":
            rows[0]["arm"] = "forged"
        else:
            rows[0]["seed_base"] = True
        value["report"]["assignments"] = tuple(rows)
        return value
    monkeypatch.setattr(replay, "audit", altered)
    with pytest.raises(ValueError):
        audit.audit(design.assignments(), blocks(tmp_path), PROTOCOL, **options())


def test_interrupted_present_block_is_not_downgraded_to_unrun(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "audit", lambda *a, **k: (_ for _ in ()).throw(ValueError("interrupted")))
    with pytest.raises(ValueError, match="interrupted"):
        audit.audit(design.assignments(), blocks(tmp_path), PROTOCOL, **options())


def test_actual_service_journal_science_join_preserves_global_failures_and_both_costs(tmp_path):
    ledger = copied.ledger.__wrapped__(tmp_path)
    before = ledger.snapshot()
    inventory = blocks(tmp_path)
    for block in inventory:
        block["ledger"] = ledger.root
        items = tuple(a for a in design.assignments() if a["seed"] == block["seed"])
        ledger.allocate(block["stage"], "2")
        clock = fabricated.Clock()
        def send(wire, secret):
            assert secret is None
            request = json.loads(wire)
            return fabricated.row(request, "fake-invalid-native", native=False)["stream"]
        def lookup(key, secret):
            return dict(http_status=404, error_type="HTTPError", data=None, secret_redacted=False)
        by_id = {a["id"] + f"-{i:02d}": a for a in items for i in range(30)}
        def classify(row, case):
            assignment = by_id[case["context"]["logical_id"]]
            return execution.classify(row, case["request"], assignment["game"], case["context"]["stage"])
        bridge = physical.Calls(block["root"], ledger, block["stage"], options()["verify"], classify,
            send=send, lookup=lookup, maximum_logical=240,
            clock=clock, sleep=clock.sleep)
        writer = journal.Journal(block["root"], items, PROTOCOL, verify=options()["verify"])
        result = execution.execute(items, respond=lambda req, key: bridge.one(fabricated.case(key, req)),
            verify=lambda: journal._guard(options()["verify"], PROTOCOL), persist=writer.append)
        writer.close()
        bridge.close()
        assert result["global_safety_stop"] and result["completed"] == 0
    result = audit.audit(design.assignments(), inventory, PROTOCOL, **options())
    assert result["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"
    assert len(result["analysis"]["assignments"]) == 16
    assert sum(b["evidence"]["physical_attempts"] for b in result["blocks"]) == 2
    assert Decimal(result["full_physical_accounted_usd"]) == (
        Decimal(ledger.snapshot()["accounted_usd"]) - Decimal(before["accounted_usd"]))
    assert ledger.snapshot()["uncertified"] == before["uncertified"] + 2
    assert ledger.snapshot()["pending"] == before["pending"]

