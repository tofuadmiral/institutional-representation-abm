"""Offline Qwen constituent pilot tests: fabricated transport only."""
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

from experiments import paper3_constituent_b_qwen_discovery as pilot


def metadata():
    return dict(data=dict(id=pilot.gate.MODEL, endpoints=[dict(
        name="DeepInfra | " + pilot.gate.MODELS[1],
        tag=pilot.gate.TAG, provider_name=pilot.gate.PROVIDER,
        model_id=pilot.gate.MODEL, quantization="fp8", status=0,
        max_completion_tokens=16384, context_length=40960,
        uptime_last_30m=99.8, uptime_last_5m=100,
        supported_parameters=["reasoning", "max_tokens", "temperature", "top_p",
                              "top_k", "min_p", "seed", "presence_penalty",
                              "repetition_penalty", "response_format"],
        pricing=dict(prompt="0.00000008", completion="0.00000028"))]))


class QwenConstituentPilotTests(unittest.TestCase):
    SECRET = "fabricated" + "-qwen-constituent-secret"

    def _prepared(self, temporary):
        root, budget = Path(temporary) / "run", Path(temporary) / "budget"
        shutil.copytree(pilot.BUDGET, budget)
        plan = dict(planned_unique=sorted({a["seed_base"] + i
                                          for a in pilot.assignments() for i in range(30)}),
                    intended_calls=630, paired_across_arms=True, overlap=[],
                    historical_files=0, inventory_sha256="0" * 64)
        with mock.patch.object(pilot, "seed_audit", return_value=plan):
            pilot.prepare(root, metadata=metadata())
        return root, budget

    @staticmethod
    def _trace(answer, generation, *, http_error=False):
        if http_error:
            return dict(started_unix=time.time(), ended_unix=time.time(),
                        http_status=502, generation_header=None, lines=[],
                        line_count=0, byte_count=0, error_type="HTTPError",
                        secret_redacted=False)
        frames = [dict(id=generation, model=pilot.gate.MODEL,
                       provider=pilot.gate.PROVIDER,
                       choices=[dict(index=0, delta=dict(reasoning="fabricated reasoning"),
                                     finish_reason=None)]),
                  dict(choices=[dict(index=0, delta=dict(content=json.dumps(answer)),
                                     finish_reason="stop")]),
                  dict(choices=[], usage=dict(prompt_tokens=100,
                       completion_tokens=100, cost=.0001,
                       completion_tokens_details=dict(reasoning_tokens=80)))]
        lines = [line for frame in frames for line in ("data: " + json.dumps(frame), "")]
        lines += ["data: [DONE]", ""]
        return dict(started_unix=time.time(), ended_unix=time.time(),
                    http_status=200, generation_header=None, lines=lines,
                    line_count=len(lines), byte_count=sum(map(len, lines)),
                    error_type=None, secret_redacted=False)

    def _execute(self, root, budget, *, transport_failure=False, invalid_first=False):
        sent = []
        bases = {row["seed_base"] for row in pilot.assignments()}

        def send(wire, secret):
            request = json.loads(wire)
            sent.append(request)
            if transport_failure:
                return self._trace(None, "", http_error=True)
            base = max(value for value in bases if value <= request["seed"])
            index = request["seed"] - base
            if index <= 8:
                answer = dict(projects=dict(A="A0", B="B0"), first="A",
                              coalition=[0, 1, 3, 4], message="fabricated")
                if 1 <= index <= 7:
                    answer["support"] = True
                if invalid_first and len(sent) == 1:
                    answer["coalition"] = [0, 1, 3]
            elif index <= 15:
                answer = dict(consent=True)
            else:
                answer = dict(vote=True)
            return self._trace(answer, "fabricated-" + str(len(sent)))

        def lookup(generation, secret):
            return dict(http_status=200, error_type=None, secret_redacted=False,
                        started_unix=time.time(), ended_unix=time.time(),
                        data=dict(id=generation, model=pilot.gate.MODEL,
                                  provider_name=pilot.gate.PROVIDER,
                                  total_cost=.0001))

        with redirect_stdout(io.StringIO()):
            terminal = pilot.execute(root, budget, secret=self.SECRET, send=send,
                                     lookup=lookup, sleep=lambda _: None)
        return terminal, sent

    def test_preflight_prerequisite_seeds_and_uptime(self):
        preflight = pilot.specification()["scripted_preflight"]
        self.assertEqual(preflight["intended_calls"], 630)
        self.assertEqual(preflight["distinct_request_seeds"], 210)
        self.assertLess(Decimal(preflight["full_output_scripted_reservations_usd"]),
                        pilot.CAP)
        self.assertEqual(len(pilot.assignments()), 21)
        self.assertEqual(pilot.prerequisite()["protocol"], pilot.GATE_PROTOCOL)
        self.assertFalse(pilot.seed_audit()["overlap"])
        bad = metadata()
        bad["data"]["endpoints"][0]["uptime_last_5m"] = 50
        with self.assertRaisesRegex(ValueError, "uptime"):
            pilot.check_endpoint(bad)

    def test_fabricated_full_path_and_exact_archive_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._execute(root, budget)
            report = pilot.audit(root, budget)
            self.assertEqual(len(sent), 630)
            self.assertEqual(len({row["seed"] for row in sent}), 210)
            self.assertEqual(report["completed_episodes"], 21)
            self.assertEqual(report["readout"]["completed_profile_pairs"], 21)
            self.assertTrue(report["feasibility_passed"])
            self.assertFalse(terminal["global_safety_stop"])
            self.assertEqual(Decimal(report["accounted_usd"]), Decimal("0.063"))
            with self.assertRaisesRegex(ValueError, "already started"):
                pilot.execute(root, budget, secret=self.SECRET)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = pilot.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_constituent_b_qwen_discovery.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)

    def test_transport_failures_stop_globally_and_preserve_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._execute(root, budget, transport_failure=True)
            report = pilot.audit(root, budget)
            self.assertLessEqual(len(sent), 8)
            self.assertTrue(terminal["global_safety_stop"])
            self.assertFalse(report["feasibility_passed"])
            self.assertEqual(len(report["assignments"]), 21)
            self.assertEqual(report["readout"]["assigned_profile_pairs"], 21)

    def test_one_invalid_action_does_not_erase_other_games(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._execute(root, budget, invalid_first=True)
            report = pilot.audit(root, budget)
            self.assertFalse(terminal["global_safety_stop"])
            self.assertEqual(len(report["assignments"]), 21)
            self.assertEqual(report["completed_episodes"], 20)
            self.assertEqual(sum(x["status"] == "failed"
                                 for x in report["assignments"]), 1)
            self.assertEqual(len(sent), 601)
            self.assertEqual(report["readout"]["assigned_profile_pairs"], 21)
            self.assertEqual(report["readout"]["completed_profile_pairs"], 19)
            self.assertTrue(any(not pair["completed"] for profile in
                                report["readout"]["profiles"]
                                for pair in profile["pairwise"]))


if __name__ == "__main__":
    unittest.main()
