"""Capture genuine offline whole-file checks and exact source/spec equality once."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from experiments import paper3_independent_validation_v1 as r  # noqa: E402

PENDING = REPO / "results/paper3/independent_validation_pending_2026_10_27.json"
TERMINAL = REPO / "results/paper3/independent_validation_checks_2026_10_27.json"
LINT = ["/Users/fali/.local/bin/ruff", "check",
        "experiments/paper3_independent_validation_v1.py",
        "paper3/retrospective_validation_budget_v1.py",
        "paper3/retrospective_validation_design_v1.py",
        "tests/test_paper3_independent_validation_v1.py",
        "analysis/paper3_validation_checks_v1.py"]


def save(path, value):
    r.require(not path.exists(), "never replace genuine test evidence")
    patch = "*** Begin Patch\n*** Add File: " + str(path) + "\n"
    patch += "\n".join("+" + line for line in json.dumps(value, indent=2, sort_keys=True).splitlines())
    patch += "\n*** End Patch\n"
    completed = subprocess.run([shutil.which("apply_patch")], input=patch,
        text=True, capture_output=True, cwd=REPO, check=True)
    r.require("Success" in completed.stdout or path.is_file(), "evidence patch failed")


def main():
    for path in (PENDING, TERMINAL, REPO/r.READINESS):
        r.require(not path.exists(), "original check already exists; inspect it, never duplicate")
    before = r.source_inventory()
    spec = r.journal.encode(r.specification())
    save(PENDING, dict(pid=os.getpid(), started_unix=time.time(), argv=r.TEST_COMMAND,
        sources_before=before, specification=spec, model_calls=0))
    lint = subprocess.run(LINT, cwd=REPO, text=True, capture_output=True)
    r.require(lint.returncode == 0, "genuine lint failed; preserve process output")
    child = subprocess.Popen(r.TEST_COMMAND, cwd=REPO, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(json.dumps(dict(event="started", pid=os.getpid(), child_pid=child.pid,
        argv=r.TEST_COMMAND, sources=len(before))), flush=True)
    out, err = child.communicate()
    after = r.source_inventory()
    result = dict(argv=r.TEST_COMMAND, returncode=child.returncode,
        stdout=out, stderr=err, sources_before=before, sources_after=after,
        specification=spec, specification_after=r.journal.encode(r.specification()),
        pid=os.getpid(), child_pid=child.pid, completed_unix=time.time(),
        lint=dict(argv=LINT, returncode=lint.returncode, stdout=lint.stdout, stderr=lint.stderr),
        software_only=True, experimental_observations=False, model_calls=0)
    save(TERMINAL, result)
    equal = before == after and spec == result['specification_after']
    r.require(child.returncode == 0 and not err.strip() and equal,
        "genuine checks failed or source/spec changed; no readiness")
    save(REPO/r.READINESS, result)
    print(json.dumps(dict(event="terminal", returncode=child.returncode,
        stdout=out, stderr=err, exact_sources_equal=equal, sources=len(after),
        readiness_sha256=r.digest(REPO/r.READINESS))), flush=True)


if __name__ == "__main__":
    main()
