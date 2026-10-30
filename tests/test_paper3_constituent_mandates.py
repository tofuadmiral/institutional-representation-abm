import copy
import unittest

from paper3 import constituent_mandates as m


class ConstituentMandatesTests(unittest.TestCase):
    def setUp(self):
        self.profile = dict(
            policies=dict(q=[0, 0], a=[2, 0], b=[0, 2]),
            districts=dict(d0=[
                dict(id="c0", ideal=[2, 0], weights=[2, 1]),
                dict(id="c1", ideal=[0, 2], weights=[1, 3]),
            ]),
        )

    def test_district_and_citizen_outcomes_are_distinct(self):
        self.assertEqual(m.mandates(self.profile)["d0"], dict(
            aggregation="sum_of_citizen_utilities", citizen_count=2,
            policy_total_utility=dict(q=0, a=4, b=8),
            best_policy_ids=["b"]))
        result = m.evaluate(self.profile, "a")
        self.assertEqual(result["citizens"]["c0"]["relative_utility"], 8)
        self.assertEqual(result["citizens"]["c1"]["relative_utility"], -4)
        self.assertEqual(result["citizens"]["c1"]["own_regret"], 16)
        self.assertEqual(result["districts"]["d0"]["mandate_regret"], 4)
        self.assertEqual(result["overall"], dict(
            citizen_count=2, total_relative_utility=4,
            mean_individual_regret_exact="8", worst_individual_regret=16,
            citizens_worse_than_q=1))

    def test_status_quo_and_ties(self):
        profile = dict(policies=dict(q=[0], a=[1], b=[-1]),
                       districts=dict(d0=[dict(id="c", ideal=[0], weights=[1])]))
        self.assertEqual(m.mandates(profile)["d0"]["best_policy_ids"], ["q"])
        self.assertEqual(m.evaluate(profile, "q")["overall"]["citizens_worse_than_q"], 0)
        profile["districts"]["d0"].append(dict(id="d", ideal=[1], weights=[1]))
        self.assertEqual(m.mandates(profile)["d0"]["best_policy_ids"], ["q", "a"])

    def test_utilitarian_total_is_not_a_majority_vote(self):
        profile = dict(policies=dict(q=[0], a=[1], b=[-1]),
                       districts=dict(d0=[
                           dict(id="c0", ideal=[1], weights=[10]),
                           dict(id="c1", ideal=[-1], weights=[1]),
                       ]))
        result = m.evaluate(profile, "a")
        self.assertEqual(result["citizens"]["c0"]["own_best_policy_ids"], ["a"])
        self.assertEqual(result["citizens"]["c1"]["own_best_policy_ids"], ["b"])
        self.assertEqual(result["districts"]["d0"]["mandate_best_policy_ids"], ["a"])
        self.assertEqual(result["districts"]["d0"]["citizens_worse_than_q"], 1)

    def test_equal_person_majority_can_disagree_with_utilitarian_total(self):
        profile = dict(policies=dict(q=[0], a=[1], b=[-1]),
                       districts=dict(d0=[
                           dict(id="c0", ideal=[1], weights=[1]),
                           dict(id="c1", ideal=[1], weights=[1]),
                           dict(id="c2", ideal=[-1], weights=[10]),
                       ]))
        self.assertEqual(m.mandates(profile)["d0"]["best_policy_ids"], ["b"])
        counts = m.preference_counts(profile)["d0"]
        self.assertEqual(counts["strict_first_choice_counts"],
                         dict(q=0, a=2, b=1))
        self.assertEqual(counts["tied_first_choice_citizens"], 0)
        a_vs_b = next(row for row in counts["pairwise"]
                      if row["first_policy_id"] == "a"
                      and row["second_policy_id"] == "b")
        self.assertEqual((a_vs_b["first_preferred"],
                          a_vs_b["second_preferred"], a_vs_b["indifferent"]),
                         (2, 1, 0))

    def test_ties_are_not_arbitrarily_broken(self):
        profile = dict(policies=dict(q=[0], a=[1], b=[-1]),
                       districts=dict(d0=[dict(id="c", ideal=[0], weights=[1])]))
        counts = m.preference_counts(profile)["d0"]
        self.assertEqual(counts["strict_first_choice_counts"],
                         dict(q=1, a=0, b=0))
        a_vs_b = next(row for row in counts["pairwise"]
                      if row["first_policy_id"] == "a"
                      and row["second_policy_id"] == "b")
        self.assertEqual(a_vs_b["indifferent"], 1)
        profile["policies"]["b"] = [0]
        counts = m.preference_counts(profile)["d0"]
        self.assertEqual(counts["strict_first_choice_counts"],
                         dict(q=0, a=0, b=0))
        self.assertEqual(counts["tied_first_choice_citizens"], 1)

    def test_scale_independent_of_legislature_size(self):
        profile = dict(policies=dict(q=[0, 0], a=[1, 1]), districts={
            f"d{i}": [dict(id=f"c{i}-{j}", ideal=[i, j], weights=[1, 2])
                      for j in range(9)] for i in range(7)})
        result = m.evaluate(profile, "a")
        self.assertEqual(result["overall"]["citizen_count"], 63)
        self.assertEqual(len(result["districts"]), 7)
        self.assertEqual(len(result["citizens"]), 63)

    def test_invalid_profiles_are_rejected_without_mutation(self):
        original = copy.deepcopy(self.profile)
        for change in (
            lambda p: p["policies"].pop("q"),
            lambda p: p["policies"].update(b=[0]),
            lambda p: p["districts"]["d0"].append(
                dict(id="c0", ideal=[0, 0], weights=[1, 1])),
            lambda p: p["districts"]["d0"][0]["weights"].__setitem__(0, 0),
            lambda p: p["districts"]["d0"][0]["ideal"].__setitem__(0, True),
            lambda p: p["districts"].update(d1=[]),
        ):
            with self.subTest(change=change):
                bad = copy.deepcopy(original)
                change(bad)
                with self.assertRaises(ValueError):
                    m.validate(bad)
        self.assertEqual(self.profile, original)
        with self.assertRaises(ValueError):
            m.evaluate(self.profile, "missing")

    def test_paired_outcome_comparison_preserves_each_citizen(self):
        comparison = m.compare(self.profile, "q", "a")
        self.assertEqual(comparison["citizens"]["c0"], dict(
            district="d0", utility_change=8, regret_change=-8))
        self.assertEqual(comparison["citizens"]["c1"], dict(
            district="d0", utility_change=-4, regret_change=4))
        self.assertEqual(comparison["districts"]["d0"], dict(
            citizen_count=2, total_utility_change=4,
            citizens_better=1, citizens_worse=1, citizens_unchanged=0))
        self.assertEqual(comparison["overall"], dict(
            citizen_count=2, total_utility_change=4,
            mean_utility_change_exact="2", citizens_better=1,
            citizens_worse=1, citizens_unchanged=0))
        reverse = m.compare(self.profile, "a", "q")
        self.assertEqual(reverse["overall"]["total_utility_change"], -4)
        self.assertEqual(reverse["overall"]["citizens_better"], 1)
        same = m.compare(self.profile, "a", "a")
        self.assertEqual(same["overall"]["citizens_unchanged"], 2)


if __name__ == "__main__":
    unittest.main()
