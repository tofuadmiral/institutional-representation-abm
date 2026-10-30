"""GENUINE old gate + PRIVATE pilot/ledger + FABRICATED failed actions; no API.

Actually export/extract/execute bundled Python -I -S. Engineering evidence only:
not new qualification, behavioral success, financial authority or model calls.
"""
from pathlib import Path
import shutil
import subprocess

import pytest

from paper3 import retrospective_anticipation_archive as archive
from paper3 import retrospective_anticipation_coordinator as coordinator
from paper3 import retrospective_anticipation_freeze as freeze
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_extended_budget as budget
from tests import test_paper3_retrospective_anticipation_coordinator as fabricated
from tests import test_paper3_retrospective_anticipation_freeze as copied

REPO = Path(__file__).resolve().parents[1]
QUALIFIED = REPO / "paper3/data/pivot_b_retrospective_score_ledger_gate_v1"


@pytest.fixture(scope="module")
def partial(tmp_path_factory):
    base = tmp_path_factory.mktemp("anticipation-production-replay")
    root, ledger = base / "run", base / "ledger"
    ledger.mkdir()
    (ledger / "entries").mkdir()
    for name in budget.AUTHORITY_FILES:
        shutil.copy2(REPO / "results/paper3/pivot_b_budget" / name, ledger / name)
    protocol = freeze.prepare(root, REPO, ledger, QUALIFIED, QUALIFIED.with_suffix(".zip"),
                              approval=copied.approved(), metadata=copied.metadata())
    options, sent = fabricated.hooks()
    report = coordinator.run_block(root, REPO, ledger, protocol, 0, **options)
    assert len(sent) == 8 and report["blocks"][0]["evidence"]["report"]["content_failed"] == 8
    assert report["assigned"] == 16 and report["blocks"][1]["status"] == "not_launched"
    target, zipped = base / "batch0", base / "batch0.zip"
    certificate = archive.export(root, REPO, ledger, protocol, QUALIFIED,
        QUALIFIED.with_suffix(".zip"), target, zipped)
    return dict(base=base, root=root, ledger=ledger, protocol=protocol, report=report,
                target=target, zipped=zipped, certificate=certificate)


def test_actual_fresh_production_replay_matches_entire_partial_and_genuine_qualification(partial):
    cert, report = partial["certificate"], partial["report"]
    assert cert["report_sha256"] == archive.report_sha(report)
    assert cert["isolated_report_matched"] and cert["network_guard_self_test"]
    assert cert["genuine_qualification_reproduced"] and not cert["publication_evidence"]
    assert report["budget"]["entries"] == report["budget"]["uncertified"] == 8
    assert report["analysis"]["first_terms_complete"] == 0
    metadata = archive.portable.verify_bundle(partial["target"], partial["protocol"])
    assert metadata["experiment_family"] == archive.FAMILY
    assert "code/" + archive.ENTRY in metadata["files"]
    assert "qualified.zip" in metadata["files"]
    assert "ledger/ledger.lock" in metadata["files"]


def test_actual_partial_replay_can_certify_second_frame_regardless_of_bad_content(partial):
    root, ledger, protocol = partial["root"], partial["ledger"], partial["protocol"]
    end = journal.load(root / "sessions/block-0-terminal.json")
    options, sent = fabricated.hooks(started=end["completed_unix"] + 1)
    options["certify_partial"] = lambda report: dict(partial["certificate"])
    report = coordinator.run_block(root, REPO, ledger, protocol, 1, **options)
    assert len(sent) == 8 and report["budget"]["entries"] == 16
    assert report["analysis"]["candidate_screen"]["status"] == "incomplete_first_term"
    assert all(row["evidence"]["report"]["content_failed"] == 8 for row in report["blocks"])
    target, zipped = partial["base"] / "complete", partial["base"] / "complete.zip"
    certificate = archive.export(root, REPO, ledger, protocol, QUALIFIED,
        QUALIFIED.with_suffix(".zip"), target, zipped)
    assert certificate["report_sha256"] == archive.report_sha(report)
    assert certificate["isolated_report_matched"] and certificate["genuine_qualification_reproduced"]


def test_parent_checkout_cannot_claim_fresh_isolated_replay(partial):
    with pytest.raises(ValueError, match="fresh isolated bundled"):
        archive.replay(partial["target"], partial["protocol"])


def test_existing_archive_cannot_be_replaced(partial):
    with pytest.raises(ValueError, match="archive exists"):
        archive.export(partial["root"], REPO, partial["ledger"], partial["protocol"],
            QUALIFIED, QUALIFIED.with_suffix(".zip"), partial["target"], partial["zipped"])


def test_wrong_external_protocol_cannot_certify(partial):
    with pytest.raises(ValueError, match="unexpected protocol"):
        archive.isolated_certificate(partial["target"], partial["zipped"], "0"*64)


def test_zip_payload_change_cannot_certify(partial, tmp_path):
    import zipfile
    damaged = tmp_path / "damaged.zip"
    with zipfile.ZipFile(partial["zipped"]) as source, zipfile.ZipFile(damaged, "x") as dest:
        for name in source.namelist():
            data = source.read(name)
            dest.writestr(name, data + b" " if name == "expected_report.json" else data)
    with pytest.raises(ValueError, match="ZIP payload differs"):
        archive.isolated_certificate(partial["target"], damaged, partial["protocol"])


def test_credential_scan_rejects_without_echoing_the_key():
    fabricated_secret = "sk-or-v1-" + "z"*40
    with pytest.raises(ValueError) as error:
        archive.portable.credentials(fabricated_secret.encode())
    assert fabricated_secret not in str(error.value)


def test_replay_entry_requires_isolation(tmp_path):
    child = subprocess.run([str(REPO / ".venv/bin/python"), str(REPO / archive.ENTRY), str(tmp_path),
        "--expected-protocol", "0"*64], capture_output=True, text=True)
    assert child.returncode != 0 and "use fresh Python -I -S" in child.stderr
