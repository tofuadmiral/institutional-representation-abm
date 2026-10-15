from decimal import Decimal
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_keyed_discovery_requests as closed
from paper3 import retrospective_keyed_interface as interface
from paper3 import retrospective_serial_requests as requests
from paper3 import retrospective_readout as readout


def test_fresh_paired_cases_preserve_objectives_institutions_and_two_sided_screen():
    assert set(requests.FRAME_SEEDS).isdisjoint(closed.FRAME_SEEDS)
    old = {a["seed_base"] + i for a in closed.assignments() for i in range(30)}
    seeds = {a["seed_base"] + i for a in requests.assignments() for i in range(30)}
    assert len(seeds) == 60 and not seeds & old
    for pair in requests.pairs():
        assert design.district_sums(pair.aligned.utilities[0]) == design.district_sums(pair.conflict.utilities[0])
        assert pair.aligned.utilities[1] == pair.conflict.utilities[1]
        assert pair.aligned.chairs == pair.conflict.chairs and pair.aligned.office_value == 24
        assert {a["arm"] for a in requests.assignments() if a["seed"] == pair.seed} == set(institution.ARMS)
    observations = {(p.seed, s, a): None for p in requests.pairs()
                    for s in readout.STRATA for a in institution.ARMS}
    screen = readout.screen(requests.pairs(), observations, completed_episodes=set(), qualified=False)
    assert screen["verdict"] == "qualification_failed" and float(screen["min_effect"]) == .04


def test_complete_base_path_and_all_reissue_reservations_are_bounded_without_paid_authority():
    report = requests.legal_history_bounds()
    assert report["base_calls"] == 480 and report["maximum_calls"] == 530
    assert report["declared_attempt_slots"] == 960 and report["output_bound"] == 14000
    assert not any(report[k] for k in ("allocation_authorized", "qualification_inherited", "old_run_reopen_authorized"))
    assert len(report["batches"]) == 2
    for batch in report["batches"]:
        assert Decimal(batch["full_path_usd"]) == Decimal(batch["base_usd"]) + 25 * Decimal(batch["largest_attempt_usd"])
        assert Decimal(batch["full_path_usd"]) <= Decimal("3.20")


def test_lossless_no_hidden_stratum_full_episode_history_and_identical_reissue_wire():
    bounds = {r["id"]: r for r in requests.legal_history_bounds()["assignments"]}
    for assignment in requests.assignments():
        def ask(actor, identity, term, stage, context, index):
            wire = requests.action_request(assignment, actor, identity, term, stage, context, index)
            assert wire == requests.action_request(assignment, actor, identity, term, stage, context, index)
            prompt = json.loads(wire["messages"][1]["content"])
            assert interface.restore_utilities(prompt["payoff_cards"], 6) == assignment["game"].utilities
            assert "aligned" not in json.dumps(prompt) and "conflict" not in json.dumps(prompt)
            assert requests.route.reservation(wire)["input_token_bound"] <= bounds[assignment["id"]]["input_bounds"][index]
            if stage in ("draft", "final"):
                return dict(policy=4, message="😀" * 128)
            if stage == "response":
                return dict(support=True, counter_policy=3, message="fixture")
            return dict(vote=actor >= 3)
        assert institution.episode(assignment["game"], assignment["arm"], ask).calls == 30


def test_historical_collision_scan_is_read_only_and_rejects_collisions(tmp_path):
    parent = tmp_path / "results/paper3/old/calls"
    parent.mkdir(parents=True)
    path = parent / "saved.json"
    path.write_text(json.dumps(dict(request=dict(seed=1))))
    before = path.read_bytes()
    report = requests.seed_audit(tmp_path)
    assert report["overlap"] == [] and report["historical_files"] == 1
    assert path.read_bytes() == before
    path.write_text(json.dumps(dict(request=dict(seed=requests.DECISION_SEED_BASE))))
    with pytest.raises(ValueError, match="collision"):
        requests.seed_audit(tmp_path)
