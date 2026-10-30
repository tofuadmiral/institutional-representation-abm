from decimal import Decimal
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_labeled_discovery_requests as requests
from paper3 import retrospective_labeled_qualification as qualification
from paper3 import retrospective_readout as readout
from paper3 import retrospective_requests as original


def test_fresh_frames_matching_units_and_no_case_selection_on_outcomes():
    pairs = requests.pairs()
    assert tuple(pair.seed for pair in pairs) == requests.FRAME_SEEDS
    assert not set(requests.FRAME_SEEDS) & {*original.FRAME_SEEDS, qualification.FRAME_SEED}
    for pair in pairs:
        assert design.district_sums(pair.aligned.utilities[0]) == design.district_sums(pair.conflict.utilities[0])
        assert pair.aligned.utilities[1] == pair.conflict.utilities[1]
        assert pair.aligned.chairs == pair.conflict.chairs
        assert pair.aligned.office_value == pair.conflict.office_value == 24
        design.opportunity(pair)
        assert pair.aligned.game_id.startswith("electorate-")
        assert pair.conflict.game_id.startswith("electorate-")


def test_fixed_sixteen_assignments_paired_seeds_and_unchanged_screen():
    assignments = requests.assignments()
    assert len(assignments) == 16 and len({row["id"] for row in assignments}) == 16
    actual_seeds = {row["seed_base"] + i for row in assignments for i in range(30)}
    earlier = {row["seed_base"] + i for row in original.assignments() for i in range(30)}
    gate = set(range(qualification.SEED_BASE, qualification.SEED_BASE + 18))
    assert len(actual_seeds) == 60 and not actual_seeds & (earlier | gate)
    for pair in requests.pairs():
        assert len({row["seed_base"] for row in assignments if row["seed"] == pair.seed}) == 1
    observations = {(pair.seed, stratum, arm): None for pair in requests.pairs()
                    for stratum in readout.STRATA for arm in institution.ARMS}
    screen = readout.screen(requests.pairs(), observations, completed_episodes=set(), qualified=False)
    assert screen["verdict"] == "qualification_failed" and not screen["publication_evidence"]
    assert float(screen["min_effect"]) == .04


def test_all_480_legal_history_bounds_cover_native_labelled_requests():
    bounds = requests.legal_history_bounds()
    assert bounds["maximum_calls"] == 480
    assert Decimal(bounds["reservation_usd"]) <= Decimal("2.90")
    assert not bounds["qualification_inherited"] and not bounds["allocation_authorized"]
    for assignment, bounded in zip(requests.assignments(), bounds["assignments"], strict=True):
        assert assignment["id"] == bounded["id"] and len(bounded["input_bounds"]) == 30

        def ask(actor, identity, term, stage, context, index):
            request = requests.action_request(assignment, actor, identity, term, stage, context, index)
            prompt = json.loads(request["messages"][1]["content"])
            assert prompt["data_layout"]["utilities_axes"] == ["term", "district", "citizen", "policy"]
            assert "aligned" not in json.dumps(prompt) and "conflict" not in json.dumps(prompt)
            assert original.reservation(request)["input_token_bound"] <= bounded["input_bounds"][index]
            if stage in ("draft", "final"):
                return dict(policy=3, message="😀" * 128)
            if stage == "response":
                return dict(support=True, counter_policy=2, message="fixture")
            return dict(vote=actor >= 3)
        assert institution.episode(assignment["game"], assignment["arm"], ask).calls == 30
