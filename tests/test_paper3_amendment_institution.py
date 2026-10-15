import json
import unittest

from paper3 import amendment_institution as institution
from paper3 import amendment_opportunity as opportunity


class AmendmentInstitutionTests(unittest.TestCase):
    def setUp(self):
        self.aligned = opportunity.draw(0, "mandate_aligned")
        self.divergent = opportunity.draw(0, "mandate_divergent")

    def test_controller_replays_identical_actions_under_all_three_arms(self):
        for item in (self.aligned, self.divergent):
            with self.subTest(stratum=item["stratum"]):
                favorite = item["favorite"]
                amendment = "C"
                four_yes = [True] * 4 + [False] * 3
                no = [False] * 7
                self.assertEqual(institution.enact(item, "closed_agenda", amendment,
                    favorite, four_yes, four_yes)["enacted_policy"], favorite)
                self.assertEqual(institution.enact(item, "open_amendment", amendment,
                    favorite, four_yes, four_yes)["enacted_policy"], "C")
                self.assertEqual(institution.enact(item, "citizen_veto", amendment,
                    favorite, four_yes, four_yes)["enacted_policy"], "q")
                self.assertEqual(institution.enact(item, "open_amendment", amendment,
                    favorite, no, four_yes)["enacted_policy"], favorite)

    def test_episode_has_seventeen_real_actions_and_person_level_scores(self):
        item = self.aligned
        favorite = item["favorite"]
        def ask(actor, stage, messages, index):
            self.assertEqual(index, len(calls))
            self.assertEqual(len(messages), 2)
            calls.append((actor, stage))
            if stage in ("draft", "final"):
                return json.dumps({"policy": favorite, "message": ""})
            if stage == "amendment":
                return json.dumps({"policy": "C", "message": ""})
            if stage == "response":
                return json.dumps({"support": True,
                                   "preferred_policy": "C", "message": ""})
            return json.dumps({"amendment": True, "final": True})
        calls = []
        result = institution.episode(item, "open_amendment", ask)
        self.assertEqual(result["calls"], 17)
        self.assertEqual(len(calls), 17)
        self.assertEqual(result["outcome"]["enacted_policy"], "C")
        self.assertEqual(len(result["outcome"]["enacted_district_utility"]), 7)
        self.assertEqual(len(result["outcome"]["enacted_citizen_utility"]), 63)
        self.assertEqual(result["outcome"]["controller_changed_actions"], 0)

    def test_parser_rejects_extra_fields_types_duplicate_keys_and_prose(self):
        bad = [('{"amendment":true,"final":true,"reason":"x"}', "vote"),
               ('{"amendment":1,"final":false}', "vote"),
               ('{"policy":"X","policy":"C","message":""}', "final"),
               ('Here is {"policy":"X","message":""}', "final")]
        for raw, stage in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                institution.parse_action(raw, stage)

    def test_institution_prompts_keep_utility_data_equal_across_arms(self):
        prompts = [institution.messages(self.aligned, arm,
                   self.aligned["profile"]["proposer"], "draft", [])
                   for arm in institution.ARMS]
        self.assertEqual(len({m[1]["content"] for m in prompts}), 1)
        self.assertEqual(len({m[0]["content"] for m in prompts}), 3)
