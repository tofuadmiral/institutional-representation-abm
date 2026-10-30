"""Entirely fabricated transport tests; no model or network calls."""
from contextlib import redirect_stdout
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

from experiments import paper3_constituent_b_gptoss_discovery as runner
from tests.test_paper3_constituent_b_gptoss_action_gate import metadata


class DiscoveryRunnerTests(unittest.TestCase):
    SECRET = "fabricated" + "-discovery-secret"

    @staticmethod
    def _prerequisite():
        def evidence(passed, calls):
            report = dict(protocol="f" * 64, gate_passed=passed, calls=calls)
            return dict(protocol="f" * 64, report=report,
                        report_sha256=runner.t.sha(runner.t.canonical(report).encode()))
        return dict(action=evidence(True, 3), factual=evidence(False, 10),
                    limitation="fabricated offline prerequisite")

    def _prepared(self, temporary):
        root, budget = Path(temporary) / "run", Path(temporary) / "budget"
        shutil.copytree(runner.BUDGET, budget)
        plan = dict(planned_unique=sorted({a["seed_base"] + i
                                          for a in runner.assignments() for i in range(30)}),
                    intended_calls=630, paired_across_arms=True, overlap=[],
                    historical_files=0, inventory_sha256="0" * 64)
        with mock.patch.object(runner, "prerequisite", return_value=self._prerequisite()), \
             mock.patch.object(runner, "prerequisite_paths", return_value=[]), \
             mock.patch.object(runner, "seed_audit", return_value=plan):
            runner.prepare(root, metadata=metadata())
        return root, budget

    @staticmethod
    def _trace(answer, generation, *, native=True):
        raw = json.dumps(answer, sort_keys=True)
        frames = [dict(id=generation, model=runner.CONFIG["models"][0],
                       provider=runner.CONFIG["provider"],
                       choices=[dict(index=0, delta=dict(
                           reasoning="fabricated reasoning" if native else ""),
                           finish_reason=None)])]
        for i, fragment in enumerate((raw[:10], raw[10:])):
            function = dict(arguments=fragment)
            call = dict(index=0, function=function)
            if i == 0:
                call.update(id="call_one", type="function")
                function["name"] = runner.requests.interface.TOOL_NAME
            frames.append(dict(choices=[dict(index=0, delta=dict(tool_calls=[call]),
                                             finish_reason=None)]))
        frames += [dict(choices=[dict(index=0, delta={}, finish_reason="tool_calls")]),
                   dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100,
                       cost=.0001,
                       completion_tokens_details=dict(reasoning_tokens=80 if native else 0)))]
        lines = [line for frame in frames for line in ("data: " + json.dumps(frame), "")]
        lines += ["data: [DONE]", ""]
        return dict(started_unix=time.time(), ended_unix=time.time(), http_status=200,
                    generation_header=None, lines=lines, line_count=len(lines),
                    byte_count=sum(map(len, lines)), error_type=None,
                    secret_redacted=False)

    def _execute(self, root, budget, *, bad_first=False):
        seen = []
        bases = {row["seed_base"] for row in runner.assignments()}

        def send(wire, secret):
            request = json.loads(wire)
            seen.append(request)
            base = max(value for value in bases if value <= request["seed"])
            index = request["seed"] - base
            if index <= 8:
                answer = dict(projects=dict(A="A0", B="B0"), first="A",
                              coalition=[0, 1, 3, 4], message="fabricated")
                if 1 <= index <= 7:
                    answer["support"] = True
            elif index <= 15:
                answer = dict(consent=True)
            else:
                answer = dict(vote=True)
            return self._trace(answer, "fabricated-" + str(len(seen)),
                               native=not (bad_first and len(seen) == 1))

        def lookup(generation, secret):
            return dict(http_status=200, error_type=None, secret_redacted=False,
                        started_unix=time.time(), ended_unix=time.time(),
                        data=dict(id=generation, model=runner.CONFIG["models"][0],
                                  provider_name=runner.CONFIG["provider"],
                                  total_cost=.0001))

        with mock.patch.object(runner, "prerequisite", return_value=self._prerequisite()), \
             redirect_stdout(io.StringIO()):
            terminal = runner.execute(root, budget, secret=self.SECRET, send=send,
                                      lookup=lookup, sleep=lambda _: None)
        return terminal, seen

    def test_request_preflight_and_cap(self):
        plan = runner.specification()["discovery_preflight"]
        self.assertEqual(plan["intended_calls"], 630)
        self.assertEqual(plan["distinct_request_seeds"], 210)
        self.assertLess(Decimal(plan["full_output_scripted_reservations_usd"]),
                        runner.CAP)
        self.assertLess(plan["max_input_bound"], runner.requests.INPUT_BOUND)
        self.assertEqual(len(runner.assignments()), 21)
        self.assertFalse(runner.prerequisite()["factual"]["report"]["gate_passed"])

    def test_fabricated_full_path_and_isolated_archive_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._execute(root, budget)
            report = runner.audit(root, budget)
            self.assertEqual(len(sent), 630)
            self.assertEqual(len({row["seed"] for row in sent}), 210)
            self.assertEqual(report["completed_episodes"], 21)
            self.assertEqual(report["readout"]["completed_profile_pairs"], 21)
            self.assertTrue(report["feasibility_passed"])
            self.assertFalse(terminal["global_safety_stop"])
            self.assertEqual(Decimal(report["accounted_usd"]), Decimal("0.063"))
            with mock.patch.object(runner, "prerequisite", return_value=self._prerequisite()), \
                 self.assertRaisesRegex(ValueError, "already started"):
                runner.execute(root, budget, secret=self.SECRET)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = runner.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_constituent_b_gptoss_discovery.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)

    def test_first_bad_action_stops_and_preserves_all_assignments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._execute(root, budget, bad_first=True)
            report = runner.audit(root, budget)
            self.assertEqual(len(sent), 1)
            self.assertTrue(terminal["global_safety_stop"])
            self.assertFalse(report["feasibility_passed"])
            self.assertEqual(len(report["assignments"]), 21)
            self.assertEqual(report["assignments"][0]["status"], "failed")
            self.assertEqual(sum(row["status"] == "not_started"
                                 for row in report["assignments"]), 20)
            self.assertEqual(report["readout"]["completed_profile_pairs"], 0)

    def test_source_and_budget_tamper_block_before_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            manifest = runner.t.load(root / "manifest.json")
            manifest["protocol"]["assignments"][0]["seed_base"] += 1
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                runner.verify(root)
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            from paper3.pivot_b_budget import Ledger
            ledger = Ledger(budget)
            ledger.allocate("fabricated_other", Decimal("1"))
            ledger.reserve("fabricated_other", "fabricated-other", Decimal("0.001"),
                           "2" * 64)
            ledger.settle("fabricated-other", Decimal("0.001"), True, "3" * 64)
            with mock.patch.object(runner, "prerequisite", return_value=self._prerequisite()), \
                 self.assertRaisesRegex(ValueError, "pre-stage accounting changed"):
                runner.execute(root, budget, secret=self.SECRET)
            self.assertFalse(list((root / "calls").glob("*.json")))


if __name__ == "__main__":
    unittest.main()
