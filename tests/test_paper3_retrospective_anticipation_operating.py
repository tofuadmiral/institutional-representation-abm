"""Default-entry-point tests only: fabricated guards, no network or real ledger."""
from pathlib import Path
import json

import pytest

from paper3 import retrospective_anticipation_operating as operating

REPO = Path(__file__).resolve().parents[1]
PROTOCOL = "a" * 64


@pytest.fixture
def guards(monkeypatch):
    calls = []
    def send(wire, secret):
        calls.append(("send", wire, secret))
        return "fabricated stream"
    def lookup(identifier, secret):
        calls.append(("lookup", identifier, secret))
        return "fabricated receipt"
    monkeypatch.setattr(operating.hosted, "transmit", send)
    monkeypatch.setattr(operating.diagnostic, "receipt_lookup", lookup)
    path = Path(operating.__file__).resolve()
    manifest = dict(sources={path.relative_to(REPO).as_posix():operating.journal._digest(path)},
                    operating_readiness=dict(path=operating.freeze.READINESS_FILE, sha256="a"*64),
                    operating_authorization=dict(path=operating.freeze.AUTHORIZATION_FILE, sha256="b"*64))
    monkeypatch.setattr(operating.freeze, "verify", lambda *args: (manifest, PROTOCOL))
    monkeypatch.setattr(operating, "readiness_check", lambda *args: {"fabricated":True})
    monkeypatch.setattr(operating.freeze, "authorization_check", lambda *args: {"fabricated":True})
    def coordinator(*args, **kwargs):
        calls.append(("coordinator", args, kwargs))
        return kwargs
    monkeypatch.setattr(operating.coordinator, "run_block", coordinator)
    return calls, manifest, send, lookup


def invoke(batch=0, **kwargs):
    return operating.run_block("private-run", REPO, "private-ledger", PROTOCOL, batch,
        metadata={"fabricated":True}, metadata_observed_unix=1, **kwargs)


def test_default_path_resolves_actual_backend_names_before_admission(guards):
    calls, _, send, lookup = guards
    result = invoke()
    assert result["send"] is send and result["lookup"] is lookup
    assert result["send"]("wire", None) == "fabricated stream"
    assert result["lookup"]("generation", None) == "fabricated receipt"
    assert [c[0] for c in calls] == ["coordinator", "send", "lookup"]
    assert result["certify_partial"] is None and result["secret"] is None


def test_missing_actual_default_backend_stops_before_admission(guards, monkeypatch):
    calls, _, _, _ = guards
    monkeypatch.delattr(operating.hosted, "transmit")
    with pytest.raises(AttributeError):
        invoke()
    assert not calls


def test_noncallable_backend_stops_before_admission(guards, monkeypatch):
    calls, _, _, _ = guards
    monkeypatch.setattr(operating.diagnostic, "receipt_lookup", None)
    with pytest.raises(ValueError, match="entry points"):
        invoke()
    assert not calls


def test_current_unintegrated_freeze_cannot_operate(guards):
    calls, manifest, _, _ = guards
    manifest["sources"].clear()
    with pytest.raises(ValueError, match="prospective source freeze"):
        invoke()
    assert not calls


def test_component_freeze_without_operating_readiness_cannot_admit(guards):
    calls, manifest, _, _ = guards
    manifest["operating_readiness"] = None
    with pytest.raises(ValueError, match="verified operating readiness"):
        invoke()
    assert not calls


def test_no_human_authorization_cannot_admit(guards):
    calls, manifest, _, _ = guards
    manifest["operating_authorization"] = None
    with pytest.raises(ValueError, match="human authorization"):
        invoke()
    assert not calls


def test_readiness_failure_cannot_reach_financial_or_transport_admission(guards, monkeypatch):
    def stale(*args):
        raise ValueError("fabricated stale readiness")
    monkeypatch.setattr(operating, "readiness_check", stale)
    with pytest.raises(ValueError, match="stale readiness"):
        invoke()
    assert not guards[0]


@pytest.mark.parametrize("batch", [True, -1, 2, "0"])
def test_invalid_batch_cannot_admit(guards, batch):
    with pytest.raises(ValueError, match="explicit batch"):
        invoke(batch)
    assert not guards[0]


def test_first_block_refuses_injected_partial_evidence(guards):
    with pytest.raises(ValueError, match="first block"):
        invoke(partial_directory="fake", partial_zip="fake.zip")
    assert not guards[0]


def test_second_block_requires_existing_archive_not_arbitrary_callback(guards):
    with pytest.raises(ValueError, match="actual partial archive paths"):
        invoke(1)
    assert not guards[0]


def test_second_block_uses_real_isolated_replay_entry_point(guards, tmp_path, monkeypatch):
    target, zipped = tmp_path / "partial", tmp_path / "partial.zip"
    target.mkdir()
    zipped.touch()  # PRIVATE placeholder; replay entry is mocked below.
    seen = []
    def isolated(directory, archive, protocol):
        seen.append((directory, archive, protocol))
        return dict(report_sha256=operating.archive.report_sha({"private":True}))
    monkeypatch.setattr(operating.archive, "isolated_certificate", isolated)
    result = invoke(1, partial_directory=target, partial_zip=zipped)
    assert not seen
    result["certify_partial"]({"private":True})
    assert seen == [(target.resolve(), zipped.resolve(), PROTOCOL)]
    with pytest.raises(ValueError, match="differs from current"):
        result["certify_partial"]({"private":False})


@pytest.fixture
def ready(tmp_path, monkeypatch):
    # FABRICATED record/inventory only; never source-ready evidence for a live run.
    sources = {"private.py":"b" * 64}
    monkeypatch.setattr(operating, "readiness_inventory", lambda repo: dict(sources))
    monkeypatch.setattr(operating.freeze, "specification", lambda: {"fabricated":True})
    record = dict(format=operating.READINESS_FORMAT, sources_before=dict(sources),
        sources_after=dict(sources), specification_sha256=operating.journal.physical.t.sha(
            operating.journal.canonical({"fabricated":True}).encode()), actual_model_calls=0,
        checks={name:dict(argv=command, returncode=0, stdout=".....\n5 passed in 2.00s\n", stderr="")
                for name, command in operating.REQUIRED_CHECKS.items()})
    path = tmp_path / "fabricated-readiness.json"
    def verify():
        path.write_text(json.dumps(record))  # PRIVATE fabricated fixture only.
        return operating.readiness_check(tmp_path, path, operating.journal._digest(path))
    return record, path, verify


def test_pinned_readiness_has_no_launch_or_authenticity_authority(ready):
    record, path, verify = ready
    result = verify()
    assert result["sources_verified"] and result["offline_checks_verified"]
    assert not result["launch_authorized"] and not result["allocation_authorized"]
    assert not result["authentic_execution_proved_by_hash"] and not result["publication_evidence"]


def test_readiness_accepts_actual_pytest_long_duration_summary_format(ready):
    record, _, verify = ready
    record["checks"]["complete_pipeline"]["stdout"] = ".....\n5 passed in 2024.25s (0:33:44)\n"
    assert verify()["offline_checks_verified"]


@pytest.mark.parametrize("mutation", ["sources_before", "sources_after", "specification", "calls", "boolean_calls"])
def test_stale_or_nonoffline_readiness_refuses(ready, mutation):
    record, _, verify = ready
    if mutation.startswith("sources"):
        record[mutation]["private.py"] = "c" * 64
    elif mutation == "specification":
        record["specification_sha256"] = "d" * 64
    else:
        record["actual_model_calls"] = 1 if mutation == "calls" else False
    with pytest.raises(ValueError):
        verify()


@pytest.mark.parametrize("mutation", ["filtered", "nonzero", "boolean_returncode", "failure",
    "skipped", "missing", "stderr", "no_summary"])
def test_readiness_requires_all_unfiltered_completed_tests(ready, mutation):
    record, _, verify = ready
    evidence = record["checks"]["complete_pipeline"]
    if mutation == "filtered":
        evidence["argv"] = evidence["argv"] + ["-k", "easy"]
    elif mutation in ("nonzero", "boolean_returncode"):
        evidence["returncode"] = 1 if mutation == "nonzero" else False
    elif mutation in ("failure", "skipped"):
        evidence["stdout"] = "1 failed\n5 passed in 2.00s\n" if mutation == "failure" else "1 skipped\n5 passed in 2.00s\n"
    elif mutation == "missing":
        record["checks"].pop("operating")
    elif mutation == "stderr":
        evidence["stderr"] = "unhandled exception"
    else:
        evidence["stdout"] = "test started"
    with pytest.raises(ValueError):
        verify()


def test_external_readiness_pin_cannot_be_recomputed_by_the_record(ready):
    _, path, verify = ready
    verify()
    with pytest.raises(ValueError, match="external readiness"):
        operating.readiness_check(path.parent, path, "0" * 64)


def test_actual_default_readiness_inventory_pins_implementation_and_whole_pipeline_tests():
    # Read-only actual source inventory, NOT a readiness record or test-pass claim.
    actual = operating.readiness_inventory(REPO)
    assert len(actual) > 58
    for name in ("paper3/retrospective_anticipation_operating.py",
        "paper3/hosted_reasoning_calls.py", "experiments/paper3_transport_diagnostic.py",
        "tests/test_paper3_retrospective_anticipation_complete_pipeline.py",
        "tests/test_paper3_retrospective_anticipation_operating.py"):
        assert actual[name] == operating.journal._digest(REPO / name)
