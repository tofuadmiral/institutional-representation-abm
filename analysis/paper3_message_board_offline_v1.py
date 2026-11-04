"""Run private reference agents and replay the prospective board without inference.

This command cannot launch a model study. It does not prepare a scientific root,
allocate funding, read credentials or contact a provider.
"""
# ruff: noqa: E402
import argparse
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from paper3 import message_board_handoff_v1 as design


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected():
    root = REPO / "results/paper3/office_sacrifice_probe_v1"
    manifest = json.loads((root / "manifest.json").read_text())
    for name, expected in manifest["sources"].items():
        design.require(sha(REPO / name) == expected, "frozen source changed: " + name)
    files = list((REPO / "results/paper3/pivot_b_budget").rglob("*.json"))
    files += list(root.rglob("*.json"))
    return dict(frozen_sources=manifest["sources"],
                evidence={p.relative_to(REPO).as_posix(): sha(p) for p in sorted(files)})


def guard_selftests():
    def guard(event, args):
        if event.startswith("socket.") or event in (
            "subprocess.Popen", "os.system", "os.fork", "os.forkpty",
            "os.posix_spawn", "os.exec", "pty.spawn",
        ):
            raise PermissionError("offline diagnostic denies network and child processes")
    sys.addaudithook(guard)
    for operation in (lambda: socket.socket(),
                      lambda: subprocess.Popen([sys.executable, "-c", "raise SystemExit(99)"])):
        try:
            operation()
        except PermissionError:
            continue
        raise AssertionError("offline denial selftest failed")
    return True


def exercise(selected, policy):
    episodes, rows = [], []
    for case in selected:
        for condition in design.CONDITIONS:
            e = design.Episode(case, condition)
            while not e.done:
                call = e.next_call()
                if call["kind"] == "post":
                    payload = dict(message="PRIVATE SCRIPTED REFERENCE: compare the supplied utility totals.")
                else:
                    code = case.best_code
                    if policy == "always_retain" or (policy == "own_position_first" and e.target == "self"):
                        code = case.retain_code
                    elif policy == "always_replace":
                        code = case.replace_code
                    payload = dict(decision=code)
                e.accept(call["key"], "recorded_valid", payload)
            row = e.result()
            replayed = design.Episode.replay(case, condition, e.events)
            design.require(replayed.events == e.events and replayed.result() == row,
                           "entire private event/request/outcome replay")
            episodes.append(dict(case=case.index, condition=condition, events=e.events))
            rows.append(row)
    return dict(report=design.readout(selected, rows), episodes=episodes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    design.require(not args.output.exists(), "new output only")
    before = protected()
    guarded = guard_selftests()
    selected = design.cases(args.cases)
    studies = {p: exercise(selected, p) for p in (
        "mandate", "always_retain", "always_replace", "own_position_first")}
    bound = design.request_bound(selected)
    proposed = {design.control(c, k)["request"]["seed"] for c in selected for k in ("factual", "score")}
    proposed.update(design.REQUEST_BASE + c.index * 64 + r * 8 + role
                    for c in selected for r in range(3) for role in range(3))
    scanned = 0
    for path in (REPO / "results/paper3").glob("**/calls/*.json"):
        saved = json.loads(path.read_text())
        design.require(saved.get("request", {}).get("seed") not in proposed, "candidate seed collision")
        scanned += 1
    after = protected()
    design.require(before == after, "frozen evidence or budget mutation")
    closeout = REPO / "results/paper3/office_sacrifice_stage_closeout_2026_11_04.json"
    design.require(sha(closeout) == "da2caf8495bc112eec919e2b4b89155c2bf5695c7b91acd764d30fb93cf1c624",
                   "audited headroom source pin")
    snapshot = json.loads(closeout.read_text())["after"]
    record = dict(kind="PRIVATE_SOFTWARE_REFERENCE_REPLAY_NOT_MODEL_OBSERVATIONS",
        version=design.VERSION, candidate_cases=[asdict(c) for c in selected],
        source_hashes={p: sha(REPO / p) for p in (
            "paper3/message_board_handoff_v1.py", "analysis/paper3_message_board_offline_v1.py",
            "tests/test_paper3_message_board_handoff_v1.py")},
        reference_studies=studies, cost_bound=bound, network_process_denial_selftests=guarded,
        candidate_seed_scan=dict(files=scanned, overlap=0),
        entire_reference_replay_matched=True,
        frozen_sources_unchanged=len(before["frozen_sources"]),
        preserved_evidence_files=len(before["evidence"]),
        before_after_inventory_sha256=design.digest(before),
        last_audited_headroom_usd=snapshot["available_for_new_stages_usd"],
        bound_fits_last_audited_headroom=Decimal(bound["full_bound_usd"]) <=
            Decimal(snapshot["available_for_new_stages_usd"]),
        new_model_calls=0, ledger_mutations=0, protocol_prepared=False,
        paid_launch_authorized=False, paid_launch_ready=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as file:
        json.dump(record, file, indent=2, ensure_ascii=False)
    print(json.dumps({k: record[k] for k in (
        "kind", "entire_reference_replay_matched", "network_process_denial_selftests",
        "frozen_sources_unchanged", "preserved_evidence_files", "new_model_calls",
        "bound_fits_last_audited_headroom", "paid_launch_ready")}, sort_keys=True))


if __name__ == "__main__":
    main()
