"""Offline-only checks of the prospective Novita route, with fabricated replies."""
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

from experiments import paper3_constituent_b_gptoss_novita_gate as gate


def metadata():
    return dict(data=dict(id=gate.requests.MODEL, endpoints=[dict(
        tag=gate.requests.PROVIDER_TAG, provider_name=gate.requests.PROVIDER_NAME,
        model_id=gate.requests.MODEL, quantization="fp4", status=0,
        max_completion_tokens=32768, context_length=131072,
        supported_parameters=["reasoning", "max_tokens", "temperature",
                              "top_p", "seed", "tools", "tool_choice"],
        supports_tool_choice=dict(function=True),
        pricing=dict(prompt="0.00000005", completion="0.00000025"))]))


class NovitaGateTests(unittest.TestCase):
    SECRET = "fabricated" + "-novita-secret"

    def _prepared(self, temporary):
        root, budget = Path(temporary) / "run", Path(temporary) / "budget"
        shutil.copytree(gate.BUDGET, budget)
        plan = dict(planned=list(range(gate.requests.SEED_BASE,
                                       gate.requests.SEED_BASE + 12)),
                    overlap=[], historical_files=0, inventory_sha256="0" * 64)
        with mock.patch.object(gate, "seed_audit", return_value=plan):
            gate.prepare(root, metadata=metadata())
        return root, budget

    @staticmethod
    def _trace(answer, generation, *, native=True):
        raw = json.dumps(answer, sort_keys=True)
        frames = [dict(id=generation, model=gate.CONFIG["models"][0],
                       provider=gate.CONFIG["provider"], choices=[dict(index=0,
                       delta=dict(reasoning="fabricated reasoning" if native else ""),
                       finish_reason=None)])]
        for index, fragment in enumerate((raw[:10], raw[10:])):
            function = dict(arguments=fragment)
            call = dict(index=0, function=function)
            if index == 0:
                call.update(id="call_one", type="function")
                function["name"] = gate.requests.TOOL_NAME
            frames.append(dict(choices=[dict(index=0, delta=dict(tool_calls=[call]),
                                             finish_reason=None)]))
        frames += [dict(choices=[dict(index=0, delta={}, finish_reason="tool_calls")]),
                   dict(choices=[], usage=dict(prompt_tokens=100,
                       completion_tokens=100, cost=.0001,
                       completion_tokens_details=dict(reasoning_tokens=80 if native else 0)))]
        lines = [line for frame in frames for line in ("data: " + json.dumps(frame), "")]
        lines += ["data: [DONE]", ""]
        return dict(started_unix=time.time(), ended_unix=time.time(), http_status=200,
                    generation_header=None, lines=lines, line_count=len(lines),
                    byte_count=sum(map(len, lines)), error_type=None,
                    secret_redacted=False)

    def _execute(self, root, budget, *, bad_first=False):
        sent = []
        cases = {row["request"]["seed"]: row for row in gate.cases()}

        def send(wire, secret):
            request = json.loads(wire)
            sent.append(request)
            context = cases[request["seed"]]["context"]
            if context["kind"] == "fact":
                answer = context["expected"]
            elif context["stage"] == "first_vote":
                answer = dict(vote=True)
            else:
                answer = dict(projects=dict(A="A0", B="B0"), first="A",
                              coalition=[0, 1, 3, 4], message="fabricated")
                if context["stage"] == "response":
                    answer["support"] = True
            return self._trace(answer, "fabricated-" + str(len(sent)),
                               native=not (bad_first and len(sent) == 1))

        def lookup(generation, secret):
            return dict(http_status=200, error_type=None, secret_redacted=False,
                        started_unix=time.time(), ended_unix=time.time(),
                        data=dict(id=generation, model=gate.CONFIG["models"][0],
                                  provider_name=gate.CONFIG["provider"],
                                  total_cost=.0001))

        with redirect_stdout(io.StringIO()):
            terminal = gate.execute(root, budget, secret=self.SECRET, send=send,
                                    lookup=lookup, sleep=lambda _: None)
        return terminal, sent

    def test_inventory_price_and_seed_scan(self):
        rows = gate.cases()
        self.assertEqual(len(rows), 12)
        self.assertEqual([row["context"]["kind"] for row in rows],
                         ["fact"] * 9 + ["action"] * 3)
        self.assertEqual({row["request"]["seed"] for row in rows},
                         set(range(669000, 669012)))
        self.assertLess(sum(Decimal(row["reserved_usd"]) for row in rows), gate.CAP)
        self.assertEqual(gate.check_endpoint(metadata())["tag"],
                         gate.requests.PROVIDER_TAG)
        self.assertFalse(gate.seed_audit()["overlap"])

    def test_fabricated_full_pass_and_isolated_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._execute(root, budget)
            report = gate.audit(root, budget)
            self.assertEqual(len(sent), 12)
            self.assertTrue(report["gate_passed"])
            self.assertFalse(terminal["global_safety_stop"])
            self.assertEqual(Decimal(report["accounted_usd"]), Decimal("0.0012"))
            with self.assertRaisesRegex(ValueError, "already started"):
                gate.execute(root, budget, secret=self.SECRET)
            target, archive = Path(temporary) / "bundle", Path(temporary) / "archive.zip"
            info = gate.export(root, budget, target, archive, secret=self.SECRET)
            extracted = Path(temporary) / "extracted"
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
            process = subprocess.run([sys.executable, "-I", "-S",
                str(extracted / "code/experiments/paper3_constituent_b_gptoss_novita_gate.py"),
                str(extracted), "--replay", "--expected-protocol", info["protocol"]],
                env={}, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            replayed = json.loads(process.stdout)
            self.assertTrue(replayed.pop("portable_replay")["exact_report_match"])
            self.assertEqual(replayed, report)

    def test_first_failure_keeps_twelve_assignments_and_no_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            terminal, sent = self._execute(root, budget, bad_first=True)
            report = gate.audit(root, budget)
            self.assertEqual(len(sent), 1)
            self.assertFalse(report["gate_passed"])
            self.assertTrue(terminal["global_safety_stop"])
            self.assertEqual(len(report["assignments"]), 12)
            self.assertEqual(sum(row["status"] == "not_started"
                                 for row in report["assignments"]), 11)

    def test_changed_budget_or_source_blocks_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            manifest = gate.t.load(root / "manifest.json")
            manifest["protocol"]["cases"][0]["request"]["provider"]["only"] = [
                "coreweave/fp4"]
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                gate.verify(root)
        with tempfile.TemporaryDirectory() as temporary:
            root, budget = self._prepared(temporary)
            from paper3.pivot_b_budget import Ledger
            ledger = Ledger(budget)
            ledger.allocate("fabricated_other", Decimal("1"))
            ledger.reserve("fabricated_other", "fabricated-other", Decimal("0.001"),
                           "2" * 64)
            ledger.settle("fabricated-other", Decimal("0.001"), True, "3" * 64)
            with self.assertRaisesRegex(ValueError, "pre-stage accounting changed"):
                gate.execute(root, budget, secret=self.SECRET)
            self.assertFalse(list((root / "calls").glob("*.json")))


if __name__ == "__main__":
    unittest.main()
