import json
import unittest

from paper3 import direct_ratification as game
from paper3 import direct_ratification_design as design


class DirectRatificationTests(unittest.TestCase):
    def setUp(self):
        self.rows = design.preflight(905001)

    def test_exact_opportunity_and_role_rotation(self):
        a, b, support, aligned = self.rows
        self.assertEqual(a["profile"]["districts"], b["profile"]["districts"])
        self.assertNotEqual(a["profile"]["proposer"], b["profile"]["proposer"])
        for row in (a, b):
            p = row["profile"]
            view = design.opportunity(p)
            self.assertTrue(view["polls"]["C"]["approved"])
            self.assertFalse(view["polls"]["X"]["approved"])
            self.assertFalse(view["polls"]["Y"]["approved"])
            outsider = view["outsider_district"]
            self.assertEqual(view["district_totals"][outsider],
                             {"X": -63, "Y": -63, "C": 18})
            self.assertEqual(view["polls"]["X"]["yes_counts"][outsider], 0)
            self.assertEqual(sum(len(c) for c in p["districts"].values()), 63)
        self.assertEqual(design.opportunity(a["profile"])["proposer_best"], "X")
        self.assertEqual(design.opportunity(b["profile"])["proposer_best"], "Y")
        self.assertTrue(all(design.opportunity(support["profile"])["polls"][p]["approved"]
                            for p in game.POLICIES))
        self.assertEqual(design.opportunity(aligned["profile"])["proposer_best"], "C")

    def test_raw_preferences_and_same_information_within_arm(self):
        p = self.rows[0]["profile"]
        for arm in game.ARMS:
            messages = game.messages(p, arm, p["proposer"], "draft", [])
            self.assertEqual(len(messages), 2)
            record = json.loads(messages[1]["content"].split("\n", 1)[0])
            self.assertEqual(record["individual_citizen_preferences"], p["districts"])
            self.assertNotIn("district_totals", record)
            self.assertNotIn("poll", record)
            self.assertEqual(record["agenda_holder"], p["proposer"])
        self.assertNotEqual(game.ARM_RULES[game.ARMS[0]],
                            game.ARM_RULES[game.ARMS[1]])

    def test_action_validation(self):
        self.assertEqual(game.parse_action('{"policy":"X","message":"ok"}',
                                           "draft")["policy"], "X")
        for raw, stage in [(r'{"policy":"X","policy":"Y","message":""}', "final"),
                           (r'{"policy":"Z","message":""}', "draft"),
                           (r'{"support":1,"preferred_policy":"C","message":""}', "response"),
                           (r'{"vote":1}', "vote"),
                           (r'{"vote":true} trailing', "vote")]:
            with self.subTest(raw=raw), self.assertRaises((ValueError, json.JSONDecodeError)):
                game.parse_action(raw, stage)

    def test_mechanical_veto_does_not_count_as_agent_proposal_change(self):
        p = self.rows[0]["profile"]
        events = [dict(type="draft", actor=p["proposer"],
                       action={"policy": "X", "message": ""}),
                  dict(type="responses", responses=[]),
                  dict(type="final", actor=p["proposer"],
                       action={"policy": "X", "message": ""}),
                  dict(type="vote", requested=[True] * 7)]
        advisory = game.score(p, "advisory_poll", events)
        binding = game.score(p, "binding_ratification", events)
        self.assertEqual(advisory["final_policy"], binding["final_policy"])
        self.assertEqual(advisory["requested_ballots"], binding["requested_ballots"])
        self.assertEqual(advisory["enacted_policy"], "X")
        self.assertEqual(binding["enacted_policy"], "q")
        self.assertEqual(advisory["controller_changed_ballots"], 0)
        self.assertEqual(binding["controller_changed_ballots"], 0)
        self.assertEqual(sum(binding["final_proposal_citizen_utility"].values()),
                         binding["final_proposal_total_citizen_utility"])
        self.assertEqual(sum(binding["enacted_district_utility"].values()), 0)

    def test_scripted_full_episode_and_sealed_stages(self):
        p = self.rows[0]["profile"]
        seen = []

        def ask(actor, stage, messages, index):
            seen.append((actor, stage, index, messages))
            if stage in ("draft", "final"):
                return '{"policy":"C","message":"compromise"}'
            if stage == "response":
                return '{"support":true,"preferred_policy":"C","message":"yes"}'
            return '{"vote":true}'

        row = game.episode(p, "binding_ratification", ask)
        self.assertEqual(row["calls"], 16)
        self.assertEqual([stage for _, stage, _, _ in seen],
                         ["draft"] + ["response"] * 7 + ["final"] + ["vote"] * 7)
        self.assertEqual([i for _, _, i, _ in seen], list(range(16)))
        self.assertEqual(row["outcome"]["enacted_policy"], "C")
        self.assertEqual(row["outcome"]["enacted_total_citizen_utility"],
                         sum(row["outcome"]["enacted_citizen_utility"].values()))
        for _, stage, _, messages in seen:
            record = json.loads(messages[1]["content"].split("\n", 1)[0])
            event_types = [e["type"] for e in record["events"]]
            if stage == "response":
                self.assertEqual(event_types, ["draft"])
            if stage == "vote":
                self.assertEqual(event_types, ["draft", "responses", "final"])


if __name__ == "__main__":
    unittest.main()
