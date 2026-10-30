import unittest

from paper3 import amendment_benchmarks as benchmarks
from paper3 import amendment_opportunity as opportunity


class AmendmentBenchmarkTests(unittest.TestCase):
    def test_complete_arm_pair_inventory_and_tie_sets(self):
        for item in opportunity.frame():
            with self.subTest(profile=item["profile"]["id"]):
                report = benchmarks.inventory(item)
                self.assertEqual(len(report["rows"]), 27)
                self.assertEqual(sum(report["positive_utility_ballots"][item["outsider_ideal"]]), 3)
                self.assertGreaterEqual(sum(report["positive_utility_ballots"]["C"]), 4)
                favorite = item["favorite"]
                ideal_open = next(row for row in report["rows"]
                                  if row["arm"] == "open_amendment"
                                  and row["amendment"] == item["outsider_ideal"]
                                  and row["final"] == favorite)
                compromise_open = next(row for row in report["rows"]
                                       if row["arm"] == "open_amendment"
                                       and row["amendment"] == "C"
                                       and row["final"] == favorite)
                self.assertEqual(ideal_open["enacted"], favorite)
                self.assertEqual(compromise_open["enacted"], "C")
                self.assertEqual(ideal_open["amendment_over_final_count"], 3)
                self.assertEqual(compromise_open["amendment_over_final_count"],
                                 4 if item["stratum"] == "mandate_aligned" else 3)
                self.assertEqual(compromise_open["conditional_fallback_enacted"],
                                 "C" if item["stratum"] == "mandate_aligned" else favorite)
                self.assertEqual(set(report["set_valued_feasible_proposer_upper_bound"]),
                                 {"closed_agenda", "open_amendment", "citizen_veto"})
                for arm, best in report["set_valued_feasible_proposer_upper_bound"].items():
                    self.assertTrue(best["amendment_final_pairs"])
                    self.assertEqual(best["proposer_utility"], max(
                        row["proposer_utility"] for row in report["rows"]
                        if row["arm"] == arm))

    def test_divergent_mandate_is_not_mistaken_for_citizen_approval(self):
        item = opportunity.draw(0, "mandate_divergent")
        report = benchmarks.inventory(item)
        favorite = item["favorite"]
        self.assertEqual(report["outsider_citizen_yes_counts"][favorite], 4)
        self.assertGreater(report["district_totals"][f'r{item["outsider"]}'][favorite],
                           report["district_totals"][f'r{item["outsider"]}']["C"])
        closed = next(row for row in report["rows"] if row["arm"] == "closed_agenda"
                      and row["amendment"] == "C" and row["final"] == favorite)
        veto = next(row for row in report["rows"] if row["arm"] == "citizen_veto"
                    and row["amendment"] == "C" and row["final"] == favorite)
        self.assertEqual(closed["enacted"], favorite)
        self.assertEqual(veto["enacted"], "q")
