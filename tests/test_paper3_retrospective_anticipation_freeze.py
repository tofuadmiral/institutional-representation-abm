"""Private/copied source freezes only: never actual allocation or launch."""
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from paper3 import retrospective_anticipation_freeze as freeze
from paper3 import retrospective_extended_budget as budget
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_anticipation_operating as operating
from paper3.pivot_b_budget import atomic
from paper3.source_closure import closure

REPO = Path(__file__).resolve().parents[1]
OLD = REPO / "results/paper3/pivot_b_retrospective_score_ledger_gate_v1"


def approved():
    return {name: True for name in freeze.APPROVAL_FIELDS}  # FABRICATED test approval only.


def metadata():
    return deepcopy(journal.load(OLD / "manifest.json")["protocol"]["endpoint_metadata"])


@pytest.fixture
def private(tmp_path, monkeypatch):
    repo, ledger = tmp_path / "code", tmp_path / "ledger"
    for source in closure(REPO, freeze.source_roots(REPO)):
        target = repo / source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    ledger.mkdir()
    (ledger / "entries").mkdir()
    for name in budget.AUTHORITY_FILES:
        shutil.copy2(REPO / "results/paper3/pivot_b_budget" / name, ledger / name)
    monkeypatch.setattr(freeze.design, "seed_audit", lambda repo: dict(overlap=[], historical_files=0,
        inventory_sha256="a" * 64, fabricated=True))
    def fabricated_proof(*args, **kwargs):
        assert kwargs == dict(allow_menu_bound_instantiation=True)
        return dict(compared_assignments=16, compared_slots=480, slots_with_declared_menu_delta=256,
            literal_full_schema_equal=False, native_system_and_template_compatible=True,
            inheritance_authorized=False, fabricated=True)
    monkeypatch.setattr(freeze.qualification, "prove", fabricated_proof)
    return tmp_path / "frozen", repo, ledger


def prepare(private, **kwargs):
    root, repo, ledger = private
    return freeze.prepare(root, repo, ledger, "unused-fabricated-qualified", "unused-fabricated-zip",
                          approval=kwargs.pop("approval", approved()),
                          metadata=kwargs.pop("metadata", metadata()), **kwargs)


def test_private_freeze_pins_complete_cases_sources_analysis_and_all_old_evidence(private):
    protocol = prepare(private)
    root, repo, ledger = private
    manifest, reproduced = freeze.verify(root, repo, protocol)
    assert reproduced == protocol
    spec = journal.decode(manifest["specification"])
    assert len(spec["assignments"]) == 16
    assert spec["bound"]["logical_calls"] == 480 and spec["bound"]["maximum_physical_calls"] == 482
    assert len(manifest["sources"]) > 58
    assert "paper3/retrospective_anticipation_audit.py" in manifest["sources"]
    assert "results/paper3/pivot_b_retrospective_score_ledger_gate_v1/manifest.json" in manifest["sources"]
    assert "results/paper3/pivot_b_retrospective_score_ledger_gate_v1/sources.json" in manifest["sources"]
    assert not (ledger / "stages").exists() and not list((ledger / "entries").iterdir())
    assert manifest["actual_model_calls"] == 0 and not manifest["launch_authorized"]
    with pytest.raises(ValueError, match="never restart"):
        prepare(private)


@pytest.mark.parametrize("field", sorted(freeze.APPROVAL_FIELDS))
def test_missing_specific_scope_approval_refuses_creation(private, field):
    value = approved()
    value[field] = False
    with pytest.raises(ValueError, match="scope approval"):
        prepare(private, approval=value)
    assert not private[0].exists()


def test_insufficient_full_pilot_budget_refuses_partial_freeze_before_proof(private, monkeypatch):
    root, _, ledger = private
    atomic(ledger / "entries/old.json", dict(stage="old", status="reserved", reserved_usd="9.608958611"))
    before = (ledger / "entries/old.json").read_bytes()
    monkeypatch.setattr(freeze.qualification, "prove", lambda *a, **k: pytest.fail("must deny budget first"))
    with pytest.raises(ValueError, match="full16-assignment budget"):
        prepare(private)
    assert not root.exists() and not (ledger / "stages").exists()
    assert (ledger / "entries/old.json").read_bytes() == before


def test_old_uncertified_reservations_are_pinned_without_release(private):
    _, _, ledger = private
    atomic(ledger / "entries/old.json", dict(stage="old", status="settled", reserved_usd=".5",
        accounted_usd=".5", certified=False))
    before = (ledger / "entries/old.json").read_bytes()
    prepare(private)
    manifest = journal.load(private[0] / "manifest.json")
    assert manifest["pre_stage_accounted_usd"] == "0.5"
    assert set(manifest["prior_entries"]) == {"old.json"}
    assert before == (ledger / "entries/old.json").read_bytes()


@pytest.mark.parametrize("mutation", ("native", "schema", "analysis", "inventory", "old_manifest", "budget"))
def test_modified_or_removed_source_is_not_a_compatible_freeze(private, mutation):
    protocol = prepare(private)
    root, repo, _ = private
    name = dict(native="paper3/retrospective_contract_route_v2.py",
        schema="paper3/retrospective_score_ledger_budget.py",
        analysis="paper3/retrospective_anticipation_analysis.py",
        inventory="paper3/retrospective_anticipation_design.py",
        old_manifest="results/paper3/pivot_b_retrospective_score_ledger_gate_v1/manifest.json",
        budget="paper3/retrospective_extended_budget.py")[mutation]
    path = repo / name
    # These are PRIVATE COPIES, never frozen files in the actual repository.
    path.write_bytes(path.read_bytes() + b"\n ")
    with pytest.raises(ValueError):
        freeze.verify(root, repo, protocol)


@pytest.mark.parametrize("mutation", ("source_deleted", "specification", "approval", "partial"))
def test_missing_inventory_or_modified_protocol_and_partial_writes_rejected(private, mutation):
    protocol = prepare(private)
    root, repo, _ = private
    manifest = journal.load(root / "manifest.json")
    if mutation == "source_deleted":
        manifest["sources"].pop(next(iter(manifest["sources"])))
    elif mutation == "specification":
        spec = journal.decode(manifest["specification"])
        spec["minimum_effect"] /= 2
        manifest["specification"] = journal.encode(spec)
    elif mutation == "approval":
        manifest["approval"]["declared_menu_bound_policy"] = False
    else:
        (root / "sources.partial").write_text("fabricated interrupted write")
    atomic(root / "manifest.json", manifest)
    with pytest.raises(ValueError):
        freeze.verify(root, repo, protocol)


def test_unhealthy_route_rejected_without_any_metadata_fetch_or_root(private):
    value = metadata()
    endpoint = next(r for r in value["data"]["endpoints"] if r["tag"] == freeze.route.TAG)
    endpoint["status"] = -2
    with pytest.raises(ValueError, match="status"):
        prepare(private, metadata=value)
    assert not private[0].exists()


@pytest.mark.parametrize("field", ("qualification_proof", "prior_entries", "endpoint_metadata"))
def test_external_pin_covers_data_not_only_source_and_analysis(private, field):
    protocol = prepare(private)
    root, repo, _ = private
    manifest = journal.load(root / "manifest.json")
    manifest[field] = {"forged": True}
    atomic(root / "manifest.json", manifest)
    with pytest.raises(ValueError, match="external freeze protocol"):
        freeze.verify(root, repo, protocol)


def test_returned_specifications_cannot_mutate_the_cached_reference():
    first = freeze.specification()
    old = journal.canonical(first)
    decoded = journal.decode(first)
    decoded["minimum_effect"] /= 2
    first.clear()
    assert journal.canonical(freeze.specification()) == old
    assert journal.canonical(journal.encode(decoded)) != old


def fabricated_readiness(private):
    """PRIVATE test output, never genuine readiness or human authority."""
    _, repo, _ = private
    paths = [REPO / command[3] for command in operating.REQUIRED_CHECKS.values()]
    for source in closure(REPO, paths):
        target = repo / source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    sources = operating.readiness_inventory(repo)
    record = dict(format=operating.READINESS_FORMAT, sources_before=sources, sources_after=sources,
        specification_sha256=journal.physical.t.sha(journal.canonical(freeze.specification()).encode()),
        checks={name:dict(argv=command, returncode=0, stdout=".....\n5 passed in 0.01s\n", stderr="")
                for name, command in operating.REQUIRED_CHECKS.items()}, actual_model_calls=0)
    path = repo / freeze.READINESS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic(path, record)
    return dict(path=freeze.READINESS_FILE, sha256=journal._digest(path))


def test_private_operating_freeze_pins_readiness_and_all_referenced_test_sources(private):
    pin = fabricated_readiness(private)
    protocol = prepare(private, operating_readiness=pin)
    root, repo, _ = private
    manifest, _ = freeze.verify(root, repo, protocol)
    assert manifest["operating_readiness"] == pin
    assert manifest["sources"][freeze.READINESS_FILE] == pin["sha256"]
    for command in operating.REQUIRED_CHECKS.values():
        assert manifest["sources"][command[3]] == journal._digest(repo / command[3])
    assert not manifest["launch_authorized"] and not manifest["allocation_authorized"]
    assert not operating.readiness_check(repo, repo / pin["path"], pin["sha256"])["launch_authorized"]


def test_modified_private_operating_readiness_refuses_before_freeze(private):
    pin = fabricated_readiness(private)
    path = private[1] / pin["path"]
    path.write_bytes(path.read_bytes() + b"\n ")  # PRIVATE copy only.
    with pytest.raises(ValueError, match="external readiness"):
        prepare(private, operating_readiness=pin)
    assert not private[0].exists() and not (private[2] / "stages").exists()


def test_private_readiness_modified_after_freeze_fails_external_source_pin(private):
    pin = fabricated_readiness(private)
    protocol = prepare(private, operating_readiness=pin)
    path = private[1] / pin["path"]
    path.write_bytes(path.read_bytes() + b"\n ")  # PRIVATE copy only.
    with pytest.raises(ValueError, match="readiness file changed"):
        freeze.verify(private[0], private[1], protocol)


@pytest.mark.parametrize("path", [".env.local", "../private.json", "/tmp/anything.json"])
def test_arbitrary_operating_readiness_path_cannot_enter_freeze(private, path):
    with pytest.raises(ValueError, match="exact prospective readiness"):
        prepare(private, operating_readiness=dict(path=path, sha256="a" * 64))
    assert not private[0].exists()


def test_actual_qualification_and_private_source_freeze_verify_in_fresh_isolated_python(tmp_path):
    # Genuine old qualification audit, PRIVATE EMPTY financial ledger, fabricated
    # scope approval and HISTORICAL route metadata. No real pilot/route observation.
    ledger, root, code = tmp_path / "ledger", tmp_path / "private-freeze", tmp_path / "copied-code"
    ledger.mkdir()
    (ledger / "entries").mkdir()
    for name in budget.AUTHORITY_FILES:
        shutil.copy2(REPO / "results/paper3/pivot_b_budget" / name, ledger / name)
    qualified = REPO / "paper3/data/pivot_b_retrospective_score_ledger_gate_v1"
    protocol = freeze.prepare(root, REPO, ledger, qualified, qualified.with_suffix(".zip"),
                              approval=approved(), metadata=metadata())
    manifest, _ = freeze.verify(root, REPO, protocol)
    proof = journal.decode(manifest["qualification_proof"])
    assert proof["full_gate_passed"] and proof["compared_slots"] == 480
    for name, value in journal.load(root / "sources.json").items():
        target = code / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)
    command = """import sys
sys.dont_write_bytecode = True
def offline(event, args):
    if event.startswith(('socket.', 'urllib.', 'subprocess.')):
        raise RuntimeError('network forbidden')
sys.addaudithook(offline)
import socket
try:
    socket.getaddrinfo('127.0.0.1', 1)
except RuntimeError:
    pass
else:
    raise RuntimeError('network guard failed')
sys.path.insert(0, sys.argv[1])
from paper3 import retrospective_anticipation_freeze as frozen
value, digest = frozen.verify(sys.argv[2], sys.argv[1], sys.argv[3])
assert value['actual_model_calls'] == 0 and value['launch_authorized'] is False
print(digest)
"""
    child = subprocess.run([sys.executable, "-I", "-S", "-c", command, str(code), str(root), protocol],
                           cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == protocol
    assert not (ledger / "stages").exists() and not list((ledger / "entries").iterdir())
