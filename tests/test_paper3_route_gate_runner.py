"""Offline candidate runner checks; no prepare, API request or budget mutation."""
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
import threading
import time
import unittest
from unittest import mock
import zipfile

from experiments import paper3_route_gate as runner


def metadata():
    return dict(data=dict(id=runner.requests.MODEL, endpoints=[dict(
        tag=runner.requests.PROVIDER_TAG, provider_name="Darkbloom",
        model_id=runner.requests.MODEL, quantization="fp4", status=0,
        max_completion_tokens=32768, context_length=262144,
        supported_parameters=["reasoning", "max_tokens", "temperature", "top_p", "top_k",
                              "seed", "presence_penalty", "repetition_penalty",
                              "response_format", "structured_outputs"],
        pricing=dict(prompt="0.00000008", completion="0.00000075"))]))


class RouteGateRunnerTests(unittest.TestCase):
    SECRET = "fabricated" + "-secret"
    def test_request_inventory_and_canonical_hash(self):
        cases = runner.cases()
        self.assertEqual(len(cases), 12)
        self.assertEqual(len({c["id"] for c in cases}), 12)
        self.assertLess(sum(Decimal(c["reserved_usd"]) for c in cases), runner.CAP)
        for c in cases:
            self.assertEqual(c["request_text"], runner.t.canonical(c["request"]))
            self.assertEqual(c["request_sha256"], runner.t.sha(c["request_text"].encode()))
            self.assertLessEqual(c["input_token_bound"], runner.requests.INPUT_BOUND)

    def test_endpoint_identity_parameters_and_price_ceiling(self):
        good = metadata()
        self.assertEqual(runner.check_endpoint(good)["tag"], runner.requests.PROVIDER_TAG)
        bad = deepcopy(good)
        bad["data"]["endpoints"][0]["provider_name"] = "Other"
        with self.assertRaisesRegex(ValueError, "identity"):
            runner.check_endpoint(bad)
        bad = deepcopy(good)
        bad["data"]["endpoints"][0]["pricing"]["completion"] = "0.000001"
        with self.assertRaisesRegex(ValueError, "price"):
            runner.check_endpoint(bad)
        bad = deepcopy(good)
        bad["data"]["endpoints"][0]["supported_parameters"].remove("reasoning")
        with self.assertRaisesRegex(ValueError, "parameter"):
            runner.check_endpoint(bad)

    def test_score_requires_native_exact_content(self):
        case = runner.cases()[0]
        row = dict(assessment=True, request=case["request"],
                   final_content=json.dumps(case["context"]["expected"]))
        assessed = dict(passed=True, stream=dict(finish_reasons=["stop"]))
        with mock.patch.object(runner.service, "assess", return_value=assessed), \
             mock.patch.object(runner.service, "native_evidence", return_value=dict(present=True)):
            self.assertTrue(runner.score(row, case)["exact"])
            row["final_content"] = '{"outcome":"q","review_binding":true,"own_best_policy":"q"}'
            self.assertFalse(runner.score(row, case)["exact"])
        with mock.patch.object(runner.service, "assess", return_value=assessed), \
             mock.patch.object(runner.service, "native_evidence", return_value=dict(present=False)):
            self.assertFalse(runner.score(row, case)["usable"])

    def test_specification_is_strict_and_seed_scan_has_no_overlap(self):
        spec = runner.specification()
        self.assertEqual(spec["max_calls"], 12)
        self.assertEqual(spec["cap_usd"], "0.15")
        self.assertEqual(spec["inference_retries"], 0)
        audit = runner.seed_audit()
        self.assertEqual(audit["planned"], list(range(362000, 362012)))
        self.assertEqual(audit["overlap"], [])

    def test_source_closure_includes_new_instrument_and_shared_billing_code(self):
        paths = runner.closure(runner.ROOT, [
            runner.ROOT / "experiments/paper3_route_gate.py",
            runner.ROOT / "tests/test_paper3_route_gate_runner.py",
            runner.BUDGET / "authority.json",
        ])
        relatives = {str(p.relative_to(runner.ROOT)) for p in paths}
        self.assertIn("experiments/paper3_route_gate.py", relatives)
        self.assertIn("paper3/route_jurisdiction_requests.py", relatives)
        self.assertIn("paper3/route_jurisdiction_gate.py", relatives)
        self.assertIn("paper3/hosted_reasoning_channel_calls.py", relatives)
        self.assertIn("paper3/pivot_b_budget.py", relatives)

    def _prepared(self, temporary):
        class Public:
            def open(self, url, timeout):
                self_url = runner.METADATA_URL
                assert url == self_url
                return io.BytesIO(json.dumps(metadata()).encode())

        root = Path(temporary) / "run"
        planned = dict(planned=list(range(362000, 362012)), overlap=[],
                       historical_files=0, inventory_sha256="0" * 64)
        with mock.patch.object(runner.t, "opener", return_value=Public()), \
             mock.patch.object(runner, "seed_audit", return_value=planned):
            runner.prepare(root)
        budget = Path(temporary) / "budget"
        shutil.copytree(runner.BUDGET, budget)
        return root, budget

    @staticmethod
    def _trace(answer, generation, *, native=True):
        reasoning = "fabricated reasoning" if native else ""
        frames = [dict(id=generation, model=runner.CONFIG["models"][1],
                       provider=runner.CONFIG["provider"],
                       choices=[dict(index=0, delta=dict(reasoning=reasoning), finish_reason=None)]),
                  dict(choices=[dict(index=0, delta=dict(content=answer), finish_reason="stop")]),
                  dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100,
                                             cost=.0001,
                                             completion_tokens_details=dict(reasoning_tokens=80)))]
        lines = []
        for frame in frames:
            lines.extend(["data: " + json.dumps(frame), ""])
        lines.extend(["data: [DONE]", ""])
        return dict(started_unix=time.time(), ended_unix=time.time(), http_status=200,
                    generation_header=None, lines=lines, line_count=len(lines),
                    byte_count=sum(map(len, lines)), error_type=None, secret_redacted=False)

    def _fabricated_execute(self, root, budget, *, wrong=False, no_reasoning=False,
                            http400=False):
        contexts = {c["request"]["seed"]: c["context"] for c in runner.cases()}
        lock, requested = threading.Lock(), []

        def send(wire, secret):
            request = json.loads(wire)
            context = contexts[request["seed"]]
            with lock:
                requested.append(request)
                generation = "fabricated-" + str(len(requested))
            if http400:
                return dict(started_unix=time.time(), ended_unix=time.time(), http_status=400,
                            generation_header=None, lines=[], line_count=0, byte_count=0,
                            error_type="HTTPError", secret_redacted=False,
                            http_error_body="fabricated unsupported schema")
            answer = dict(context["expected"])
            if context["name"] == "action-offer":
                answer["route"] = "floor"
            if wrong and context["name"] == "rule-00":
                answer["outcome"] = "q"
            return self._trace(json.dumps(answer), generation, native=not no_reasoning)

        def lookup(generation, secret):
            return dict(http_status=200, error_type=None, secret_redacted=False,
                        started_unix=time.time(), ended_unix=time.time(),
                        data=dict(id=generation, model=runner.CONFIG["models"][1],
                                  provider_name=runner.CONFIG["provider"], total_cost=.0001))

        with redirect_stdout(io.StringIO()):
            terminal = runner.execute(root, budget, secret=self.SECRET, send=send,
                                      lookup=lookup, sleep=lambda _: None)
        return terminal, requested

    def test_fabricated_success_audit_and_no_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, requests = self._fabricated_execute(root, budget)
            report = runner.audit(root, budget)
            self.assertEqual(len(requests), 12)
            self.assertTrue(report["gate_passed"])
            self.assertFalse(terminal["global_safety_stop"])
            self.assertEqual(Decimal(report["accounted_usd"]), Decimal("0.0012"))
            with self.assertRaisesRegex(ValueError, "already started"):
                runner.execute(root, budget, secret=self.SECRET,
                               send=lambda *a: None, lookup=lambda *a: None)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = runner.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([
                sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_route_gate.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)

    def test_no_reasoning_and_http400_fail_without_reissue(self):
        for mode in ("no_reasoning", "http400"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root, budget = self._prepared(temporary)
                terminal, requested = self._fabricated_execute(
                    root, budget, **{mode: True})
                report = runner.audit(root, budget)
                self.assertFalse(report["gate_passed"])
                self.assertTrue(terminal["global_safety_stop"])
                self.assertEqual(len(report["assignments"]), 12)
                self.assertGreater(len(requested), 0)
                self.assertEqual(len({r["seed"] for r in requested}), len(requested))

    def test_seed_collision_and_budget_baseline_change_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            historical = Path(temporary) / "results/paper3/old"
            historical.mkdir(parents=True)
            (historical / "manifest.json").write_text(json.dumps(dict(seed=362000)))
            with self.assertRaisesRegex(ValueError, "seed overlap"):
                runner.seed_audit(temporary)
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            from paper3.pivot_b_budget import Ledger
            ledger = Ledger(budget)
            ledger.allocate("fabricated_other", Decimal("1"))
            ledger.reserve("fabricated_other", "fabricated-other-case", Decimal("0.001"), "2" * 64)
            ledger.settle("fabricated-other-case", Decimal("0.001"), True, "3" * 64)
            with self.assertRaisesRegex(ValueError, "pre-stage accounting changed"):
                runner.execute(root, budget, secret=self.SECRET)
            self.assertFalse(list((root / "calls").glob("*.json")))

    def test_manifest_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            manifest = runner.t.load(root / "manifest.json")
            manifest["protocol"]["cases"][0]["request"]["reasoning"]["enabled"] = False
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                runner.verify(root)

    def test_fabricated_wrong_answer_stops_and_archives_all_assignments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, requests = self._fabricated_execute(root, budget, wrong=True)
            report = runner.audit(root, budget)
            self.assertFalse(report["gate_passed"])
            self.assertTrue(terminal["global_safety_stop"])
            self.assertEqual(len(report["assignments"]), 12)
            self.assertGreater(len(requests), 0)
            self.assertLessEqual(len(requests), 12)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = runner.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([
                sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_route_gate.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)


if __name__ == "__main__":
    unittest.main()
