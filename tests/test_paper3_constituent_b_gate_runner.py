"""Offline-only tests for the unapproved constituent-mandate B gate."""
from copy import deepcopy
from decimal import Decimal
from contextlib import redirect_stdout
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

from experiments import paper3_constituent_b_gate as runner


def metadata():
    return dict(data=dict(id=runner.requests.MODEL, endpoints=[dict(
        tag=runner.requests.PROVIDER_TAG, provider_name=runner.requests.PROVIDER_NAME,
        model_id=runner.requests.MODEL, quantization="fp4", status=0,
        max_completion_tokens=16384, context_length=163840,
        supported_parameters=["reasoning", "max_tokens", "temperature", "top_p",
                              "top_k", "min_p", "seed", "presence_penalty",
                              "repetition_penalty", "response_format", "structured_outputs"],
        pricing=dict(prompt="0.00000026", completion="0.00000038"))]))


class ConstituentGateRunnerTests(unittest.TestCase):
    SECRET = "fabricated" + "-secret"

    def test_inventory_bounds_and_request_hashes(self):
        cases = runner.cases()
        self.assertEqual(len(cases), 12)
        self.assertEqual(len({case["id"] for case in cases}), 12)
        self.assertEqual(sum(Decimal(case["reserved_usd"]) for case in cases),
                         Decimal("0.09514616"))
        for case in cases:
            self.assertEqual(case["request_text"], runner.t.canonical(case["request"]))
            self.assertEqual(case["request_sha256"], runner.t.sha(case["request_text"].encode()))
            self.assertLessEqual(case["input_token_bound"], runner.requests.INPUT_BOUND)
        self.assertLess(sum(Decimal(case["reserved_usd"]) for case in cases), runner.CAP)

    def test_endpoint_identity_feature_and_price_guards(self):
        good = metadata()
        self.assertEqual(runner.check_endpoint(good)["tag"], runner.requests.PROVIDER_TAG)
        for mutation, error in (
            (lambda row: row.update(provider_name="Other"), "identity"),
            (lambda row: row["supported_parameters"].remove("reasoning"), "parameter"),
            (lambda row: row["supported_parameters"].remove("min_p"), "parameter"),
            (lambda row: row["pricing"].update(completion="0.000001"), "price"),
            (lambda row: row.update(status=-2), "identity"),
            (lambda row: row.update(max_completion_tokens=8192), "capacity"),
        ):
            with self.subTest(error=error):
                bad = deepcopy(good)
                mutation(bad["data"]["endpoints"][0])
                with self.assertRaisesRegex(ValueError, error):
                    runner.check_endpoint(bad)

    def test_exact_factual_score_and_native_reasoning(self):
        case = runner.cases()[0]
        expected = case["context"]["expected"]
        row = dict(assessment=True, request=case["request"],
                   final_content=json.dumps(expected))
        assessment = dict(passed=True, stream=dict(finish_reasons=["stop"]))
        with mock.patch.object(runner.service, "assess", return_value=assessment), \
             mock.patch.object(runner.service, "native_evidence", return_value=dict(present=True)):
            self.assertTrue(runner.score(row, case)["exact"])
            changed = dict(expected)
            changed["district_total_utility"] += 1
            row["final_content"] = json.dumps(changed)
            self.assertFalse(runner.score(row, case)["exact"])
            row["final_content"] = json.dumps(expected)
            row["request"] = dict(case["request"], reasoning=dict(enabled=False))
            self.assertFalse(runner.score(row, case)["usable"])
        row["request"] = case["request"]
        with mock.patch.object(runner.service, "assess", return_value=assessment), \
             mock.patch.object(runner.service, "native_evidence", return_value=dict(present=False)):
            self.assertFalse(runner.score(row, case)["usable"])

    def test_seed_scan_includes_conditional_pilot_and_rejects_collision(self):
        plan = runner.seed_audit()
        self.assertEqual(plan["gate"], list(range(641900, 641912)))
        # Three institutional arms share each profile's 30 seeds for pairing.
        self.assertEqual(len(plan["discovery_unique"]), 120)
        self.assertFalse(plan["overlap"])
        with tempfile.TemporaryDirectory() as temporary:
            history = Path(temporary) / "results/paper3/old"
            history.mkdir(parents=True)
            (history / "manifest.json").write_text(json.dumps(dict(seed=641900)))
            with self.assertRaisesRegex(ValueError, "historical seed overlap"):
                runner.seed_audit(temporary)

    def _prepared(self, temporary):
        root = Path(temporary) / "run"
        plan = dict(gate=list(range(641900, 641912)),
                    discovery_unique=sorted({case["seed_base"] + i
                                             for case in runner.requests.discovery_assignments()
                                             for i in range(30)}),
                    overlap=[], historical_files=0, inventory_sha256="0" * 64)
        with mock.patch.object(runner, "seed_audit", return_value=plan):
            runner.prepare(root, metadata=metadata())
        budget = Path(temporary) / "budget"
        shutil.copytree(runner.BUDGET, budget)
        return root, budget

    @staticmethod
    def _trace(answer, generation, *, native=True):
        frames = [dict(id=generation, model=runner.CONFIG["models"][0],
                       provider=runner.CONFIG["provider"],
                       choices=[dict(index=0, delta=dict(reasoning="fabricated reasoning" if native else ""),
                                     finish_reason=None)]),
                  dict(choices=[dict(index=0, delta=dict(content=answer), finish_reason="stop")]),
                  dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100,
                                             cost=.0001,
                                             completion_tokens_details=dict(reasoning_tokens=80 if native else 0)))]
        lines = [item for frame in frames for item in ("data: " + json.dumps(frame), "")]
        lines.extend(["data: [DONE]", ""])
        return dict(started_unix=time.time(), ended_unix=time.time(), http_status=200,
                    generation_header=None, lines=lines, line_count=len(lines),
                    byte_count=sum(map(len, lines)), error_type=None, secret_redacted=False)

    def _fabricated_execute(self, root, budget, *, wrong=False, no_reasoning=False,
                            http400=False):
        cases = {case["request"]["seed"]: case for case in runner.cases()}
        requested = []

        def send(wire, secret):
            request = json.loads(wire)
            case = cases[request["seed"]]["context"]
            requested.append(request)
            if http400:
                return dict(started_unix=time.time(), ended_unix=time.time(), http_status=400,
                            generation_header=None, lines=[], line_count=0, byte_count=0,
                            error_type="HTTPError", secret_redacted=False,
                            http_error_body="fabricated unsupported schema")
            if case["kind"] == "fact":
                answer = dict(case["expected"])
                if wrong and case["name"] == "mandate-00":
                    answer["district_total_utility"] += 1
            elif case["stage"] == "first_vote":
                answer = dict(vote=False)
            else:
                answer = dict(projects=dict(A="A0", B="B0"), first="A",
                              coalition=[0, 1, 3, 4], message="fabricated")
                if case["stage"] == "response":
                    answer["support"] = True
            return self._trace(json.dumps(answer), "fabricated-" + str(len(requested)),
                               native=not no_reasoning)

        def lookup(generation, secret):
            return dict(http_status=200, error_type=None, secret_redacted=False,
                        started_unix=time.time(), ended_unix=time.time(),
                        data=dict(id=generation, model=runner.CONFIG["models"][0],
                                  provider_name=runner.CONFIG["provider"], total_cost=.0001))

        with redirect_stdout(io.StringIO()):
            terminal = runner.execute(root, budget, secret=self.SECRET, send=send,
                                      lookup=lookup, sleep=lambda _: None)
        return terminal, requested

    def test_success_archive_replay_and_no_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, requests = self._fabricated_execute(root, budget)
            report = runner.audit(root, budget)
            self.assertEqual(len(requests), 12)
            self.assertTrue(report["gate_passed"])
            self.assertFalse(terminal["global_safety_stop"])
            self.assertEqual(Decimal(report["accounted_usd"]), Decimal("0.0012"))
            with self.assertRaisesRegex(ValueError, "already started"):
                runner.execute(root, budget, secret=self.SECRET)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = runner.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_constituent_b_gate.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)

    def test_bad_content_or_transport_stops_without_reissue_and_keeps_assignments(self):
        for mode in ("wrong", "no_reasoning", "http400"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root, budget = self._prepared(temporary)
                terminal, requested = self._fabricated_execute(root, budget, **{mode: True})
                report = runner.audit(root, budget)
                self.assertFalse(report["gate_passed"])
                self.assertTrue(terminal["global_safety_stop"])
                self.assertEqual(len(report["assignments"]), 12)
                self.assertEqual(len(requested), 1)
                self.assertEqual(len({request["seed"] for request in requested}), 1)
                self.assertEqual(sum(row["status"] == "not_started"
                                     for row in report["assignments"]), 11)

    def test_budget_change_and_source_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            from paper3.pivot_b_budget import Ledger
            ledger = Ledger(budget)
            ledger.allocate("fabricated_other", Decimal("1"))
            ledger.reserve("fabricated_other", "fabricated-other", Decimal("0.001"), "2" * 64)
            ledger.settle("fabricated-other", Decimal("0.001"), True, "3" * 64)
            with self.assertRaisesRegex(ValueError, "pre-stage accounting changed"):
                runner.execute(root, budget, secret=self.SECRET)
            self.assertFalse(list((root / "calls").glob("*.json")))
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            manifest = runner.t.load(root / "manifest.json")
            manifest["protocol"]["cases"][0]["request"]["reasoning"]["enabled"] = False
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                runner.verify(root)


if __name__ == "__main__":
    unittest.main()
