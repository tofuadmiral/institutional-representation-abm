"""Pure legal-history and byte-bound tests; never provider-performance evidence."""
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_late_context_bounded_gate_v1 as gate
from paper3 import retrospective_score_ledger_budget as wire


def test_inventory_covers_all_arms_and_phases_in_full_late_term_context():
    rows = gate.cases()
    assert len(rows) == 16
    assert {(r["arm"], r["stage"]) for r in rows} == {
        (a, s) for a in institution.ARMS for s in ("draft", "response", "final", "vote")}
    for row in rows:
        payload = json.loads(row["request"]["messages"][1]["content"])
        assert row["term"] == payload["term"] == 1 and len(payload["history"]) == 1
        assert len(row["game"].utilities) == 2
        assert all(len(term) == 7 and all(len(d) == 9 for d in term)
                   for term in row["game"].utilities)
        assert row["game"].office_value == 24
        assert row["request"]["reasoning"] == dict(enabled=True, exclude=False)
        assert row["request"]["max_tokens"] == 14000
        assert row["request"]["tool_choice"] == "auto"
        assert row["request"]["seed"] in range(gate.SEED_BASE, gate.SEED_BASE + 16)
        assert wire.structured(row["request"]["messages"], row["game"], row["stage"])
        if row["stage"] == "response":
            assert "responses" not in payload


def test_full_reservation_includes_nine_identical_reissues_without_new_launch_authority():
    bound = gate.bound()
    assert bound["maximum_physical_calls"] == 25 and bound["maximum_reissues"] == 9
    assert bound["largest_wire_bytes"] <= 49152
    assert not bound["model_calls_authorized_by_module"]
    assert not bound["publication_evidence"] and bound["all_sixteen_must_pass"]


def test_fresh_seeds_and_bounded_attempt_slots():
    from paper3 import retrospective_late_context_bounded_retry_v1 as retry
    assert gate.FRAME_SEED == 2026101801 and gate.SEED_BASE == 2026101900
    assert retry.MAX_REISSUES_PER_ACTION == 3 and retry.MAX_REISSUES == 9
    case = gate.requests()[0]
    assert [retry.physical(case, n)["id"] for n in range(1, 5)] == [
        case["id"] + "-a1", case["id"] + "-a2", case["id"] + "-a3", case["id"] + "-a4"]
    for n in (0, 4, True):
        assert not retry.eligibility({}, logical_attempt=n, recoveries_used=0)["eligible"]
    for n in (-1, 9, True):
        assert not retry.eligibility({}, logical_attempt=1, recoveries_used=n)["eligible"]
