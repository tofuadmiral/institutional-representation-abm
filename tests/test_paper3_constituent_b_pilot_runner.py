"""Offline-only pilot runner tests; all responses and charges are fabricated."""
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

from experiments import paper3_constituent_b_pilot as pilot
from tests.test_paper3_constituent_b_gate_runner import metadata


class ConstituentPilotRunnerTests(unittest.TestCase):
    SECRET = "fabricated" + "-pilot-secret"

    @staticmethod
    def _fake_prerequisite():
        protocol = "f" * 64
        report = dict(protocol=protocol, gate_passed=True, calls=12)
        return dict(protocol=protocol, report=report,
                    report_sha256=pilot.t.sha(pilot.t.canonical(report).encode()),
                    limitation="fabricated gate for offline test only")

    def _prepared(self, temporary):
        plan = dict(planned_unique=sorted({a["seed_base"] + i
                                          for a in pilot.assignments() for i in range(30)}),
                    intended_calls=360, paired_across_arms=True, overlap=[],
                    historical_files=0, inventory_sha256="0" * 64)
        root = Path(temporary) / "run"
        with mock.patch.object(pilot, "prerequisite", return_value=self._fake_prerequisite()), \
             mock.patch.object(pilot, "prerequisite_paths", return_value=[]), \
             mock.patch.object(pilot, "seed_audit", return_value=plan):
            pilot.prepare(root, metadata=metadata())
        budget = Path(temporary) / "budget"
        shutil.copytree(pilot.BUDGET, budget)
        return root, budget

    @staticmethod
    def _trace(answer, generation, *, native=True):
        frames = [dict(id=generation, model=pilot.CONFIG["models"][0],
                       provider=pilot.CONFIG["provider"],
                       choices=[dict(index=0, delta=dict(
                           reasoning="fabricated reasoning" if native else ""),
                           finish_reason=None)]),
                  dict(choices=[dict(index=0, delta=dict(content=answer),
                                     finish_reason="stop")]),
                  dict(choices=[], usage=dict(prompt_tokens=100, completion_tokens=100,
                                             cost=.0001,
                                             completion_tokens_details=dict(
                                                 reasoning_tokens=80 if native else 0)))]
        lines = [item for frame in frames for item in ("data: " + json.dumps(frame), "")]
        lines.extend(["data: [DONE]", ""])
        return dict(started_unix=time.time(), ended_unix=time.time(), http_status=200,
                    generation_header=None, lines=lines, line_count=len(lines),
                    byte_count=sum(map(len, lines)), error_type=None,
                    secret_redacted=False)

    def _fabricated_execute(self, root, budget, *, bad_first=False):
        sent = []
        bases = {row["seed_base"] for row in pilot.assignments()}

        def send(wire, secret):
            request = json.loads(wire)
            sent.append(request)
            generation = "fabricated-" + str(len(sent))
            base = max(value for value in bases if value <= request["seed"])
            index = request["seed"] - base
            if bad_first and len(sent) == 1:
                answer = "not JSON"
            elif index in (0, 8) or 1 <= index <= 7:
                answer = dict(projects=dict(A="A0", B="B0"), first="A",
                              coalition=[], message="fabricated")
                if 1 <= index <= 7:
                    answer["support"] = True
            elif 9 <= index <= 15:
                answer = dict(consent=True)
            else:
                answer = dict(vote=True)
            return self._trace(answer if isinstance(answer, str) else json.dumps(answer),
                               generation)

        def lookup(generation, secret):
            return dict(http_status=200, error_type=None, secret_redacted=False,
                        started_unix=time.time(), ended_unix=time.time(),
                        data=dict(id=generation, model=pilot.CONFIG["models"][0],
                                  provider_name=pilot.CONFIG["provider"], total_cost=.0001))

        with mock.patch.object(pilot, "prerequisite", return_value=self._fake_prerequisite()), \
             redirect_stdout(io.StringIO()):
            terminal = pilot.execute(root, budget, secret=self.SECRET, send=send,
                                     lookup=lookup, sleep=lambda _: None)
        return terminal, sent

    def test_schedule_and_case_bounds(self):
        rows = pilot.assignments()
        self.assertEqual(len(rows), 12)
        self.assertEqual([row["phase"] for row in rows], [1] * 3 + [2] * 9)
        self.assertEqual({row["arm"] for row in rows}, set(pilot.game.ARMS))
        self.assertEqual(len({row["seed_base"] for row in rows}), 4)
        prepared = pilot.prepared_profiles()[rows[0]["profile_id"]]["prepared"]
        messages = pilot.institution.messages(prepared, rows[0]["arm"],
                                              prepared["contract_profile"]["proposer"],
                                              "draft", [])
        case = pilot.make_case(rows[0], prepared["contract_profile"]["proposer"],
                               "draft", messages, 0)
        self.assertEqual(case["request"]["seed"], rows[0]["seed_base"])
        self.assertLess(Decimal(case["reserved_usd"]), Decimal("0.01"))

    def test_seed_scan_and_missing_gate(self):
        with self.assertRaises(FileNotFoundError):
            pilot.prerequisite(Path(tempfile.gettempdir()) / "definitely-missing-paper3-gate")
        scan = pilot.seed_audit()
        self.assertEqual(len(scan["planned_unique"]), 120)
        self.assertFalse(scan["overlap"])
        with tempfile.TemporaryDirectory() as temporary:
            gate = Path(temporary) / "results/paper3" / pilot.GATE_ROOT.name
            gate.mkdir(parents=True)
            (gate / "manifest.json").write_text(json.dumps(dict(protocol=dict(
                cases=[dict(request=dict(seed=641900))],
                discovery_assignments=[dict(seed_base=642000)]))))
            # Planned future seeds in the gate manifest are not used requests.
            self.assertFalse(pilot.seed_audit(temporary)["overlap"])
            (gate / "calls").mkdir()
            (gate / "calls" / "wrong.json").write_text(
                json.dumps(dict(request=dict(seed=642000))))
            with self.assertRaisesRegex(ValueError, "historical discovery seed overlap"):
                pilot.seed_audit(temporary)

    def test_budget_and_source_tampering_block_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            from paper3.pivot_b_budget import Ledger
            ledger = Ledger(budget)
            ledger.allocate("fabricated_other", Decimal("1"))
            ledger.reserve("fabricated_other", "fabricated-other", Decimal("0.001"), "2" * 64)
            ledger.settle("fabricated-other", Decimal("0.001"), True, "3" * 64)
            with mock.patch.object(pilot, "prerequisite", return_value=self._fake_prerequisite()), \
                 self.assertRaisesRegex(ValueError, "pre-stage accounting changed"):
                pilot.execute(root, budget, secret=self.SECRET)
            self.assertFalse(list((root / "calls").glob("*.json")))
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            manifest = pilot.t.load(root / "manifest.json")
            manifest["protocol"]["assignments"][0]["seed_base"] += 1
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                pilot.verify(root)

    def test_action_score_requires_native_reasoning_and_exact_schema(self):
        assignment = pilot.assignments()[0]
        prepared = pilot.prepared_profiles()[assignment["profile_id"]]["prepared"]
        actor = prepared["contract_profile"]["proposer"]
        messages = pilot.institution.messages(prepared, assignment["arm"],
                                              actor, "draft", [])
        case = pilot.make_case(assignment, actor, "draft", messages, 0)
        good = json.dumps(dict(projects=dict(A="A0", B="B0"), first="A",
                               coalition=[], message="fabricated"))
        row = dict(assessment=True, request=case["request"], final_content=good)
        assessment = dict(passed=True, stream=dict(finish_reasons=["stop"]))
        with mock.patch.object(pilot.service, "assess", return_value=assessment), \
             mock.patch.object(pilot.service, "native_evidence",
                               return_value=dict(present=True)):
            self.assertTrue(pilot.score(row, case)["valid_action"])
            row["final_content"] = '{"projects":{},"first":"A","coalition":[],"message":""}'
            self.assertFalse(pilot.score(row, case)["valid_action"])
        row["final_content"] = good
        with mock.patch.object(pilot.service, "assess", return_value=assessment), \
             mock.patch.object(pilot.service, "native_evidence",
                               return_value=dict(present=False)):
            self.assertFalse(pilot.score(row, case)["usable"])

    def test_complete_fabricated_path_and_extracted_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._fabricated_execute(root, budget)
            report = pilot.audit(root, budget)
            self.assertEqual(len(sent), 360)
            self.assertEqual(len({row["seed"] for row in sent}), 120)
            self.assertEqual(report["completed_episodes"], 12)
            self.assertEqual(report["readout"]["completed_profile_pairs"], 12)
            self.assertTrue(report["feasibility_passed"])
            self.assertFalse(terminal["global_safety_stop"])
            self.assertEqual(Decimal(report["accounted_usd"]), Decimal("0.036"))
            with mock.patch.object(pilot, "prerequisite", return_value=self._fake_prerequisite()), \
                 self.assertRaisesRegex(ValueError, "already started"):
                pilot.execute(root, budget, secret=self.SECRET)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = pilot.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([
                sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_constituent_b_pilot.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)

    def test_first_failure_preserves_twelve_assignments_and_blocks_phase_two(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._fabricated_execute(root, budget, bad_first=True)
            report = pilot.audit(root, budget)
            self.assertEqual(len(sent), 1)
            self.assertFalse(report["feasibility_passed"])
            self.assertEqual(len(report["assignments"]), 12)
            self.assertEqual(report["assignments"][0]["status"], "failed")
            self.assertEqual(sum(row["status"] == "not_started"
                                 for row in report["assignments"]), 11)
            self.assertTrue(terminal["global_safety_stop"])
            self.assertEqual(report["readout"]["completed_profile_pairs"], 0)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = pilot.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([
                sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_constituent_b_pilot.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)


if __name__ == "__main__":
    unittest.main()
