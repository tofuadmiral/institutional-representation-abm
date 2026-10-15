"""Offline constituent-level readout tests; no model outputs or experiment."""
from copy import deepcopy
import json
import unittest

from paper3 import coalition_contracts as game
from paper3 import constituent_b_analysis as analysis
from paper3 import constituent_b_design as design
from paper3 import constituent_b_institution as institution


def fixture_records(profiles):
    return {(item["prepared"]["contract_profile"]["id"], arm):
            dict(status="not_started")
            for item in profiles for arm in game.ARMS}


def fabricated_episode(prepared, arm, *, project="A0", vote=True):
    def ask(actor, stage, messages, index):
        if stage in ("draft", "response", "final"):
            reply = dict(projects=dict(A=project, B="B0"), first="A",
                         coalition=[], message="fabricated")
            if stage == "response":
                reply["support"] = True
        elif stage == "consent":
            reply = dict(consent=True)
        else:
            reply = dict(vote=vote)
        return json.dumps(reply)

    return dict(status="completed", **institution.episode(prepared, arm, ask))


def pivotal_episode(prepared):
    """Four first-round yes votes include an A0-harmed B district."""
    first_yes = {0, 1, 5, 6}

    def ask(actor, stage, messages, index):
        if stage in ("draft", "response", "final"):
            reply = dict(projects=dict(A="A0", B="B0"), first="A",
                         coalition=[], message="fabricated")
            if stage == "response":
                reply["support"] = True
        elif stage == "consent":
            reply = dict(consent=True)
        else:
            reply = dict(vote=actor in first_yes if stage == "first_vote" else False)
        return json.dumps(reply)

    return dict(status="completed", **institution.episode(prepared, "public_promise", ask))


class ConstituentAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.profiles = design.frame(641001)
        self.records = fixture_records(self.profiles)
        self.profile = self.profiles[0]["prepared"]
        self.profile_id = self.profile["contract_profile"]["id"]

    def test_missing_cells_are_kept_with_finite_menu_bounds(self):
        report = analysis.readout(self.profiles, self.records)
        self.assertEqual(report["assigned_episodes"], 12)
        self.assertEqual(report["completed_episodes"], 0)
        self.assertEqual(report["assigned_profile_pairs"], 12)
        self.assertEqual(report["completed_profile_pairs"], 0)
        for item in report["profiles"]:
            self.assertEqual(len(item["pairwise"]), 3)
            self.assertEqual(set(item["arms"]), set(game.ARMS))
            for comparison in item["pairwise"]:
                bounds = comparison["finite_bounds"]
                self.assertEqual(bounds["possible_outcome_pairs"], 81)
                self.assertLessEqual(bounds["citizens_harmed"][1], 63)
                self.assertLessEqual(bounds["citizens_harmed"][0],
                                     bounds["citizens_harmed"][1])

    def test_completed_comparison_separates_terms_from_mechanical_votes(self):
        configurations = (("public_promise", "A0", True),
                          ("member_enforcement", "A1", True),
                          ("universal_clearance", "A0", False))
        for arm, project, vote in configurations:
            self.records[(self.profile_id, arm)] = fabricated_episode(
                self.profile, arm, project=project, vote=vote)
        report = analysis.readout(self.profiles, self.records)
        self.assertEqual(report["completed_episodes"], 3)
        self.assertEqual(report["completed_profile_pairs"], 3)
        first = report["profiles"][0]
        self.assertEqual(first["arms"]["public_promise"]["passed"], ["A0", "B0"])
        self.assertEqual(first["arms"]["universal_clearance"]["passed"], [])
        for comparison in first["pairwise"]:
            self.assertTrue(comparison["completed"])
            self.assertEqual(comparison["finite_bounds"]["possible_outcome_pairs"], 1)
            self.assertEqual(comparison["finite_bounds"]["total_utility_change"][0],
                             comparison["finite_bounds"]["total_utility_change"][1])
            self.assertEqual(len(comparison["citizen_comparison"]["citizens"]), 63)
        public_member = first["pairwise"][0]
        self.assertTrue(public_member["before_vote_final_changed"])
        self.assertFalse(public_member["ballot_projects_match"])
        self.assertFalse(public_member["requested_ballot_patterns_differ"])

    def test_one_missing_arm_bounds_nine_possible_outcomes(self):
        self.records[(self.profile_id, "public_promise")] = fabricated_episode(
            self.profile, "public_promise")
        report = analysis.readout(self.profiles, self.records)
        first = report["profiles"][0]
        self.assertEqual(sum(pair["completed"] for pair in first["pairwise"]), 0)
        self.assertEqual(first["pairwise"][0]["finite_bounds"]["possible_outcome_pairs"], 9)
        self.assertEqual(first["pairwise"][2]["finite_bounds"]["possible_outcome_pairs"], 81)

    def test_changed_episode_or_missing_assignment_is_rejected(self):
        self.records[(self.profile_id, "public_promise")] = fabricated_episode(
            self.profile, "public_promise")
        tampered = deepcopy(self.records)
        tampered[(self.profile_id, "public_promise")]["outcome"]["passed"] = []
        with self.assertRaisesRegex(ValueError, "disagrees"):
            analysis.readout(self.profiles, tampered)
        tampered = deepcopy(self.records)
        tampered.pop((self.profile_id, "member_enforcement"))
        with self.assertRaisesRegex(ValueError, "inventory"):
            analysis.readout(self.profiles, tampered)

    def test_fixed_continuation_pivotal_check_is_local_not_global_regret(self):
        saved = pivotal_episode(self.profile)
        self.assertEqual(saved["outcome"]["passed"], ["A0"])
        checks = analysis.fixed_continuation_ballot_checks(
            self.profile, "public_promise", saved["events"])
        self.assertEqual(len(checks), 14)
        harmed_b = next(item for item in checks if item["stage"] == "first_vote"
                        and item["actor"] == 0)
        self.assertEqual(harmed_b["local_missed_gain"], 2)
        self.assertEqual(harmed_b["alternative_passed"], [])
        positive_a = next(item for item in checks if item["stage"] == "first_vote"
                          and item["actor"] == 1)
        self.assertEqual(positive_a["local_missed_gain"], 0)
        self.assertLess(positive_a["alternative_own_district_utility_change"], 0)
        self.assertTrue(all(item["local_missed_gain"] == 0 for item in checks
                            if item["stage"] == "second_vote"))
        tampered = deepcopy(saved["events"])
        next(item for item in tampered if item["type"] == "first_vote")["passed"] = False
        with self.assertRaisesRegex(ValueError, "saved vote"):
            analysis.fixed_continuation_ballot_checks(
                self.profile, "public_promise", tampered)

    def test_enforced_request_is_not_misread_as_pivotal_model_choice(self):
        def ask(actor, stage, messages, index):
            if stage in ("draft", "response", "final"):
                reply = dict(projects=dict(A="A0", B="B0"), first="A",
                             coalition=[0, 1, 5, 6], message="fabricated")
                if stage == "response":
                    reply["support"] = True
            elif stage == "consent":
                reply = dict(consent=True)
            else:
                reply = dict(vote=False)
            return json.dumps(reply)

        saved = institution.episode(self.profile, "member_enforcement", ask)
        self.assertEqual(saved["outcome"]["passed"], ["A0", "B0"])
        checks = analysis.fixed_continuation_ballot_checks(
            self.profile, "member_enforcement", saved["events"])
        first = next(item for item in checks if item["stage"] == "first_vote"
                     and item["actor"] == 0)
        self.assertFalse(first["requested"])
        self.assertTrue(first["executed"])
        self.assertTrue(first["request_was_overridden"])
        self.assertEqual(first["alternative_own_district_utility_change"], 0)


if __name__ == "__main__":
    unittest.main()
