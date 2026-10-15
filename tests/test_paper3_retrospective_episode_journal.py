"""Fabricated controller/ledger evidence, including real fresh isolated replay."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_independent_execution as execution
from paper3.pivot_b_budget import atomic
from tests import test_paper3_retrospective_independent_calls as fabricated
from tests import test_paper3_retrospective_extended_budget as copied_budget

PROTOCOL = "f" * 64


@pytest.fixture
def ledger(tmp_path):
    return copied_budget.ledger.__wrapped__(tmp_path)


def run(tmp_path, ledger, *, bad=(), rate=(), unsafe=None, transport_error=False, billing_error=False):
    bridge, sent, _ = fabricated.setup(tmp_path, ledger, bad=bad, rate=rate, unsafe=unsafe)
    if transport_error:
        def failed_send(wire, secret):
            sent.append(wire)
            raise OSError("fabricated unknown transport failure")
        bridge.send = failed_send
    if billing_error:
        bridge.lookup = lambda key, secret: dict(http_status=503, error_type="HTTPError", data=None,
                                               secret_redacted=False)
    items = fabricated.assignments()
    writer = journal.Journal(bridge.root, items, PROTOCOL, verify=bridge.verify)
    report = execution.execute(items, respond=lambda request, key: bridge.one(fabricated.case(key, request)),
        verify=lambda: journal._guard(bridge.verify, PROTOCOL), persist=writer.append)
    writer.close()
    bridge.close()
    audited = journal.audit(bridge.root, ledger.root, bridge.stage, items, PROTOCOL,
                            verify=bridge.verify, maximum_reissues=1)
    assert journal.canonical(journal.encode(audited["report"])) == journal.canonical(journal.encode(report))
    return bridge, items, report, audited, sent


@pytest.mark.parametrize("failure", ("transport", "billing"))
def test_unknown_failure_preserves_full_cost_and_all_missing_outcomes_in_replay(tmp_path, ledger, failure):
    bridge, _, report, audited, sent = run(tmp_path, ledger,
        transport_error=failure == "transport", billing_error=failure == "billing")
    assert len(sent) == audited["physical_attempts"] == 1
    assert report["global_safety_stop"] and report["completed"] == 0
    assert not report["assignments"][0]["first_term"]["complete"]
    assert report["assignments"][1]["status"] == "not_started"
    record = journal.load(next((bridge.root / "calls").glob("*.json")))
    assert audited["physical_accounted_usd"] == record["reserved_usd"]
    entries = [journal.load(p) for p in (ledger.root / "entries").glob("*.json")]
    own = [r for r in entries if r["stage"] == bridge.stage]
    assert len(own) == 1 and (own[0]["status"] == "reserved" if failure == "transport" else
                             own[0]["certified"] is False)


@pytest.mark.parametrize("bad,rate,unsafe", (((), (), None), ((1,), (), None),
    ((16,), (), None), ((), (1,), None), ((), (1, 2), None), ((), (), dict(channel="both"))))
def test_physical_financial_journal_and_full_controller_replay(tmp_path, ledger, bad, rate, unsafe):
    bridge, items, report, audited, sent = run(tmp_path, ledger, bad=bad, rate=rate, unsafe=unsafe)
    assert audited["physical_attempts"] == len(sent)
    assert not audited["publication_evidence"]
    saved = journal.inspect(bridge.root, items, PROTOCOL, verify=bridge.verify)
    assert saved["complete"] and saved["events_recorded"] == audited["events_replayed"]
    assert saved["events"][0]["event"] == "inventory" and saved["events"][-1]["event"] == "terminal"
    assert len(report["assignments"]) == 2
    for path in (bridge.root / "episode_journal").glob("*.json"):
        # Native transcript copied once per physical file, not in every snapshot.
        assert '"lines"' not in path.read_text()
    if bad == (16,):
        assert report["assignments"][0]["first_term"]["complete"]
        assert not report["assignments"][0]["two_term"]["complete"]
    if unsafe or rate == (1, 2):
        assert report["global_safety_stop"] and report["assignments"][1]["status"] == "not_started"


@pytest.mark.parametrize("value", (None, True, 1, False, 0, 1.0, "text", Fraction(1, 3),
    (1, True, [False]), {False: 0, True: 1}, {"kind": "map", "items": []},
    {"fraction": Fraction(3, 7), "game": fabricated.fixture(2)}))
def test_codec_is_lossless_and_type_distinguishing(value):
    result = journal.decode(journal.encode(value))
    assert type(result) is type(value)
    assert journal.canonical(journal.encode(result)) == journal.canonical(journal.encode(value))
    assert journal.encode(True) != journal.encode(1) or journal.canonical(journal.encode(True)) != journal.canonical(journal.encode(1))


@pytest.mark.parametrize("value", (dict(kind="fraction", numerator=True, denominator=1),
    dict(kind="fraction", numerator=2, denominator=4), dict(kind="dataclass", name="os.system", fields={}),
    dict(kind="tuple", items=[], ignored=True), dict(kind="map", items=[[True, 0], [1, 1]])))
def test_codec_rejects_ambiguity_coercion_and_arbitrary_class_execution(value):
    with pytest.raises((ValueError, TypeError)):
        journal.decode(value)


@pytest.mark.parametrize("value", (float("inf"), float("nan"), {1, 2}, Path("unregistered")))
def test_codec_rejects_nonfinite_or_unregistered_objects(value):
    with pytest.raises(ValueError):
        journal.encode(value)


def test_duplicate_json_keys_never_silently_replace_evidence(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"protocol":"one","protocol":"two"}')
    with pytest.raises(ValueError, match="duplicate JSON"):
        journal.load(path)


def test_interruption_has_prefix_not_terminal_and_never_restarts(tmp_path):
    items = fabricated.assignments()
    writer = journal.Journal(tmp_path, items, PROTOCOL, verify=lambda: ({}, PROTOCOL))
    writer.append(dict(event="inventory", assignments=()))
    writer.close()
    prefix = journal.inspect(tmp_path, items, PROTOCOL, verify=lambda: ({}, PROTOCOL))
    assert not prefix["complete"] and prefix["events_recorded"] == 1
    with pytest.raises(ValueError, match="incomplete journal"):
        journal.replay(tmp_path, items, PROTOCOL, verify=lambda: ({}, PROTOCOL), transport_report={})
    with pytest.raises(FileExistsError):
        journal.Journal(tmp_path, items, PROTOCOL, verify=lambda: ({}, PROTOCOL))


def test_source_rejection_poisoning_is_not_a_resume_or_terminal(tmp_path):
    state = [True]
    def verify():
        return {}, PROTOCOL if state[0] else "0" * 64
    writer = journal.Journal(tmp_path, fabricated.assignments(), PROTOCOL, verify=verify)
    state[0] = False
    with pytest.raises(ValueError, match="verification rejected"):
        writer.append(dict(event="inventory", assignments=()))
    state[0] = True
    with pytest.raises(ValueError, match="never resume"):
        writer.append(dict(event="inventory", assignments=()))
    writer.close()


def test_boolean_integer_start_forgery_rejected_even_when_python_equality_accepts_it(tmp_path):
    items = fabricated.assignments()
    writer = journal.Journal(tmp_path, items, PROTOCOL, verify=lambda: ({}, PROTOCOL))
    writer.close()
    path = tmp_path / "episode_journal/start.json"
    data = journal.load(path)
    def substitute(value):
        if type(value) in (list, dict):
            for key in (range(len(value)) if type(value) is list else value):
                if type(value[key]) is int and value[key] == 1:
                    value[key] = True
                    return True
                if substitute(value[key]):
                    return True
        return False
    assert substitute(data)
    assert data == journal.start_record(items, PROTOCOL)
    atomic(path, data)
    with pytest.raises(ValueError, match="start/inventory changed"):
        journal.inspect(tmp_path, items, PROTOCOL, verify=lambda: ({}, PROTOCOL))


@pytest.mark.parametrize("mutation", ("event", "physical", "deleted", "chain", "terminal_report", "partial"))
def test_changed_or_incomplete_evidence_cannot_match_exact_replay(tmp_path, ledger, mutation):
    bridge, items, _, _, _ = run(tmp_path, ledger, bad=(1,))
    directory = bridge.root / "episode_journal"
    paths = sorted(p for p in directory.glob("*.json") if p.name != "start.json")
    if mutation == "physical":
        path = next((bridge.root / "calls").glob("*.json"))
        data = journal.load(path)
        data["request"]["seed"] += 1
        atomic(path, data)
    elif mutation == "deleted":
        paths[2].unlink()
    elif mutation == "partial":
        (directory / "999999.partial").write_text("interrupted fabricated write")
    else:
        path = paths[-1] if mutation == "terminal_report" else paths[1]
        data = journal.load(path)
        if mutation == "chain":
            data["previous_sha256"] = "0" * 64
        else:
            payload = journal.decode(data["payload"])
            if mutation == "terminal_report":
                payload["report"]["completed"] += 1
            else:
                payload["slot"]["id"] = "changed"
            data["payload"] = journal.encode(payload)
        atomic(path, data)
    with pytest.raises(ValueError):
        journal.audit(bridge.root, ledger.root, bridge.stage, items, PROTOCOL,
                      verify=bridge.verify, maximum_reissues=1)


def test_fake_logical_evidence_copy_is_not_referenced_as_original(tmp_path, ledger):
    bridge, _, _ = fabricated.setup(tmp_path, ledger)
    saved = bridge.one(fabricated.case())
    changed = deepcopy(saved)
    changed["id"] = "unassigned"
    with pytest.raises(ValueError, match="provenance"):
        journal.compact(changed, bridge.root, PROTOCOL)
    changed = deepcopy(saved)
    changed["result"]["status"] = "content_failed"
    with pytest.raises(ValueError, match="logical copy differs"):
        journal.compact(changed, bridge.root, PROTOCOL)
    bridge.close()


def test_recomputed_hash_chain_cannot_hide_a_changed_controller_event(tmp_path, ledger):
    bridge, items, _, _, _ = run(tmp_path, ledger, bad=(1,))
    directory = bridge.root / "episode_journal"
    previous = journal._digest(directory / "start.json")
    for path in sorted(p for p in directory.glob("*.json") if p.name != "start.json"):
        data = journal.load(path)
        if data["index"] == 1:
            event = journal.decode(data["payload"])
            event["slot"]["id"] = "forged-assignment"
            data["payload"] = journal.encode(event)
        data["previous_sha256"] = previous
        atomic(path, data)
        previous = journal._digest(path)
    # Cryptographic consistency by itself is insufficient: semantic replay must fail.
    assert journal.inspect(bridge.root, items, PROTOCOL, verify=bridge.verify)["complete"]
    with pytest.raises(ValueError, match="recomputed journal"):
        journal.audit(bridge.root, ledger.root, bridge.stage, items, PROTOCOL,
                      verify=bridge.verify, maximum_reissues=1)


def test_complete_journal_cannot_accept_another_event_or_release_spending_authority(tmp_path, ledger):
    bridge, sent, _ = fabricated.setup(tmp_path, ledger, bad=(1,))
    writer = journal.Journal(bridge.root, fabricated.assignments(), PROTOCOL, verify=bridge.verify)
    execution.execute(fabricated.assignments(),
        respond=lambda request, key: bridge.one(fabricated.case(key, request)),
        verify=lambda: journal._guard(bridge.verify, PROTOCOL), persist=writer.append)
    before = ledger.snapshot()
    with pytest.raises(ValueError, match="never resume"):
        writer.append(dict(event="terminal", report={}))
    writer.close()
    bridge.close()
    assert ledger.snapshot() == before and len(sent) == 31
    assert not (ledger.root / "stage_closures").exists()


def test_actual_fresh_extracted_stdlib_only_network_disabled_full_replay(tmp_path, ledger):
    bridge, items, _, report, _ = run(tmp_path, ledger, bad=(16,), rate=(1,))
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    repo = Path(__file__).resolve().parents[1]
    for package in ("paper3", "experiments", "analysis"):
        shutil.copytree(repo / package, bundle / "code" / package,
            ignore=shutil.ignore_patterns("data", "__pycache__", "*.zip"))
    shutil.copytree(bridge.root, bundle / "run")
    shutil.copytree(ledger.root / "entries", bundle / "ledger/entries")
    for name in copied_budget.budget.AUTHORITY_FILES:
        shutil.copy2(ledger.root / name, bundle / "ledger" / name)
    shutil.copytree(ledger.root / "stages", bundle / "ledger/stages")
    inventory = bundle / "inventory.json"
    atomic(inventory, journal.encode(items))
    archive = tmp_path / "fabricated.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(bundle).as_posix())
    extracted = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(extracted)  # Own generated archive; no untrusted extraction.
    script = extracted / "code/analysis/paper3_episode_journal_replay.py"
    result = subprocess.run([sys.executable, "-I", "-S", str(script), str(extracted / "run"),
        "--ledger", str(extracted / "ledger"), "--stage", bridge.stage,
        "--inventory", str(extracted / "inventory.json"), "--inventory-sha256", journal._digest(inventory),
        "--expected-protocol", PROTOCOL, "--maximum-reissues", "1",
        "--expected-report-sha256", journal.physical.t.sha(journal.canonical(journal.encode(report)).encode())],
        cwd=extracted, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    assert proof["component_replay_matched"] and proof["network_prohibited"]
    assert proof["network_guard_self_test"]
    assert proof["physical_reissues"] == 1 and proof["content_failed"] == 1
    assert not proof["production_source_freeze_verified"] and not proof["publication_evidence"]
