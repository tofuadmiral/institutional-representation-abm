"""Offline tests of the prospective, not-yet-approved tool action channel."""
from __future__ import annotations

import json
import unittest

from paper3 import constituent_b_gate as gate
from paper3 import constituent_b_requests as old
from paper3 import constituent_b_tool_interface as tool


def trace(fragments, *, name=tool.TOOL_NAME, ending="tool_calls", content=None):
    chunks = []
    for index, part in enumerate(fragments):
        delta = {"tool_calls": [dict(index=0,
            **({"id": "call_one", "type": "function"} if index == 0 else {}),
            function=dict(**({"name": name} if index == 0 else {}), arguments=part))]}
        if content is not None and index == 0:
            delta["content"] = content
        chunks.append({"choices": [{"index": 0, "delta": delta,
                                     "finish_reason": None}]})
    chunks.append({"choices": [{"index": 0, "delta": {},
                                 "finish_reason": ending}]})
    return {"lines": [item for frame in chunks for item in
                      ["data: " + json.dumps(frame), ""]] + ["data: [DONE]", ""]}


class ToolInterfaceTests(unittest.TestCase):
    def test_gate_requests_use_forced_single_function_not_json_text(self):
        for index, case in enumerate(gate.cases()):
            with self.subTest(case=case["name"]):
                request = tool.request(case["messages"], 650000 + index,
                                       kind=case["kind"], stage=case.get("stage"),
                                       name=case["name"])
                self.assertNotIn("response_format", request)
                self.assertEqual(request["tool_choice"]["function"]["name"], tool.TOOL_NAME)
                self.assertEqual(len(request["tools"]), 1)
                self.assertEqual(request["tools"][0]["function"]["parameters"],
                                 old.schema(case["kind"], case.get("stage"), case["name"]))
                self.assertEqual(request["provider"]["only"], [old.PROVIDER_TAG])
                self.assertEqual(request["reasoning"], dict(enabled=True, exclude=False))
                self.assertIn(tool.NEW_INSTRUCTION, request["messages"][0]["content"])
                self.assertNotIn(tool.OLD_INSTRUCTION, request["messages"][0]["content"])
                self.assertLessEqual(old.reservation(request)["input_token_bound"], old.INPUT_BOUND)

    def test_split_streamed_arguments_score_exact_without_parsing_prose(self):
        case = gate.cases()[1]
        raw = json.dumps(case["expected"])
        stream = trace([raw[:9], raw[9:32], raw[32:]],
                       content="```json\nnot the action\n```")
        self.assertEqual(tool.arguments(stream), case["expected"])
        self.assertEqual(tool.score(stream, case)["status"], "completed")
        self.assertTrue(tool.score(stream, case)["exact"])

    def test_actual_action_stages_keep_the_same_legal_action_parser(self):
        action_cases = [case for case in gate.cases() if case["kind"] == "action"]
        examples = {
            "draft": {"projects": {"A": "A0", "B": "B0"}, "first": "A",
                      "coalition": [0, 1, 3, 4], "message": "offer"},
            "response": {"projects": {"A": "A0", "B": "B0"}, "first": "A",
                         "coalition": [0, 1, 3, 4], "message": "counter",
                         "support": True},
            "first_vote": {"vote": True},
        }
        for case in action_cases:
            with self.subTest(stage=case["stage"]):
                action = examples[case["stage"]]
                self.assertEqual(tool.score(trace([json.dumps(action)]), case)["reply"],
                                 action)
                request = tool.request(case["messages"], 650100,
                                       kind="action", stage=case["stage"])
                self.assertNotIn("response_format", request)
                self.assertEqual(request["tools"][0]["function"]["parameters"],
                                 old.schema("action", case["stage"]))

    def test_wrong_answer_is_still_wrong(self):
        case = gate.cases()[1]
        wrong = dict(case["expected"], district_total_utility=0)
        self.assertFalse(tool.score(trace([json.dumps(wrong)]), case)["exact"])

    def test_no_tool_call_is_not_repaired_from_json_prose(self):
        raw = {"lines": ["data: " + json.dumps({"choices": [{"index": 0,
              "delta": {"content": json.dumps(gate.cases()[1]["expected"])},
              "finish_reason": "stop"}]}), "", "data: [DONE]", ""]}
        self.assertEqual(tool.score(raw, gate.cases()[1])["status"], "failed")

    def test_multiple_calls_bad_name_bad_finish_and_duplicate_keys_fail(self):
        valid = json.dumps(gate.cases()[1]["expected"])
        bad_cases = [trace([valid], name="other"), trace([valid], ending="stop"),
                     trace(['{"x":1,"x":2}'])]
        duplicate = trace([valid])
        frame = json.loads(duplicate["lines"][0][6:])
        frame["choices"][0]["delta"]["tool_calls"].append(
            dict(index=1, id="call_two", type="function",
                 function=dict(name=tool.TOOL_NAME, arguments=valid)))
        duplicate["lines"][0] = "data: " + json.dumps(frame)
        bad_cases.append(duplicate)
        for item in bad_cases:
            with self.subTest(lines=item["lines"][0][:100]):
                with self.assertRaises(ValueError):
                    tool.arguments(item)

    def test_fenced_json_in_tool_arguments_is_invalid(self):
        case = gate.cases()[1]
        raw = "```json\n" + json.dumps(case["expected"]) + "\n```"
        self.assertEqual(tool.score(trace([raw]), case)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
