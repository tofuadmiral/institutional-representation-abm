"""Offline checks of untouched two-topology candidate cases."""

from fractions import Fraction

from paper3 import mandate_release_fresh_design as design
from paper3 import mandate_release_rival_opportunity as opportunity


def test_cases_are_two_distinct_qualified_topologies():
    cases = design.cases()
    assert len(cases) == len(design.SPECS) == 10
    assert len({case.seed for case in cases}) == 10
    assert len({case.game for case in cases}) == 10
    assert {case.family for case in cases} == {"overlap2", "overlap3"}
    assert sum(case.stratum == "pivotal" for case in cases) == 8
    assert sum(case.stratum == "nonpivotal" for case in cases) == 2
    for case in cases:
        opportunity.validate(case.game)
        assert design._certificate(case.game, case.family, case.stratum)
        y2 = set(opportunity.acceptable_coalitions(case.game, "Y2"))
        assert ((0, 1, 2, 4) in y2) == (case.family == "overlap3")
        assert (0, 1, 4, 5) in y2
        assert opportunity.bundle_total(case.game.before, 3, "Y2") <= 0


def test_cases_are_not_the_archived_v1_numeric_profiles():
    from paper3 import mandate_release_design as earlier

    old_games = {case.game for case in earlier.cases()}
    assert all(case.game not in old_games for case in design.cases())


def test_macro_risk_parameters_vary_before_any_scientific_run():
    cases = design.cases()
    assert {case.game.shock_probability for case in cases} == {
        Fraction(11, 50), Fraction(1, 4), Fraction(3, 10)}
    assert len({opportunity.bundle_total(case.game.after, 3, "Y1")
                for case in cases}) >= 4
    assert len({opportunity.district_total(case.game.after, 3, "X")
                for case in cases}) >= 4
