"""Private analytical fixtures, no experimental observations or network."""

from fractions import Fraction
from itertools import product

from analysis import paper3_behavioral_identification_v1 as b
from paper3 import retrospective_accountability as core


def fixture():
    first = tuple(
        zip(
            (0,) * 9,
            (4, 4, 4, 4, -1, -1, -1, -1, -2),
            (2, 2, 2, 2, 4, -1, -1, -1, -1),
            strict=True,
        )
    )
    second = tuple((0, 1, 2) for _ in range(9))
    return core.Game(
        "private-identification", ((first,) * 7, (second,) * 7), (0, 1), 24
    )


def test_possible_sets_match_exhaustive_continuations():
    vectors = [(0, 10, 8), (0, 0, 0), (-2, 1, 3), (4, -1, 2)]
    for u, s in product(vectors, repeat=2):
        for eps in range(4):
            result = b.prediction_sets(u, s, [0, 1, 2], eps)
            observed_u, observed_s = set(), set()
            for future in product(range(eps + 1), repeat=3):
                observed_u.update(
                    b.optimal([x + y for x, y in zip(u, future)], range(3))
                )
                observed_s.update(
                    b.optimal([x + y for x, y in zip(s, future)], range(3))
                )
            assert result["mandate_possible"] == sorted(observed_u)
            assert result["office_possible"] == sorted(observed_s)


def test_exact_overlap_radius_and_tie():
    u, s = [0, 10, 8], [24, 10, 32]
    assert b.prediction_sets(u, s, range(3), 0)["first_overlap_epsilon"] == 2
    assert b.prediction_sets(u, s, range(3), Fraction(3, 2))["disjoint"]
    assert b.prediction_sets(u, s, range(3), 2)["overlap"] == [2]
    assert (
        b.membership(b.prediction_sets(u, s, [0, 1], 30), 2) == "outside_assumed_menu"
    )


def test_shared_witness_supports_both_and_preserves_future_after_removal():
    w = b.continuation_witness([0, 10, 8], [24, 10, 32], [0, 9, 18], [0, 1, 2], 2)
    assert w["selected_mandate_optimal"] and w["selected_office_optimal"]
    assert w["mandate_scores"][2] == 26 and w["office_scores"][2] == 50
    assert (
        b.continuation_witness([0, 10, 8], [24, 10, 32], [0, 9, 18], [0, 1], 2) is None
    )


def test_controlled_pivotal_choice_has_exact_two_term_divergence():
    r = b.controlled_scores(fixture(), "binding_majority", 0, 1)
    assert r["mandate_predictions"] == [True] and r["office_predictions"] == [False]
    assert r["outcomes"][True]["enacted"] == [1, 0]
    assert r["outcomes"][True]["mandate"] == 10 and r["outcomes"][True]["office"] == 10
    assert r["outcomes"][False]["mandate"] == 0 and r["outcomes"][False]["office"] == 24
    assert sum(r["fixed_peer_votes"].values()) == 3


def test_negative_controls_and_bonus_threshold():
    from dataclasses import replace

    for game, arm in [
        (replace(fixture(), office_value=0), "binding_majority"),
        (fixture(), "binding_sum"),
    ]:
        r = b.controlled_scores(game, arm, 3, 1)
        assert r["mandate_predictions"] == r["office_predictions"] == [True]
    r = b.controlled_scores(
        replace(fixture(), office_value=10), "binding_majority", 0, 1
    )
    assert r["office_predictions"] == [False, True]


def test_coalition_stress_uses_common_future_for_all_districts():
    rows = b.coalition_stress(fixture(), "binding_majority")
    assert len(rows) == 2 and len(rows[0]["scenarios"]) == 9
    r = next(
        s
        for s in rows[0]["scenarios"]
        if s["terminal_if_passed"] == 2 and s["terminal_if_rejected"] == 0
    )
    assert r["mandate_deltas"] == [28] * 7
    assert r["office_deltas"] == [4] * 7
    assert rows[0]["summary"]["mandate"]["minimum_supporters"] == 0
    assert rows[0]["summary"]["mandate"]["maximum_supporters"] == 7


def test_constant_continuation_has_identical_fixed_rankings():
    u, s = [0, 10, 8], [24, 10, 32]
    r = b.prediction_sets(u, s, [0, 1, 2], 0)
    for constant in (-30, 0, 30):
        assert b.optimal([v + constant for v in u], range(3)) == r["mandate_possible"]
        assert b.optimal([v + constant for v in s], range(3)) == r["office_possible"]
