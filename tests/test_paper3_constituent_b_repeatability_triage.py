"""Pure decision-rule tests; no model calls and no frozen-data mutation."""
from itertools import combinations
import unittest

from analysis.paper3_constituent_b_repeatability_triage import evaluate
from paper3.constituent_b_repeatability_analysis import EXCHANGE_FAMILIES, _compare


def fixture(*, member_totals=(0, 0, 0), universal_totals=(20, 20, 20),
            missing=(), control_policy="q", final_changed=True,
            requested_changed=False):
    profiles, families = [], {}
    for family in EXCHANGE_FAMILIES:
        cells = []
        for block in range(3):
            identifier = family + "-" + str(block)
            member = dict(status="completed", final_policy="A0+B0",
                          enacted_policy="A0+B0", total_citizen_utility=member_totals[block],
                          citizens_worse=10, enforcement_changes=0)
            universal = dict(status="completed",
                             final_policy="A1+B0" if final_changed else "A0+B0",
                             enacted_policy="A1+B0", total_citizen_utility=universal_totals[block],
                             citizens_worse=9, enforcement_changes=0)
            if (family, block, "universal_clearance") in missing:
                universal = dict(status="failed")
            cells.append(dict(profile_id=identifier, family=family, block=block,
                              arms=dict(public_promise=member,
                                        member_enforcement=member,
                                        universal_clearance=universal)))
            pair = _compare(member, universal)
            profiles.append(dict(profile_id=identifier, pairwise=[dict(
                arms=["member_enforcement", "universal_clearance"],
                completed=pair["completed"],
                ballot_projects_match=True,
                requested_ballot_patterns_differ=requested_changed,
                citizen_comparison=dict(overall=dict(citizens_better=1,
                                                     citizens_worse=0))
            )]))
        families[family] = dict(
            cells=cells,
            within_arm={arm: [dict(blocks=[a["block"], b["block"]],
                                   **_compare(a["arms"][arm], b["arms"][arm]))
                              for a, b in combinations(cells, 2)]
                        for arm in ("member_enforcement", "universal_clearance")},
            between_arms={"member_enforcement__universal_clearance": [
                dict(block=cell["block"],
                     **_compare(cell["arms"]["member_enforcement"],
                                cell["arms"]["universal_clearance"]))
                for cell in cells]})
    control = dict(profile_id="aligned", family="aligned_control", block=None,
                   arms={arm: dict(status="completed", enacted_policy=(
                       control_policy if arm == "universal_clearance" else "q"))
                         for arm in ("public_promise", "member_enforcement",
                                     "universal_clearance")})
    profiles.append(dict(profile_id="aligned", pairwise=[]))
    return dict(profiles=profiles,
                repeatability=dict(exchange_families=families,
                                   aligned_control=[control]))


class RepeatabilityTriageTests(unittest.TestCase):
    def test_consistent_between_exceeds_zero_within(self):
        result = evaluate(fixture())
        self.assertTrue(result["triage"])
        self.assertTrue(result["coverage_sufficient"])
        self.assertEqual(result["welfare_signs"], [1])

    def test_one_missing_block_can_be_described_but_not_repaired(self):
        missing = {(family, 2, "universal_clearance")
                   for family in EXCHANGE_FAMILIES}
        result = evaluate(fixture(missing=missing))
        self.assertTrue(result["triage"])
        self.assertTrue(all(row["missing_matched_blocks"] == [2]
                            for row in result["families"].values()))

    def test_insufficient_coverage_is_indeterminate(self):
        missing = {(EXCHANGE_FAMILIES[0], block, "universal_clearance")
                   for block in (1, 2)}
        result = evaluate(fixture(missing=missing))
        self.assertIsNone(result["triage"])
        self.assertFalse(result["coverage_sufficient"])

    def test_within_arm_spread_blocks_continuation(self):
        result = evaluate(fixture(member_totals=(0, 11, 0)))
        self.assertFalse(result["triage"])
        self.assertEqual(result["families"][EXCHANGE_FAMILIES[0]][
            "maximum_absolute_within"], 11)

    def test_direction_and_control_specificity(self):
        self.assertFalse(evaluate(fixture(universal_totals=(20, -20, 20)))["triage"])
        self.assertFalse(evaluate(fixture(control_policy="A0"))["triage"])

    def test_citizen_consequence_without_pre_vote_change_fails(self):
        result = evaluate(fixture(final_changed=False))
        self.assertFalse(result["triage"])
        self.assertTrue(all(not row["lead"] for family in result["families"].values()
                            for row in family["pre_vote_leads"]))
        # An unforced, same-project requested-ballot shift is an allowed
        # alternative pre-vote pathway, even with identical final terms.
        self.assertTrue(evaluate(fixture(final_changed=False,
                                         requested_changed=True))["triage"])


if __name__ == "__main__":
    unittest.main()
