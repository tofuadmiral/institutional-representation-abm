import copy
import unittest

from paper3 import constituent_contract_bridge as bridge
from paper3 import constituent_mandates
from paper3 import coalition_contracts


class ConstituentContractBridgeTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "policies": {"q": [0, 0], "A0": [1, 0], "A1": [-1, 0],
                         "B0": [0, 1], "B1": [0, -1]},
            "districts": {f"r{i}": [
                {"id": f"c{i}-{j}", "ideal": [1 if j < 5 else -1, 1 if i < 4 else -1],
                 "weights": [1 if j < 8 else 13, 1]}
                for j in range(9)] for i in range(7)},
        }

    def prepare(self, profile=None):
        return bridge.prepare(profile or self.profile, "citizen-b", 0,
                              aggregation="sum_of_citizen_utilities")

    @staticmethod
    def fixed_standing_profile():
        districts = {}
        for i in range(7):
            if i < 3:
                weak, strong, priority = [-1, 1], [5, -1], [3, 1]
            elif i < 6:
                weak, strong, priority = [1, -1], [-1, 5], [1, 3]
            else:
                weak = strong = [-1, -1]
                priority = [2, 2]
            districts[f"r{i}"] = [
                {"id": f"fixed-{i}-{j}", "ideal": weak if j < 5 else strong,
                 "weights": [2, 2] if j < 5 else priority}
                for j in range(9)]
        return {"policies": {"q": [0, 0], "A0": [1, 0], "A1": [2, 0],
                             "B0": [0, 1], "B1": [0, 2]},
                "districts": districts}

    def test_all_outcomes_conserve_individual_and_district_utilities(self):
        prepared = self.prepare()
        self.assertEqual(len(prepared["contract_profile"]["utilities"]), 7)
        self.assertEqual(len(prepared["electorate_profile"]["policies"]), 9)
        for passed in ([], ["A0"], ["A1"], ["B0"], ["B1"],
                       ["A0", "B0"], ["A0", "B1"], ["A1", "B0"], ["A1", "B1"]):
            with self.subTest(passed=passed):
                result = bridge.evaluate_passed(prepared, passed)
                self.assertEqual(result["overall"]["citizen_count"], 63)
                self.assertEqual(sum(d["total_relative_utility"]
                                     for d in result["districts"].values()),
                                 result["overall"]["total_relative_utility"])

    def test_plurality_and_cardinal_mandate_remain_distinct(self):
        prepared = self.prepare()
        district = prepared["electorate_profile"]["districts"]["r0"]
        self.assertEqual(len(district), 9)
        self.assertEqual(prepared["aggregation"], "sum_of_citizen_utilities")
        # Five equal-person first choices prefer the A0 package, while one
        # high-priority dissenting citizen flips summed district welfare.
        counts = constituent_mandates.preference_counts(
            prepared["electorate_profile"])["r0"]
        self.assertEqual(counts["strict_first_choice_counts"]["A0+B0"], 5)
        self.assertEqual(counts["strict_first_choice_counts"]["A1+B0"], 4)
        self.assertEqual(constituent_mandates.mandates(
            prepared["electorate_profile"])["r0"]["best_policy_ids"], ["A1+B0"])
        self.assertGreater(prepared["contract_profile"]["utilities"][0]["A1"],
                           prepared["contract_profile"]["utilities"][0]["A0"])
        # The adapter does not choose a plurality or electoral winner.
        self.assertNotIn("election_winner", prepared)
        self.assertEqual(counts["citizen_count"], 9)

    def test_bad_shapes_and_aggregation_fail_without_mutation(self):
        original = copy.deepcopy(self.profile)
        for change in (
            lambda p: p["policies"]["A0"].__setitem__(1, 1),
            lambda p: p["policies"]["B0"].__setitem__(0, 1),
            lambda p: p["districts"].pop("r6"),
            lambda p: p["policies"].update(extra=[1, 1]),
        ):
            with self.subTest(change=change):
                bad = copy.deepcopy(original)
                change(bad)
                with self.assertRaises(ValueError):
                    self.prepare(bad)
        with self.assertRaises(ValueError):
            bridge.prepare(self.profile, "citizen-b", 0, aggregation="majority")
        self.assertEqual(self.profile, original)

    def test_invalid_outcomes_fail(self):
        prepared = self.prepare()
        for passed in (["A0", "A1"], ["A0", "A0"], ["q"], ["X"], ["A0", "B0", "B1"]):
            with self.subTest(passed=passed), self.assertRaises(ValueError):
                bridge.evaluate_passed(prepared, passed)

    def test_prepared_citizens_are_snapshot_not_input_alias(self):
        prepared = self.prepare()
        expected = bridge.evaluate_passed(prepared, ["A0", "B0"])
        self.profile["districts"]["r0"][0]["ideal"][0] = 999
        self.assertEqual(bridge.evaluate_passed(prepared, ["A0", "B0"]), expected)

    def test_fixed_priority_budget_and_equal_person_frame(self):
        profile = self.fixed_standing_profile()
        original = copy.deepcopy(profile)
        prepared = bridge.prepare_equal_standing(
            profile, "fixed-standing", 0, citizens_per_district=9,
            priority_budget=4, coordinate_bound=5)
        self.assertEqual(prepared["equal_standing_specification"], dict(
            citizens_per_district=9, priority_budget=4,
            coordinate_bound=5, citizen_count=63))
        self.assertEqual(prepared["contract_profile"]["utilities"][0]["A0"], 78)
        counts = constituent_mandates.preference_counts(
            prepared["electorate_profile"])["r0"]
        self.assertEqual(counts["strict_first_choice_counts"]["B0"], 5)
        self.assertEqual(bridge.compare_passed(prepared, [], ["A0", "B0"])[
            "overall"]["citizens_worse"], 39)
        self.assertEqual(profile, original)
        for change, kwargs in (
            (lambda p: p["districts"]["r0"][0]["weights"].__setitem__(0, 3), {}),
            (lambda p: p["districts"]["r0"].pop(), {}),
            (lambda p: p["districts"]["r0"][0]["ideal"].__setitem__(0, 6), {}),
            (lambda p: None, {"citizens_per_district": True}),
        ):
            with self.subTest(change=change, kwargs=kwargs):
                bad = copy.deepcopy(original)
                change(bad)
                params = dict(citizens_per_district=9, priority_budget=4,
                              coordinate_bound=5)
                params.update(kwargs)
                with self.assertRaises(ValueError):
                    bridge.prepare_equal_standing(bad, "fixed-standing", 0, **params)

    def test_constructed_exchange_opportunity_exposes_mandate_conflict(self):
        # Arithmetic existence proof, deliberately selected and NOT a sampled
        # profile, pilot case, or LLM result. Six districts have five citizens
        # whose first choice opposes their district's summed-utility favorite.
        districts = {}
        for i in range(7):
            if i < 3:
                weak, strong, priority = [-1, 1], [5, -1], [2, 1]
            elif i < 6:
                weak, strong, priority = [1, -1], [-1, 5], [1, 2]
            else:
                weak = strong = [-1, -1]
                priority = [1, 1]
            districts[f"r{i}"] = [
                {"id": f"c{i}-{j}", "ideal": weak if j < 5 else strong,
                 "weights": [1, 1] if j < 5 else priority}
                for j in range(9)]
        profile = {"policies": {"q": [0, 0], "A0": [1, 0], "A1": [2, 0],
                                "B0": [0, 1], "B1": [0, 2]},
                   "districts": districts}
        prepared = self.prepare(profile)
        rows = prepared["contract_profile"]["utilities"]
        self.assertEqual([rows[i]["A0"] for i in range(7)],
                         [57, 57, 57, -7, -7, -7, -27])
        self.assertEqual([rows[i]["B0"] for i in range(7)],
                         [-7, -7, -7, 57, 57, 57, -27])
        counts = constituent_mandates.preference_counts(
            prepared["electorate_profile"])
        self.assertEqual(counts["r0"]["strict_first_choice_counts"]["B0"], 5)
        self.assertEqual(counts["r3"]["strict_first_choice_counts"]["A0"], 5)
        opportunities = [offer for offer in coalition_contracts.offer_inventory(
            prepared["contract_profile"])
            if offer["projects"] == {"A": "A0", "B": "B0"}
            and offer["coalition"] == [0, 1, 3, 4]]
        self.assertEqual(len(opportunities), 2)  # both execution orders
        self.assertTrue(all(offer["member_strict_improvement"] and
                            offer["outsiders_harmed_vs_independent"] == [6]
                            for offer in opportunities))
        outcome = bridge.evaluate_passed(prepared, ["A0", "B0"])
        self.assertEqual(outcome["districts"]["r0"]["total_relative_utility"], 50)
        self.assertEqual(outcome["districts"]["r0"]["citizens_worse_than_q"], 5)
        self.assertEqual(outcome["districts"]["r6"]["citizens_worse_than_q"], 9)
        self.assertEqual(outcome["overall"]["citizens_worse_than_q"], 39)
        paired = bridge.compare_passed(prepared, [], ["A0", "B0"])
        self.assertEqual(paired["overall"]["citizens_better"], 24)
        self.assertEqual(paired["overall"]["citizens_worse"], 39)
        self.assertEqual(paired["overall"]["total_utility_change"], 246)
        self.assertEqual(paired["districts"]["r0"]["total_utility_change"], 50)
        self.assertEqual(paired["districts"]["r6"]["total_utility_change"], -54)


if __name__ == "__main__":
    unittest.main()
