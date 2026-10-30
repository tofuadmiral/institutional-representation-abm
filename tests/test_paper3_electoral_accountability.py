"""Offline controller tests only; no model calls or election inference."""
import json
import unittest

from paper3 import electoral_accountability as election


def profile(focal_values=(-2, -2, -2, -2, -2, 8, 8, 8, 8)):
    districts = {}
    for actor in election.ACTORS:
        values = (2,) * 9 if actor < 3 else ((-2,) * 9 if actor > 3 else focal_values)
        districts[f"r{actor}"] = [dict(id=f"c{actor}-{index}", p=value)
                                for index, value in enumerate(values)]
    return dict(id="synthetic-conflict", focal=3,
                districts=districts, office_bonus=30)


def scripted(consents, requested):
    def ask(actor, stage, messages, index):
        order = [i for i in election.ACTORS if i != 3] + [3]
        assert index == (order.index(actor) if stage == "consent" else actor + 7)
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        key = "consent" if stage == "consent" else "vote"
        return json.dumps({key: (consents if stage == "consent" else requested)[actor]})
    return ask


class ElectionControllerTests(unittest.TestCase):
    def test_requested_record_can_hide_executed_pivotal_yes(self):
        consent = [True, True, True, True, False, False, False]
        requested = [True, True, True, False, False, False, False]
        result = election.episode(profile(), "binding_requested_record",
                                  scripted(consent, requested))
        outcome = result["outcome"]
        self.assertEqual(result["calls"], 14)
        self.assertTrue(outcome["contract_active"])
        self.assertEqual(outcome["controller_changed_ballots"], 1)
        self.assertEqual(outcome["enacted_policy"], "P")
        self.assertEqual(outcome["district_outcomes"]["r3"], 22)
        self.assertEqual(outcome["representative_payoffs"]["r3"], 52)
        self.assertEqual(sum(outcome["citizen_election_ballots"]["r3"].values()), 5)
        self.assertTrue(outcome["retained"]["r3"])
        self.assertEqual(len(outcome["citizen_outcomes"]), 63)
        self.assertEqual(sum(len(v) for v in outcome["citizen_election_ballots"].values()), 63)

    def test_executed_record_exposes_same_enacted_yes(self):
        consent = [True, True, True, True, False, False, False]
        requested = [True, True, True, False, False, False, False]
        result = election.episode(profile(), "binding_executed_record",
                                  scripted(consent, requested))
        outcome = result["outcome"]
        self.assertEqual(outcome["enacted_policy"], "P")
        self.assertEqual(outcome["representative_payoffs"]["r3"], 22)
        self.assertEqual(sum(outcome["citizen_election_ballots"]["r3"].values()), 4)
        self.assertFalse(outcome["retained"]["r3"])

    def test_refusal_changes_policy_before_election_not_just_tally(self):
        consent = [True, True, True, False, False, False, False]
        requested = [True, True, True, False, False, False, False]
        result = election.episode(profile(), "binding_executed_record",
                                  scripted(consent, requested))
        outcome = result["outcome"]
        self.assertFalse(outcome["contract_active"])
        self.assertEqual(outcome["enacted_policy"], "q")
        self.assertEqual(outcome["representative_payoffs"]["r3"], 30)
        self.assertTrue(outcome["retained"]["r3"])

    def test_promise_cannot_enforce_hidden_yes(self):
        consent = [True, True, True, True, False, False, False]
        requested = [True, True, True, False, False, False, False]
        for arm in ("promise_requested_record", "promise_executed_record"):
            with self.subTest(arm=arm):
                outcome = election.episode(profile(), arm,
                                           scripted(consent, requested))["outcome"]
                self.assertEqual(outcome["controller_changed_ballots"], 0)
                self.assertEqual(outcome["enacted_policy"], "q")

    def test_action_projection_is_prospective_and_discrete(self):
        self.assertEqual(election.parse_action('{"vote":true,"reason":"x"}', "vote"),
                         {"vote": True})
        self.assertEqual(election.parse_action('```json\n{"consent":true}\n```',
                                               "consent"), {"consent": True})
        projected = election.parse_action(json.dumps(
            {"consent": True, "message": "a" * 1500}), "consent")
        self.assertEqual(projected, {"consent": True})
        for raw in ('{"vote":true,"vote":false}', '{"vote":"yes"}',
                    'The answer is {"vote":true}', '{}',
                    '```json\n{"vote":true}\n```\nmore'):
            with self.subTest(raw=raw), self.assertRaises((ValueError, json.JSONDecodeError)):
                election.parse_action(raw, "vote")

    def test_sealed_round_prompt_and_role_invariants(self):
        item = profile()
        first = election.messages(item, "binding_requested_record", 0,
                                  "consent", [])
        self.assertIn("REQUESTED ballot", first[0]["content"])
        self.assertIn('"r3":22', first[1]["content"])
        early = dict(type="early_consents",
                     consents={f"r{i}": True for i in election.ACTORS if i != 3})
        focal = election.messages(item, "binding_requested_record", 3,
                                  "consent", [early])
        self.assertIn('"early_consents"', focal[1]["content"])
        consents = dict(type="consent", consents=[True] * 7)
        second = election.messages(item, "binding_executed_record", 3,
                                   "vote", [early, consents])
        self.assertIn("EXECUTED ballot", second[0]["content"])
        self.assertIn('"contract_active":true', second[1]["content"])
        with self.assertRaises(ValueError):
            election.messages(item, "binding_requested_record", 3,
                              "vote", [])


if __name__ == "__main__":
    unittest.main()
