"""Private copied sources/financial history; fabricated proof, no live freeze/API."""
from copy import deepcopy
from pathlib import Path
import shutil

import pytest

from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_recovery_freeze_v2 as freeze
from paper3.pivot_b_budget import atomic
from paper3.retrospective_source_closure import closure

REPO = Path(__file__).resolve().parents[1]
SOURCE_LEDGER = REPO / "results/paper3/pivot_b_budget"
OLD = REPO / "results/paper3/pivot_b_retrospective_score_ledger_gate_v1"


def metadata():
    return deepcopy(journal.load(OLD / "manifest.json")["protocol"]["endpoint_metadata"])


@pytest.fixture
def private(tmp_path, monkeypatch):
    repo, ledger = tmp_path / "code", tmp_path / "ledger"
    for source in closure(REPO, freeze.source_roots(REPO)):
        target = repo / source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Includes real preserved incurred history and exact retirement; mutations
    # below affect ONLY this private copy, never the actual program ledger.
    shutil.copytree(SOURCE_LEDGER, ledger)
    monkeypatch.setattr(freeze.design, "seed_audit", lambda repo, **k: dict(
        overlap=[], historical_files=0, inventory_sha256="a" * 64, fabricated=True))
    def fabricated_proof(*args, **kwargs):
        assert kwargs == dict(allow_menu_bound_instantiation=True)
        return dict(compared_assignments=16, compared_slots=480, slots_with_declared_menu_delta=256,
            literal_full_schema_equal=False, native_system_and_template_compatible=True,
            inheritance_authorized=False, fabricated=True)
    monkeypatch.setattr(freeze.qualification, "prove", fabricated_proof)
    return tmp_path / "frozen", repo, ledger


def prepare(private, **kwargs):
    return freeze.prepare(*private, "fabricated-qualified-directory", "fabricated-qualified-zip",
                          metadata=kwargs.pop("metadata", metadata()), **kwargs)


def test_complete_private_freeze_and_source_verification_preserve_every_incurred_entry(private):
    root, repo, ledger = private
    before = freeze.inventory(ledger)
    protocol = prepare(private)
    manifest, reproduced = freeze.verify(root, repo, protocol)
    spec = journal.decode(manifest["specification"])
    assert reproduced == protocol and len(spec["assignments"]) == 16
    assert spec["bound"]["logical_calls"] == 480 and spec["bound"]["maximum_physical_calls"] == 560
    assert spec["total_cap_usd"] == "17.00" and spec["recovery"]["maximum_reissues_per_block"] == 40
    assert manifest["retirement_pins"] == freeze.RETIREMENT_PINS
    assert manifest["pre_stage_accounted_usd"] == "6.828589091"
    assert freeze.inventory(ledger) == before and len(before) == 6556
    assert not (ledger / freeze.budget.GROUPS).exists()
    assert not manifest["launch_authorized"] and manifest["operating_readiness"] is None
    assert len(manifest["sources"]) > 88
    with pytest.raises(ValueError, match="never restart"):
        prepare(private)


@pytest.mark.parametrize("name", (
    "paper3/retrospective_recovery_calls_v2.py",
    "paper3/retrospective_recovery_design_v2.py",
    "paper3/retrospective_recovery_coordinator_v2.py",
    "paper3/retrospective_anticipation_analysis.py",
    "paper3/retrospective_contract_route_v2.py",
    freeze.AUTHORIZATION_FILE,
    "results/paper3/pivot_b_budget/authority_extension_2026_10_05.json"))
def test_private_source_or_authority_mutation_cannot_pass_freeze(private, name):
    protocol = prepare(private)
    path = private[1] / name
    path.write_bytes(path.read_bytes() + b"\n ")  # PRIVATE copy only.
    with pytest.raises(ValueError):
        freeze.verify(private[0], private[1], protocol)


@pytest.mark.parametrize("field", ("retirement_pins", "prior_entries", "qualification_proof",
                                    "specification", "operating_authorization"))
def test_external_protocol_pins_data_as_well_as_source(private, field):
    protocol = prepare(private)
    path = private[0] / "manifest.json"
    record = journal.load(path)
    record[field] = {"forged": True}
    atomic(path, record)
    with pytest.raises(ValueError, match="external recovery protocol"):
        freeze.verify(private[0], private[1], protocol)


def test_retirement_tamper_refuses_before_private_root_creation(private):
    path = private[2] / freeze.retirement.DIRECTORY / (freeze.retirement.STAGE + ".json")
    path.write_bytes(path.read_bytes() + b"\n ")
    with pytest.raises(ValueError, match="retirement certificate"):
        prepare(private)
    assert not private[0].exists()


def test_new_account_cannot_erase_uncertified_history_or_fit_partial_study(private, monkeypatch):
    _, _, ledger = private
    before = freeze.inventory(ledger)
    atomic(ledger / "entries/private-extra.json", dict(stage="private-extra", status="reserved", reserved_usd="2"))
    monkeypatch.setattr(freeze.qualification, "prove", lambda *a, **k: pytest.fail("budget must deny first"))
    with pytest.raises(ValueError, match="full16-assignment recovery budget"):
        prepare(private)
    assert not private[0].exists() and not (ledger / freeze.budget.GROUPS).exists()
    after = freeze.inventory(ledger)
    assert all(after[name] == digest for name, digest in before.items())


def test_unhealthy_exact_route_denied_without_private_freeze_or_network(private):
    value = metadata()
    next(r for r in value["data"]["endpoints"] if r["tag"] == freeze.route.TAG)["status"] = -2
    with pytest.raises(ValueError, match="status"):
        prepare(private, metadata=value)
    assert not private[0].exists()


def test_mutable_return_cannot_change_fixed_specification():
    before = journal.canonical(freeze.specification())
    value = freeze.specification()
    value.clear()
    assert journal.canonical(freeze.specification()) == before


def test_partial_persistence_cannot_be_reprepared_or_verified(private):
    protocol = prepare(private)
    (private[0] / "sources.partial").write_text("private fabricated interruption")
    with pytest.raises(ValueError, match="interrupted freeze"):
        freeze.verify(private[0], private[1], protocol)
    with pytest.raises(ValueError, match="never restart"):
        prepare(private)
