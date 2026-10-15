"""Offline-only verification of the fresh action-only tool diagnostic."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from decimal import Decimal
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

from experiments import paper3_constituent_b_gptoss_action_gate as runner


def metadata():
    return dict(data=dict(id=runner.requests.MODEL, endpoints=[dict(
        tag=runner.requests.PROVIDER_TAG, provider_name=runner.requests.PROVIDER_NAME,
        model_id=runner.requests.MODEL, quantization="fp4", status=0,
        max_completion_tokens=16384, context_length=163840,
        supported_parameters=["reasoning", "max_tokens", "temperature", "top_p",
                              "top_k", "min_p", "seed", "presence_penalty",
                              "repetition_penalty", "tools", "tool_choice"],
        supports_tool_choice=dict(function=True),
        pricing=dict(prompt="0.00000003", completion="0.00000017"))]))


class ToolGateRunnerTests(unittest.TestCase):
    SECRET = "fabricated" + "-secret"

    def test_inventory_and_live_metadata_guards(self):
        cases = runner.cases()
        self.assertEqual(len(cases), 3)
        self.assertEqual(sum(Decimal(row["reserved_usd"]) for row in cases),
                         Decimal("0.00901692"))
        self.assertEqual({row["request"]["seed"] for row in cases},
                         set(range(runner.SEED_BASE, runner.SEED_BASE + 3)))
        for case in cases:
            self.assertEqual(case["request_text"], runner.t.canonical(case["request"]))
            self.assertEqual(case["request_sha256"],
                             runner.t.sha(case["request_text"].encode()))
            self.assertEqual(case["request"]["tool_choice"]["function"]["name"],
                             runner.requests.TOOL_NAME)
        self.assertEqual(runner.check_endpoint(metadata())["tag"],
                         runner.requests.PROVIDER_TAG)
        for mutation in (
            lambda row: row["supported_parameters"].remove("tools"),
            lambda row: row["supports_tool_choice"].update(function=False),
            lambda row: row["pricing"].update(completion="0.000001"),
            lambda row: row.update(status=-1),
        ):
            with self.subTest(mutation=mutation):
                bad = deepcopy(metadata())
                mutation(bad["data"]["endpoints"][0])
                with self.assertRaises(ValueError):
                    runner.check_endpoint(bad)

    def test_fresh_seeds_reject_historical_overlap(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = runner.seed_audit(temporary)
            self.assertEqual(plan["planned"], list(range(664000, 664003)))
            history = Path(temporary) / "results/paper3/old"
            history.mkdir(parents=True)
            (history / "manifest.json").write_text(json.dumps(dict(seed=664000)))
            with self.assertRaisesRegex(ValueError, "seed overlap"):
                runner.seed_audit(temporary)

    def _prepared(self, temporary):
        root = Path(temporary) / "run"
        budget = Path(temporary) / "budget"
        budget.mkdir()
        shutil.copy2(runner.BUDGET / "authority.json", budget / "authority.json")
        (budget / "entries").mkdir()
        (budget / "stages").mkdir()
        planned = dict(planned=list(range(664000, 664003)), overlap=[],
                       historical_files=0, inventory_sha256="0" * 64)
        with mock.patch.object(runner, "seed_audit", return_value=planned):
            runner.prepare(root, metadata=metadata(), ledger_root=budget)
        return root, budget

    @staticmethod
    def _trace(answer, generation, *, native=True, inconsistent_count=False,
               tool_name=runner.requests.TOOL_NAME):
        raw = json.dumps(answer, sort_keys=True)
        fragments = [raw[:10], raw[10:]]
        frames = [dict(id=generation, model=runner.CONFIG["models"][0],
                       provider=runner.CONFIG["provider"], choices=[dict(index=0,
                       delta=dict(reasoning="fabricated reasoning" if native else ""),
                       finish_reason=None)])]
        for index, part in enumerate(fragments):
            tool = dict(index=0, function=dict(arguments=part))
            if index == 0:
                tool.update(id="call_one", type="function")
                tool["function"]["name"] = tool_name
            frames.append(dict(choices=[dict(index=0,
                         delta=dict(tool_calls=[tool]), finish_reason=None)]))
        frames.append(dict(choices=[dict(index=0, delta={}, finish_reason="tool_calls")]))
        frames.append(dict(choices=[], usage=dict(prompt_tokens=100,
                       completion_tokens=100, cost=.0001,
                       completion_tokens_details=dict(
                           reasoning_tokens=(120 if inconsistent_count else 80)
                           if native else 0))))
        lines = [line for frame in frames for line in
                 ("data: " + json.dumps(frame), "")]
        lines += ["data: [DONE]", ""]
        return dict(started_unix=time.time(), ended_unix=time.time(), http_status=200,
                    generation_header=None, lines=lines, line_count=len(lines),
                    byte_count=sum(map(len, lines)), error_type=None,
                    secret_redacted=False)

    def _execute(self, root, budget, *, wrong=False, bad_name=False,
                 no_reasoning=False, inconsistent_count=False):
        cases = {case["request"]["seed"]: case for case in runner.cases()}
        sent = []

        def send(wire, secret):
            request = json.loads(wire)
            case = cases[request["seed"]]["context"]
            sent.append(request)
            if case["stage"] == "first_vote":
                answer = dict(vote=False)
            else:
                answer = dict(projects=dict(A="A0", B="B0"), first="A",
                              coalition=[0, 1, 3, 4], message="fabricated")
                if case["stage"] == "response":
                    answer["support"] = True
                if wrong and case["stage"] == "draft":
                    answer["coalition"] = [0, 1, 3]
            return self._trace(answer, "fabricated-" + str(len(sent)),
                               native=not no_reasoning,
                               inconsistent_count=inconsistent_count,
                               tool_name="wrong_tool" if bad_name else runner.requests.TOOL_NAME)

        def lookup(generation, secret):
            return dict(http_status=200, error_type=None, secret_redacted=False,
                        started_unix=time.time(), ended_unix=time.time(),
                        data=dict(id=generation, model=runner.CONFIG["models"][0],
                                  provider_name=runner.CONFIG["provider"],
                                  total_cost=.0001))

        with redirect_stdout(io.StringIO()):
            terminal = runner.execute(root, budget, secret=self.SECRET, send=send,
                                      lookup=lookup, sleep=lambda _: None)
        return terminal, sent

    def test_fabricated_success_exact_archive_replay_and_no_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._execute(root, budget)
            report = runner.audit(root, budget)
            self.assertEqual(len(sent), 3)
            self.assertTrue(report["gate_passed"])
            self.assertFalse(terminal["global_safety_stop"])
            self.assertEqual(Decimal(report["accounted_usd"]), Decimal("0.0003"))
            with self.assertRaisesRegex(ValueError, "already started"):
                runner.execute(root, budget, secret=self.SECRET)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = runner.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_constituent_b_gptoss_action_gate.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)

    def test_bad_answer_or_wrong_function_stops_and_retains_all_assignments(self):
        for mode in ("wrong", "bad_name", "no_reasoning"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root, budget = self._prepared(temporary)
                terminal, sent = self._execute(root, budget, **{mode: True})
                report = runner.audit(root, budget)
                self.assertFalse(report["gate_passed"])
                self.assertTrue(terminal["global_safety_stop"])
                self.assertEqual(len(report["assignments"]), 3)
                self.assertEqual(len(sent), 1)
                self.assertEqual(sum(row["status"] == "not_started"
                                     for row in report["assignments"]), 2)

    def test_nonempty_channel_suffices_despite_inconsistent_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            self._execute(root, budget, inconsistent_count=True)
            report = runner.audit(root, budget)
            self.assertTrue(report["gate_passed"])
            self.assertTrue(all(not row["result"]["native_reasoning"][
                "reported_count_consistent"] for row in report["assignments"]))

    def test_budget_change_and_manifest_tamper_are_rejected_before_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            from paper3.pivot_b_budget import Ledger
            ledger = Ledger(budget)
            ledger.allocate("fabricated_other", Decimal("1"))
            ledger.reserve("fabricated_other", "fabricated-other", Decimal("0.001"),
                           "2" * 64)
            ledger.settle("fabricated-other", Decimal("0.001"), True, "3" * 64)
            with self.assertRaisesRegex(ValueError, "pre-stage accounting changed"):
                runner.execute(root, budget, secret=self.SECRET)
            self.assertFalse(list((root / "calls").glob("*.json")))
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            manifest = runner.t.load(root / "manifest.json")
            manifest["protocol"]["cases"][0]["request"]["tool_choice"]["function"][
                "name"] = "other"
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                runner.verify(root)


if __name__ == "__main__":
    unittest.main()
