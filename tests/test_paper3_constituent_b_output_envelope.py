"""Offline boundary tests for a prospective formatting-tolerant instrument."""
from __future__ import annotations

import json
import unittest

from paper3 import constituent_b_gate as gate
from paper3 import constituent_b_output_envelope as envelope


class OutputEnvelopeTests(unittest.TestCase):
    def test_same_factual_score_for_bare_or_singly_fenced_object(self):
        case = gate.cases()[1]
        body = json.dumps(case["expected"])
        for candidate in (body, "\n " + body + " \n",
                          "```json\n" + body + "\n```",
                          "```JSON\r\n" + body + "\r\n```"):
            with self.subTest(candidate=candidate[:20]):
                self.assertEqual(envelope.score(candidate, case), gate.score(body, case))

    def test_fence_does_not_repair_wrong_answer(self):
        case = gate.cases()[1]
        wrong = dict(case["expected"], district_total_utility=0)
        result = envelope.score("```json\n" + json.dumps(wrong) + "\n```", case)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["exact"])

    def test_malformed_ambiguous_or_prose_responses_fail(self):
        case = gate.cases()[1]
        body = json.dumps(case["expected"])
        candidates = ("", "answer: " + body, body + " thanks",
                      "```json\n" + body + "\n```\nextra",
                      "```json\n" + body + "\n```\n```json\n" + body + "\n```",
                      "```python\n" + body + "\n```",
                      "```json\n{" + "bad" + "}\n```", None)
        for candidate in candidates:
            with self.subTest(candidate=repr(candidate)[:50]):
                self.assertEqual(envelope.score(candidate, case)["status"], "failed")

    def test_duplicate_keys_and_nonfinite_numbers_still_fail(self):
        case = gate.cases()[1]
        for body in ('{"district_total_utility":1,"district_total_utility":2}',
                     '{"district_total_utility":NaN}'):
            with self.subTest(body=body):
                self.assertEqual(envelope.score("```json\n" + body + "\n```", case)[
                    "status"], "failed")

    def test_action_validation_is_unchanged(self):
        case = next(item for item in gate.cases() if item.get("stage") == "first_vote")
        self.assertEqual(envelope.score('```json\n{"vote":true}\n```', case),
                         gate.score('{"vote":true}', case))
        self.assertEqual(envelope.score('```json\n{"vote":"true"}\n```', case)[
            "status"], "failed")


if __name__ == "__main__":
    unittest.main()
