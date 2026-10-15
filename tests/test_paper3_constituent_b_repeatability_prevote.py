"""Offline tests for supplemental, non-frozen proposal diagnostics."""
import copy
import unittest

from analysis import paper3_constituent_b_repeatability_prevote as diagnostic
from paper3 import coalition_contracts as game
from paper3 import constituent_contract_bridge as bridge
from paper3 import constituent_b_repeatability_design as design


def offer(a="A0", b="B0"):
    return dict(projects=dict(A=a, B=b), first="A",
                coalition=[0, 1, 2, 3], message="fabricated")


def fixture():
    source = design.profiles()
    rows = []
    for item in source:
        prepared = item["prepared"]
        arms = {}
        for arm in game.ARMS:
            final = offer()
            if item["repeatability_block"] == 0 and arm == "universal_clearance":
                final = offer("A1", "B0")
            enacted = bridge.evaluate_passed(
                prepared, list(final["projects"].values()))
            arms[arm] = dict(status="completed", draft_terms=offer(),
                             final_terms=final, citizen_outcome=enacted)
        rows.append(dict(profile_id=prepared["contract_profile"]["id"], arms=arms))
    return source, dict(profiles=rows)


class RepeatabilityPrevoteTests(unittest.TestCase):
    def test_proposals_and_enactments_are_distinct_fields(self):
        source, audited = fixture()
        result = diagnostic.evaluate(source, audited)
        self.assertEqual(len(result["profiles"]), 7)
        row = result["profiles"][0]
        pair = row["contrasts"]["member_enforcement__universal_clearance"]
        self.assertTrue(pair["completed"])
        self.assertTrue(pair["final_proposal"]["full_delivery_policy_changed"])
        self.assertEqual(
            pair["final_proposal"]["total_citizen_utility_change"],
            pair["enacted_total_citizen_utility_change"],
        )
        self.assertEqual(row["arms"]["member_enforcement"]["draft_full_delivery"]
                         ["full_delivery_policy"], "A0+B0")
        self.assertEqual(len(result["exchange_families"]), 2)
        for family in result["exchange_families"].values():
            self.assertEqual(len(family["within_arm_final_proposals"]
                                 ["member_enforcement"]), 3)

    def test_failed_arm_is_retained_without_imputation(self):
        source, audited = fixture()
        audited["profiles"][0]["arms"]["member_enforcement"] = dict(status="failed")
        result = diagnostic.evaluate(source, audited)
        pair = result["profiles"][0]["contrasts"][
            "member_enforcement__universal_clearance"]
        self.assertFalse(pair["completed"])
        family = result["exchange_families"][source[0]["family"]]
        self.assertEqual(sum(not row["completed"] for row in family
                             ["within_arm_final_proposals"]["member_enforcement"]), 2)

    def test_split_or_failed_passage_is_not_mistaken_for_full_delivery(self):
        source, audited = fixture()
        audited["profiles"][0]["arms"]["member_enforcement"]["citizen_outcome"] = (
            bridge.evaluate_passed(source[0]["prepared"], []))
        result = diagnostic.evaluate(source, audited)
        cell = result["profiles"][0]["arms"]["member_enforcement"]
        self.assertNotEqual(cell["final_full_delivery"]["full_delivery_policy"],
                            cell["enacted_policy"])
        self.assertEqual(cell["final_full_delivery"]["full_delivery_policy"],
                         "A0+B0")

    def test_inventory_and_table_drift_rejected(self):
        source, audited = fixture()
        with self.assertRaisesRegex(ValueError, "inventory"):
            diagnostic.evaluate(source, dict(profiles=audited["profiles"][:-1]))
        bad = copy.deepcopy(source)
        bad[1]["prepared"]["contract_profile"]["utilities"][0]["A0"] += 1
        with self.assertRaisesRegex(ValueError, "payoff or electorate"):
            diagnostic.evaluate(bad, audited)


if __name__ == "__main__":
    unittest.main()
