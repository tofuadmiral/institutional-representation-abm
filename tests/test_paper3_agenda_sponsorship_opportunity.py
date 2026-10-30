"""Only structural sponsorship certificates; no model-result assertions."""
from __future__ import annotations

from paper3 import agenda_sponsorship_opportunity as opportunity
from paper3 import direct_ratification as base


def test_factorial_opportunities_and_distinct_profiles():
    ids = set()
    for structure in opportunity.STRUCTURES:
        for welfare in opportunity.WELFARE:
            for seed in (2026092900, 2026092901):
                item = opportunity.draw(structure, welfare, seed)
                cert = opportunity.certificate(item)
                profile = item["profile"]
                assert cert["profile_id"] not in ids
                ids.add(cert["profile_id"])
                assert 1 <= item["draw_attempts"] <= 500
                assert sum(map(len, profile["districts"].values())) == 63
                assert cert["sincere_qualifies"] is (structure != "split")
                assert all(len(sponsors) == 4
                           for sponsors in cert["potential_sponsors"].values())
                y, c = item["compromises"]
                if welfare == "y_high":
                    assert cert["total_citizen_utility"][y] > cert[
                        "total_citizen_utility"][c]
                else:
                    assert cert["total_citizen_utility"][c] > cert[
                        "total_citizen_utility"][y]
                assert all(len(set(c["utility"].values())) > 1
                           for citizens in profile["districts"].values()
                           for c in citizens)
                totals = base.district_totals(profile)
                for actor in item["flexible"]:
                    assert all(totals[f"r{actor}"][p] > 0
                               for p in item["compromises"])
    assert len(ids) == 12


def test_independent_payoff_draws_and_conditioning_rate():
    for structure in opportunity.STRUCTURES:
        for welfare in opportunity.WELFARE:
            items = [opportunity.draw(structure, welfare, 2026093000 + i)
                     for i in range(8)]
            totals = [base.district_totals(item["profile"])
                      for item in items]
            canonical_rows = [tuple(tuple(totals[index][f"r{actor}"].values())
                                    for actor in item["canonical_roles"])
                              for index, item in enumerate(items)]
            assert len(set(canonical_rows)) == len(canonical_rows)
            assert sum(item["draw_attempts"] for item in items) < 4000


def test_reject_unknown_factors():
    for args in (("unknown", "y_high", 1), ("split", "unknown", 1),
                 ("split", "y_high", True)):
        try:
            opportunity.draw(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid factor accepted")


def test_order_strata_are_exact_permutations():
    item = opportunity.draw("split", "y_high", 2026093033)
    early = opportunity.with_order(item, "flexible_first", 33)
    late = opportunity.with_order(item, "flexible_last", 33)
    assert set(early["sponsor_order"]) == set(item["outsiders"])
    assert set(late["sponsor_order"]) == set(item["outsiders"])
    assert set(early["sponsor_order"][:2]) == set(item["flexible"])
    assert set(late["sponsor_order"][-2:]) == set(item["flexible"])
