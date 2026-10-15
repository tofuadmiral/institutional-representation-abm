"""Offline fabricated readout checks before any election-model run."""
import json
import unittest

from paper3 import electoral_accountability as game
from paper3 import electoral_accountability_analysis as analysis
from paper3 import electoral_accountability_design as design


def fabricated_records():
    records = {}
    for item in design.inventory():
        for arm in game.ARMS:
            focal = item["focal"]
            supporters = {actor for actor in game.ACTORS
                          if all(c["p"] > 0 for c in
                                 item["profile"]["districts"][f"r{actor}"])}
            consents = [actor in supporters for actor in game.ACTORS]
            requested = consents.copy()
            if item["id"].startswith("credit-conflict"):
                consents[focal] = arm == "binding_requested_record"
                requested[focal] = False
            elif item["id"] == "credit-aligned-control":
                consents[focal] = True
                requested[focal] = True
            else:
                consents[focal] = True
                requested[focal] = True

            def ask(actor, stage, messages, index):
                value = (consents if stage == "consent" else requested)[actor]
                return json.dumps({"consent" if stage == "consent" else "vote": value})

            episode = game.episode(item["profile"], arm, ask)
            records[(item["id"], arm)] = dict(status="completed", **episode)
    return records


class ElectionAnalysisTests(unittest.TestCase):
    def test_full_constructed_pathway_requires_pre_enforcement_choices(self):
        report = analysis.readout(fabricated_records())
        screen = analysis.discovery_screen(report)
        self.assertEqual(report["assignments"], 16)
        self.assertEqual(report["completed_episodes"], 16)
        self.assertEqual(screen["pathway"], "selected_case_mechanism_lead")
        self.assertTrue(all(row["predicted_choice_pattern"] for row in
                            screen["conflicts"]))
        self.assertTrue(all(row["matched_pivotal_opportunity"] for row in
                            screen["conflicts"]))
        self.assertTrue(all(screen["controls"].values()))
        first = report["profiles"][0]
        self.assertEqual(first["cells"]["binding_requested_record"]["focal_action"],
                         "consent_request_no")
        self.assertEqual(first["cells"]["binding_executed_record"]["focal_action"],
                         "refuse_request_no")

    def test_missing_cell_kept_with_finite_bounds_and_not_classified(self):
        records = fabricated_records()
        key = ("credit-conflict-a", "binding_requested_record")
        records[key] = dict(status="failed", error="invalid action", prefix=["retained"])
        report = analysis.readout(records)
        screen = analysis.discovery_screen(report)
        self.assertEqual(report["assignments"], 16)
        self.assertEqual(report["completed_episodes"], 15)
        self.assertEqual(screen["pathway"], "incomplete_not_classified")
        cell = report["profiles"][0]["cells"][key[1]]
        self.assertEqual(cell["status"], "failed")
        self.assertEqual(cell["finite_missingness_bounds"]["focal_policy_utility"],
                         [0, 22])
        self.assertEqual(cell["prefix"], ["retained"])

    def test_changed_controller_outcome_without_choice_divergence_is_not_lead(self):
        records = fabricated_records()
        for item in design.inventory()[:2]:
            key = (item["id"], "binding_requested_record")
            saved = records[key]
            focal = item["focal"]
            saved["events"][1]["consents"][focal] = False
            saved["outcome"] = game.score(item["profile"], key[1], saved["events"])
        screen = analysis.discovery_screen(analysis.readout(records))
        self.assertEqual(screen["pathway"], "no_repeated_choice_divergence")
        self.assertFalse(any(row["before_enforcement_divergence"] for row in
                             screen["conflicts"]))

    def test_unmatched_early_coalition_is_not_attribution_evidence(self):
        records = fabricated_records()
        key = ("credit-conflict-a", "binding_executed_record")
        saved = records[key]
        saved["events"][0]["consents"]["r0"] = False
        saved["events"][1]["consents"][0] = False
        profile = design.inventory()[0]["profile"]
        saved["outcome"] = game.score(profile, key[1], saved["events"])
        screen = analysis.discovery_screen(analysis.readout(records))
        self.assertEqual(screen["pathway"], "coalition_opportunity_not_matched")
        self.assertFalse(screen["conflicts"][0]["matched_pivotal_opportunity"])

    def test_nonbinding_record_label_difference_is_ambiguous(self):
        records = fabricated_records()
        key = ("credit-conflict-a", "promise_executed_record")
        saved = records[key]
        focal = design.inventory()[0]["focal"]
        saved["events"][1]["consents"][focal] = True
        saved["outcome"] = game.score(design.inventory()[0]["profile"],
                                       key[1], saved["events"])
        screen = analysis.discovery_screen(analysis.readout(records))
        self.assertEqual(screen["pathway"], "ambiguous_controls")
        self.assertFalse(screen["controls"]["promise_focal_choice_invariant"])

    def test_no_office_non_enactment_is_ambiguous(self):
        records = fabricated_records()
        key = ("credit-no-office-control", "binding_executed_record")
        saved = records[key]
        focal = design.inventory()[3]["focal"]
        saved["events"][1]["consents"][focal] = False
        saved["events"][2]["requested"][focal] = False
        saved["outcome"] = game.score(design.inventory()[3]["profile"],
                                       key[1], saved["events"])
        screen = analysis.discovery_screen(analysis.readout(records))
        self.assertEqual(screen["pathway"], "ambiguous_controls")
        self.assertFalse(screen["controls"]["no_office_both_enact_p"])

    def test_no_office_requested_vote_is_payoff_indifferent(self):
        records = fabricated_records()
        key = ("credit-no-office-control", "binding_executed_record")
        saved = records[key]
        focal = design.inventory()[3]["focal"]
        saved["events"][2]["requested"][focal] = False
        saved["outcome"] = game.score(design.inventory()[3]["profile"],
                                       key[1], saved["events"])
        screen = analysis.discovery_screen(analysis.readout(records))
        self.assertEqual(screen["pathway"], "selected_case_mechanism_lead")
        self.assertTrue(screen["controls"]["no_office_both_enact_p"])

    def test_inventory_is_exact_not_selectively_subsampled(self):
        records = fabricated_records()
        records.pop(next(iter(records)))
        with self.assertRaises(ValueError):
            analysis.readout(records)


if __name__ == "__main__":
    unittest.main()
