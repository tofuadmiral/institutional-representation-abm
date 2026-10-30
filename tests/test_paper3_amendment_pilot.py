import unittest

from paper3 import amendment_pilot_analysis as analysis
from paper3 import amendment_pilot_design as design


def fake_outcome(amendment="Y", final="X", yes=4):
    return dict(amendment_policy=amendment, final_policy=final,
                amendment_ballots=[True] * yes + [False] * (7 - yes),
                enacted_policy=final,
                enacted_district_utility={f"r{i}": i for i in range(7)},
                unconstrained_menu_regret={f"r{i}": 7 - i for i in range(7)},
                enacted_citizen_utility={f"c{i}": i for i in range(63)})


class AmendmentPilotTests(unittest.TestCase):
    def test_fixed_schedule_unique_seeds_and_profiles(self):
        rows = design.assignments()
        self.assertEqual(rows, design.assignments())
        self.assertEqual(len(rows), 24)
        self.assertEqual(len({row["profile_id"] for row in rows}), 4)
        self.assertEqual(len({row["seed_base"] + i for row in rows
                              for i in range(17)}), 408)

    def test_readout_keeps_all_assignments_and_positive_alternative(self):
        records = {}
        for row in design.assignments():
            amendment = "C" if (row["stratum"] == "mandate_aligned"
                                and row["arm"] == "open_amendment") else row["outsider_ideal"]
            records[row["id"]] = dict(status="completed",
                                       outcome=fake_outcome(amendment, row["favorite"]))
        report = analysis.readout(records)
        self.assertEqual(report["complete_episodes"], 24)
        self.assertEqual(report["complete_blocks"], 8)
        self.assertEqual(report["triage"]["classification"], "selected_action_lead")
        self.assertEqual(len(report["blocks"][0]["actions"]["district_utility_by_arm"]), 3)
        self.assertEqual(report["missingness_bounds"]["open_closed_switch_by_stratum"]
                         ["mandate_aligned"]["switch_rate_lower"], 1)

    def test_missing_block_cannot_be_dropped(self):
        records = {row["id"]: dict(status="completed", outcome=fake_outcome())
                   for row in design.assignments()}
        failed = design.assignments()[0]["id"]
        records[failed] = dict(status="failed")
        report = analysis.readout(records)
        self.assertEqual(report["complete_episodes"], 23)
        self.assertEqual(report["complete_blocks"], 7)
        self.assertEqual(report["triage"]["classification"], "not_identified_incomplete")
        self.assertEqual(len(report["triage"]["missing_blocks"]), 1)
        self.assertGreaterEqual(report["missingness_bounds"]
                                ["open_closed_switch_by_stratum"]["mandate_aligned"]
                                ["switch_rate_upper"],
                                report["missingness_bounds"]
                                ["open_closed_switch_by_stratum"]["mandate_aligned"]
                                ["switch_rate_lower"])
        with self.assertRaises(ValueError):
            analysis.readout({key: value for key, value in records.items() if key != failed})

    def test_mechanical_enactment_cannot_make_action_lead(self):
        records = {row["id"]: dict(status="completed",
                                  outcome=fake_outcome("C", row["favorite"]))
                   for row in design.assignments()}
        report = analysis.readout(records)
        self.assertEqual(report["triage"]["classification"],
                         "no_prespecified_action_lead")
