"""Offline configuration comparison only; never new gate or launch evidence."""
from copy import deepcopy
from pathlib import Path
import json
import shutil
import subprocess
import sys
import zipfile

import pytest

from paper3 import retrospective_qualification_inheritance as proof
from paper3 import retrospective_score_ledger_qualification as qualification
from paper3 import retrospective_score_ledger_budget as budget
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_anticipation_design as design
from paper3.source_closure import closure
from paper3.pivot_b_budget import atomic


def request(phase):
    case = next(c for c in qualification.cases() if c["kind"] == "action" and c["stage"] == phase)
    value = next(c["request"] for c in qualification.requests() if c["context"]["case_id"] == case["id"])
    return deepcopy(value)


def larger(phase):
    value = request(phase)
    value["seed"] = 3850000
    if phase != "vote":
        field = "counter_policy" if phase == "response" else "policy"
        value["tools"][0]["function"]["parameters"]["properties"][field]["maximum"] = 5
    return value


@pytest.mark.parametrize("phase", ("draft", "response", "final", "vote"))
def test_exact_qualification_task_fragments_match_new_wrapper(phase):
    case = next(c for c in qualification.cases() if c["kind"] == "action" and c["stage"] == phase)
    rebuilt = route.request(budget.structured(case["messages"], case["game"], phase), 3850000)
    report = proof.compare(request(phase), rebuilt, qualified_width=4, task_width=4, phase=phase)
    assert report["literal_full_schema_equal"] and report["native_equal"]
    assert not report["inheritance_authorized"]


@pytest.mark.parametrize("phase", ("draft", "response", "final", "vote"))
def test_only_explicit_menu_bound_inspection_permitted_never_hidden_waiver(phase):
    reference, proposed = request(phase), larger(phase)
    before = deepcopy(proposed)
    if phase != "vote":
        with pytest.raises(ValueError, match="explicit policy required"):
            proof.compare(reference, proposed, qualified_width=4, task_width=6, phase=phase)
    report = proof.compare(reference, proposed, qualified_width=4, task_width=6, phase=phase,
                           allow_menu_bound_instantiation=True)
    assert report["literal_full_schema_equal"] is (phase == "vote")
    assert len(report["declared_task_deltas"]) == (0 if phase == "vote" else 1)
    assert not report["qualification_at_task_width_established"]
    assert not report["inheritance_authorized"] and proposed == before


@pytest.mark.parametrize("mutation", ("model", "provider", "reasoning", "temperature", "output", "force",
    "system", "extra", "tool_name", "description", "message_limit", "additional", "policy_float", "seed_bool"))
def test_task_bound_policy_never_hides_other_interface_or_native_changes(mutation):
    reference, value = request("draft"), larger("draft")
    f = value["tools"][0]["function"]
    if mutation == "model":
        value["model"] = "different-model"
    elif mutation == "provider":
        value["provider"]["allow_fallbacks"] = True
    elif mutation == "reasoning":
        value["reasoning"]["enabled"] = 1
    elif mutation == "temperature":
        value["temperature"] = .7
    elif mutation == "output":
        value["max_tokens"] -= 1
    elif mutation == "force":
        value["tool_choice"] = "required"
    elif mutation == "system":
        value["messages"][0]["content"] += "changed"
    elif mutation == "extra":
        value["new_option"] = True
    elif mutation == "tool_name":
        f["name"] = "different"
    elif mutation == "description":
        f["description"] = "different"
    elif mutation == "message_limit":
        f["parameters"]["properties"]["message"]["maxLength"] += 1
    elif mutation == "additional":
        f["parameters"]["additionalProperties"] = True
    elif mutation == "policy_float":
        f["parameters"]["properties"]["policy"]["maximum"] = 5.0
    else:
        value["seed"] = True
    with pytest.raises(ValueError):
        proof.compare(reference, value, qualified_width=4, task_width=6, phase="draft",
                      allow_menu_bound_instantiation=True)


@pytest.mark.parametrize("policy", (1, "true", None))
def test_inspection_policy_is_not_coerced(policy):
    with pytest.raises(ValueError):
        proof.compare(request("draft"), larger("draft"), qualified_width=4, task_width=6,
                      phase="draft", allow_menu_bound_instantiation=policy)


def test_real_pinned_gate_archive_recomputed_read_only_and_template_inspected():
    repo = Path(__file__).resolve().parents[1]
    directory = repo / "paper3/data/pivot_b_retrospective_score_ledger_gate_v1"
    archive = directory.with_suffix(".zip")
    case = next(c for c in qualification.cases() if c["kind"] == "action")
    items = (dict(id="offline-qualified-game", game=case["game"], arm=case["arm"], seed_base=3950000),)
    before = proof.file_sha(archive)
    report = proof.prove(directory, archive, items)
    assert report["full_gate_passed"] and report["literal_full_schema_equal"]
    assert report["qualified_payload_files"] == 6688 and report["compared_slots"] == 30
    assert not report["launch_authorized"] and not report["inheritance_authorized"]
    assert report["actual_model_calls"] == 0
    assert proof.file_sha(archive) == before


def test_full_fresh_inventory_compatibility_in_actual_isolated_extracted_source_snapshot(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    directory = repo / "paper3/data/pivot_b_retrospective_score_ledger_gate_v1"
    qualified_zip = directory.with_suffix(".zip")
    report = proof.prove(directory, qualified_zip, design.assignments(), allow_menu_bound_instantiation=True)
    assert report["compared_assignments"] == 16 and report["compared_slots"] == 480
    assert report["slots_with_declared_menu_delta"] == 256 and not report["literal_full_schema_equal"]
    assert not report["inheritance_authorized"] and not report["launch_authorized"]
    bundle = tmp_path / "bundle"
    shutil.copytree(directory, bundle / "qualification")
    shutil.copy2(qualified_zip, bundle / "qualification.zip")
    shutil.copytree(directory / "code", bundle / "code")  # All original58 sources/assets intact.
    sources = closure(repo, [repo / "analysis/paper3_qualification_compatibility.py",
                             repo / "analysis/paper3_contracts_archive.py"])
    for path in sources:
        target = bundle / "code" / path.relative_to(repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    inventory = {p.relative_to(bundle / "code").as_posix(): proof.file_sha(p)
                 for p in sorted((bundle / "code").rglob("*")) if p.is_file()}
    atomic(bundle / "sources.json", inventory)
    archive = tmp_path / "compatibility.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(bundle).as_posix())
    extracted = tmp_path / "fresh"
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(extracted)  # Own fabricated engineering archive, no untrusted input.
    command = [sys.executable, "-I", "-S", str(extracted / "code/analysis/paper3_qualification_compatibility.py"),
        str(extracted / "qualification"), "--qualified-zip", str(extracted / "qualification.zip"),
        "--sources", str(extracted / "sources.json"), "--sources-sha256", proof.file_sha(bundle / "sources.json"),
        "--expected-proof-sha256", proof.sha256(proof.canonical(report).encode()).hexdigest(),
        "--allow-menu-bound-instantiation"]
    child = subprocess.run(command, cwd=extracted, capture_output=True, text=True, timeout=60)
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    assert result["full_proof_matched"] and result["source_snapshot_verified"]
    assert result["network_guard_self_test"] and result["compared_slots"] == 480
    assert not result["literal_full_schema_equal"] and result["slots_with_declared_menu_delta"] == 256
    assert not result["inheritance_authorized"] and not result["launch_authorized"]
    # Optional comparison must fail without the explicit offline task-bound policy.
    rejected = subprocess.run(command[:-1], cwd=extracted, capture_output=True, text=True, timeout=60)
    assert rejected.returncode != 0 and "explicit policy required" in rejected.stderr


@pytest.mark.parametrize("mutation", ("extra", "deleted", "changed", "pin"))
def test_source_snapshot_requires_exact_external_pin_and_every_file(tmp_path, mutation):
    from analysis.paper3_qualification_compatibility import source_snapshot
    code = tmp_path / "code"
    code.mkdir()
    path = code / "module.py"
    path.write_text("# fabricated offline source\n")
    inventory = tmp_path / "sources.json"
    atomic(inventory, {"module.py": proof.file_sha(path)})
    pin = proof.file_sha(inventory)
    if mutation == "extra":
        (code / "unknown.py").write_text("# unknown\n")
    elif mutation == "deleted":
        path.unlink()
    elif mutation == "changed":
        path.write_text("# changed\n")
    else:
        pin = "0" * 64
    with pytest.raises(ValueError):
        source_snapshot(code, inventory, pin)


def test_source_snapshot_does_not_silently_decode_duplicate_inventory_keys(tmp_path):
    from analysis.paper3_qualification_compatibility import source_snapshot
    code = tmp_path / "code"
    code.mkdir()
    path = code / "module.py"
    path.write_text("# fabricated source\n")
    digest = proof.file_sha(path)
    inventory = tmp_path / "sources.json"
    inventory.write_text('{"module.py":"' + digest + '","module.py":"' + digest + '"}')
    with pytest.raises(ValueError, match="duplicate source"):
        source_snapshot(code, inventory, proof.file_sha(inventory))


def test_unlisted_symlink_directory_cannot_shadow_imports_outside_snapshot(tmp_path):
    from analysis.paper3_qualification_compatibility import source_snapshot
    code = tmp_path / "code"
    code.mkdir()
    path = code / "module.py"
    path.write_text("# fabricated source\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (code / "unlisted-package").symlink_to(outside, target_is_directory=True)
    inventory = tmp_path / "sources.json"
    atomic(inventory, {"module.py": proof.file_sha(path)})
    with pytest.raises(ValueError, match="symlink"):
        source_snapshot(code, inventory, proof.file_sha(inventory))
