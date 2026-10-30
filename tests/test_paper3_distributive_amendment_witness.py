"""A toy existence proof, not behavioral evidence or a population sample."""
from __future__ import annotations

from paper3 import amendment_institution as institution
from paper3 import direct_ratification as base
from paper3 import distributive_amendment_witness as witness


def test_four_structural_cells_and_two_rights_holders():
    seen = set()
    for size in (4, 5):
        for welfare_high in (False, True):
            item = witness.opportunity(size, welfare_high)
            profile = item["profile"]
            totals = base.district_totals(profile)
            pairwise = item["pairwise_over_favorite"]
            assert len(pairwise[witness.OWN_COMPROMISE]) == size
            assert len(pairwise[witness.OTHER_COMPROMISE]) == 9 - size
            assert pairwise[witness.OWN_COMPROMISE] != pairwise[
                witness.OTHER_COMPROMISE]
            assert (item["total_citizen_utility"][witness.OWN_COMPROMISE] >
                    item["total_citizen_utility"][witness.OTHER_COMPROMISE]) is welfare_high
            assert (totals["r0"][witness.FAVORITE] >
                    totals["r0"][witness.OWN_COMPROMISE] >
                    totals["r0"][witness.OTHER_COMPROMISE])
            assert (totals["r1"][witness.OWN_COMPROMISE] >
                    totals["r1"][witness.FAVORITE] >
                    totals["r1"][witness.OTHER_COMPROMISE])
            assert (totals["r6"][witness.OTHER_COMPROMISE] >
                    totals["r6"][witness.FAVORITE] >
                    totals["r6"][witness.OWN_COMPROMISE])
            aligned = profile["districts"]["r1"]
            opposed = profile["districts"]["r6"]
            assert sum(c["utility"][witness.OTHER_COMPROMISE] >
                       c["utility"][witness.OWN_COMPROMISE]
                       for c in aligned) == 5
            assert sum(c["utility"][witness.OWN_COMPROMISE] >
                       c["utility"][witness.OTHER_COMPROMISE]
                       for c in opposed) == 5
            assert sum(map(len, profile["districts"].values())) == 63
            for right_holder in item["rights_holders"]:
                game = witness.institution_item(item, right_holder)
                holder_totals = totals[f"r{right_holder}"]
                expected = (witness.OWN_COMPROMISE if right_holder ==
                            witness.ALIGNED_RIGHT_HOLDER else
                            witness.OTHER_COMPROMISE)
                assert holder_totals[expected] > holder_totals[
                    witness.OTHER_COMPROMISE if expected ==
                    witness.OWN_COMPROMISE else witness.OWN_COMPROMISE]
                final_ballots = [totals[f"r{actor}"][witness.FAVORITE] > 0
                                 for actor in base.ACTORS]
                for policy in (witness.OWN_COMPROMISE,
                               witness.OTHER_COMPROMISE):
                    amendment_ballots = [actor in pairwise[policy]
                                         for actor in base.ACTORS]
                    opened = institution.enact(game, "open_amendment", policy,
                                                witness.FAVORITE,
                                                amendment_ballots, final_ballots)
                    closed = institution.enact(game, "closed_agenda", policy,
                                                witness.FAVORITE,
                                                amendment_ballots, final_ballots)
                    assert opened["enacted_policy"] == policy
                    assert closed["enacted_policy"] == witness.FAVORITE
            seen.add((size, welfare_high))
    assert len(seen) == 4
