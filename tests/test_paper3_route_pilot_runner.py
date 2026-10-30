"""Offline candidate pilot execution; every model answer here is fabricated."""
from contextlib import redirect_stdout
from decimal import Decimal
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

from experiments import paper3_route_pilot as pilot


def metadata():
    return dict(data=dict(id=pilot.requests.MODEL, endpoints=[dict(
        tag=pilot.requests.PROVIDER_TAG, provider_name="Darkbloom",
        model_id=pilot.requests.MODEL, quantization="fp4", status=0,
        max_completion_tokens=32768, context_length=262144,
        supported_parameters=["reasoning", "max_tokens", "temperature", "top_p", "top_k",
                              "seed", "presence_penalty", "repetition_penalty",
                              "response_format", "structured_outputs"],
        pricing=dict(prompt="0.00000008", completion="0.00000075"))]))


class RoutePilotRunnerTests(unittest.TestCase):
    SECRET = "fabricated" + "-pilot-secret"

    @staticmethod
    def _fake_prerequisite():
        protocol = "f" * 64
        report = dict(protocol=protocol, gate_passed=True, calls=12)
        return dict(protocol=protocol, report=report,
                    report_sha256=pilot.t.sha(pilot.t.canonical(report).encode()),
                    action_request_template=pilot.requests.request([], 0, kind="action", stage="offer"),
                    limitation="fabricated gate for offline test only")

    def _prepared(self, temporary):
        class Public:
            def open(self, url, timeout):
                assert url == pilot.gate_runner.METADATA_URL
                return io.BytesIO(json.dumps(metadata()).encode())

        planned = sorted({a["seed_base"] + j for a in pilot.schedule() for j in range(16)})
        seed_audit = dict(planned=planned, overlap=[], historical_files=0,
                          inventory_sha256="0" * 64, pairing="fabricated offline")
        root = Path(temporary) / "run"
        with mock.patch.object(pilot, "prerequisite", return_value=self._fake_prerequisite()), \
             mock.patch.object(pilot, "prerequisite_paths", return_value=[]), \
             mock.patch.object(pilot, "seed_audit", return_value=seed_audit), \
             mock.patch.object(pilot.t, "opener", return_value=Public()):
            pilot.prepare(root)
        budget = Path(temporary) / "budget"
        shutil.copytree(pilot.BUDGET, budget)
        return root, budget

    @staticmethod
    def _trace(answer, generation):
        frames = [dict(id=generation, model=pilot.CONFIG["models"][1],
                       provider=pilot.CONFIG["provider"],
                       choices=[dict(index=0, delta=dict(reasoning="fabricated reasoning"),
                                     finish_reason=None)]),
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

    def _fabricated_execute(self, root, budget, *, first_bad=False):
        sent, lock = [], threading.Lock()

        def send(wire, secret):
            request = json.loads(wire)
            context = json.loads(request["messages"][1]["content"].split("\n", 1)[0])
            stage = context["stage"]
            with lock:
                sent.append(request)
                generation = "fabricated-" + str(len(sent))
                bad = first_bad and len(sent) == 1
            if bad:
                answer = "not JSON"
            elif stage == "recommendation":
                answer = '{"policy_id":"p0"}'
            elif stage == "offer":
                answer = '{"policy_id":"p0","route":"floor"}'
            elif stage == "ballot":
                actor = context["acting_for"]
                answer = json.dumps(dict(yes=context["utilities"][actor]["p0"] > 0))
            else:
                reviewer = context["reviewer"]
                answer = json.dumps(dict(approve=context["utilities"][reviewer]["p0"] > 0))
            return self._trace(answer, generation)

        def lookup(generation, secret):
            return dict(http_status=200, error_type=None, secret_redacted=False,
                        started_unix=time.time(), ended_unix=time.time(),
                        data=dict(id=generation, model=pilot.CONFIG["models"][1],
                                  provider_name=pilot.CONFIG["provider"], total_cost=.0001))

        with mock.patch.object(pilot, "prerequisite", return_value=self._fake_prerequisite()), \
             redirect_stdout(io.StringIO()):
            terminal = pilot.execute(root, budget, secret=self.SECRET,
                                     send=send, lookup=lookup, sleep=lambda _: None)
        return terminal, sent

    def test_schedule_bounds_and_case_identity(self):
        rows = pilot.schedule()
        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(x["intended_calls"] for x in rows), 128)
        self.assertEqual({x["arm"] for x in rows}, set(pilot.game.ARMS))
        p = rows[0]["profile"]
        messages = pilot.game.messages(p, rows[0]["arm"], p["actors"][0], "recommendation")
        case = pilot.make_case(rows[0], p["actors"][0], "recommendation", messages, 0)
        self.assertEqual(case["request"]["seed"], rows[0]["seed_base"])
        self.assertEqual(case["request_sha256"], pilot.t.sha(case["request_text"].encode()))
        self.assertLess(Decimal(case["reserved_usd"]), Decimal("0.01"))

    def test_seed_scan_and_no_overlap(self):
        audit = pilot.seed_audit()
        self.assertEqual(len(audit["planned"]), 128)
        self.assertEqual(audit["overlap"], [])

    def test_gate_missing_and_budget_change_block_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                pilot.prerequisite(Path(temporary) / "missing_gate")
            root, budget = self._prepared(temporary)
            from paper3.pivot_b_budget import Ledger
            ledger = Ledger(budget)
            ledger.allocate("fabricated_other", Decimal("1"))
            ledger.reserve("fabricated_other", "fabricated-other-case", Decimal("0.001"), "2" * 64)
            ledger.settle("fabricated-other-case", Decimal("0.001"), True, "3" * 64)
            with mock.patch.object(pilot, "prerequisite", return_value=self._fake_prerequisite()), \
                 self.assertRaisesRegex(ValueError, "pre-stage accounting changed"):
                pilot.execute(root, budget, secret=self.SECRET)
            self.assertFalse(list((root / "calls").glob("*.json")))

    def test_action_score_requires_usable_exact_schema(self):
        assignment = pilot.schedule()[0]
        p = assignment["profile"]
        messages = pilot.game.messages(p, assignment["arm"], p["actors"][0], "recommendation")
        case = pilot.make_case(assignment, p["actors"][0], "recommendation", messages, 0)
        assessed = dict(passed=True, stream=dict(finish_reasons=["stop"]))
        row = dict(assessment=True, request=case["request"], final_content='{"policy_id":"p0"}')
        with mock.patch.object(pilot.service, "assess", return_value=assessed), \
             mock.patch.object(pilot.service, "native_evidence", return_value=dict(present=True)):
            self.assertTrue(pilot.score(row, case)["valid_action"])
            row["final_content"] = '{"policy_id":"not-a-policy"}'
            self.assertFalse(pilot.score(row, case)["valid_action"])
        with mock.patch.object(pilot.service, "assess", return_value=assessed), \
             mock.patch.object(pilot.service, "native_evidence", return_value=dict(present=False)):
            self.assertFalse(pilot.score(row, case)["usable"])

    def test_fabricated_full_pilot_and_isolated_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._fabricated_execute(root, budget)
            report = pilot.audit(root, budget)
            self.assertEqual(len(sent), 128)
            self.assertEqual(len({r["seed"] for r in sent}), 128)
            self.assertEqual(report["completed_episodes"], 8)
            self.assertTrue(report["feasibility_passed"])
            self.assertEqual(report["readout"]["total_pairs"], 4)
            self.assertEqual(report["readout"]["completed_pairs"], 4)
            self.assertFalse(terminal["global_safety_stop"])
            self.assertEqual(Decimal(report["accounted_usd"]), Decimal("0.0128"))
            with self.assertRaisesRegex(ValueError, "already started"):
                with mock.patch.object(pilot, "prerequisite", return_value=self._fake_prerequisite()):
                    pilot.execute(root, budget, secret=self.SECRET)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = pilot.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([
                sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_route_pilot.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)
            decision = sorted((root / "decisions").glob("*.json"))[0]
            altered = pilot.t.load(decision)
            altered["case"]["request"]["seed"] += 1
            decision.write_text(json.dumps(altered))
            with self.assertRaises(ValueError):
                pilot.audit(root, budget)

    def test_invalid_first_action_retains_all_episode_assignments(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            _, sent = self._fabricated_execute(root, budget, first_bad=True)
            report = pilot.audit(root, budget)
            self.assertLess(len(sent), 128)
            self.assertEqual(len(report["assignments"]), 8)
            self.assertFalse(report["feasibility_passed"])
            self.assertGreaterEqual(report["readout"]["missing_pairs"], 1)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = pilot.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([
                sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_route_pilot.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)


if __name__ == "__main__":
    unittest.main()
