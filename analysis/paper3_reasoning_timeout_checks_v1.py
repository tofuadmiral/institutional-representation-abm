"""Capture authentic whole-file amendment checks once, without model calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from experiments import paper3_reasoning_timeout_recovery_v1 as r  # noqa: E402
from analysis.paper3_validation_checks_v1 import save  # noqa: E402

PENDING=REPO/'results/paper3/reasoning_timeout_pending_2026_10_28.json'
TERMINAL=REPO/'results/paper3/reasoning_timeout_checks_2026_10_28.json'
LINT=['/Users/fali/.local/bin/ruff','check',
    'experiments/paper3_reasoning_timeout_recovery_v1.py',
    'paper3/retrospective_reasoning_timeout_recovery_v1.py',
    'tests/test_paper3_reasoning_timeout_recovery_v1.py',
    'analysis/paper3_reasoning_timeout_checks_v1.py']


def main():
    for path in (PENDING,TERMINAL,REPO/r.READINESS):
        r.require(not path.exists(),'original checks exist; inspect, never duplicate')
    before=r.source_inventory()
    spec=r.old.journal.encode(r.specification())
    save(PENDING,dict(pid=os.getpid(),started_unix=time.time(),argv=r.TEST_COMMAND,
        sources_before=before,specification=spec,experimental_observations=False,model_calls=0))
    lint=subprocess.run(LINT,cwd=REPO,text=True,capture_output=True)
    if lint.returncode:
        save(TERMINAL,dict(lint_argv=LINT,returncode=lint.returncode,
            stdout=lint.stdout,stderr=lint.stderr,checks_not_started=True))
        raise RuntimeError('genuine lint failure; no tests/readiness')
    child=subprocess.Popen(r.TEST_COMMAND,cwd=REPO,text=True,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    print(json.dumps(dict(event='started',pid=os.getpid(),child_pid=child.pid,
        argv=r.TEST_COMMAND,sources=len(before))),flush=True)
    out,err=child.communicate()
    after=r.source_inventory()
    result=dict(argv=r.TEST_COMMAND,returncode=child.returncode,stdout=out,stderr=err,
        sources_before=before,sources_after=after,specification=spec,
        specification_after=r.old.journal.encode(r.specification()),
        pid=os.getpid(),child_pid=child.pid,completed_unix=time.time(),
        lint=dict(argv=LINT,returncode=lint.returncode,stdout=lint.stdout,stderr=lint.stderr),
        software_only=True,experimental_observations=False,model_calls=0)
    save(TERMINAL,result)
    equal=before==after and spec==result['specification_after']
    r.require(child.returncode==0 and not err.strip() and equal,
        'genuine test failure or source/spec change; preserve, no readiness')
    save(REPO/r.READINESS,result)
    print(json.dumps(dict(event='terminal',returncode=child.returncode,stdout=out,
        stderr=err,exact_source_spec_equality=equal,sources=len(after),
        readiness_sha256=r.digest(REPO/r.READINESS))),flush=True)


if __name__=='__main__':
    main()
