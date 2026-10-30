"""Post-terminal combined audit of both prespecified ratification batches.

Never run this as an interim batch-1 outcome report. Both exact terminal
audits and archives must verify before the 15-game behavioral gate is read.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path

from experiments import paper3_constituent_b_gptoss_action_gate as archive_source
from experiments import paper3_ratification_population_validation_batch1 as first
from experiments import paper3_ratification_population_validation_batch2 as second
from paper3 import ratification_population_holdout as holdout
from paper3 import ratification_population_schedule as schedule
from paper3.pivot_b_budget import Ledger


def _verified_batch(runner, root, archive):
    root, archive = Path(root), Path(archive)
    if not (root / "sessions/terminal.json").is_file():
        raise ValueError("holdout batch not terminal")
    _, protocol = runner.verify(root)
    helper = archive_source.archive_helpers()
    metadata = helper.verify_bundle(archive, protocol)
    if metadata["experiment_family"] != runner.STAGE:
        raise ValueError("wrong holdout archive family")
    actual = runner.audit(root)
    expected = runner.t.load(archive / "expected_report.json")
    if actual != expected or expected["protocol"] != protocol:
        raise ValueError("holdout archive/report mismatch")
    rows = runner.assignments()
    if [item["id"] for item in expected["assignments"]] != [
            row["id"] for row in rows]:
        raise ValueError("holdout assignment inventory changed")
    records = {}
    for row, summary in zip(rows, expected["assignments"], strict=True):
        saved = runner.t.load(root / "episodes" / (row["id"] + ".json"))
        if saved["id"] != row["id"] or saved["status"] != summary["status"]:
            raise ValueError("holdout episode status mismatch")
        records[row["id"]] = dict(
            complete=saved["status"] == "completed",
            outcome=saved.get("outcome"), failure=saved.get("error"),
            status=saved["status"])
    return dict(protocol=protocol, report=expected, records=records)


def readout(first_root, first_archive, second_root, second_archive,
            ledger_root=None):
    """Verify both complete batches before computing any behavioral outcome."""
    if not (Path(first_root) / "sessions/terminal.json").is_file() or not (
            Path(second_root) / "sessions/terminal.json").is_file():
        raise ValueError("both holdout batches must be terminal")
    first_batch = _verified_batch(first, first_root, first_archive)
    second_batch = _verified_batch(second, second_root, second_archive)
    records = dict(first_batch["records"])
    if set(records) & set(second_batch["records"]):
        raise ValueError("duplicate holdout assignment")
    records.update(second_batch["records"])
    if set(records) != {row["id"] for row in schedule.assignments("validation")}:
        raise ValueError("incomplete holdout assignment inventory")
    behavioral = holdout.readout(records)
    stages = []
    total = Decimal("0")
    for runner, batch in ((first, first_batch), (second, second_batch)):
        report = batch["report"]
        cost = Decimal(report["accounted_usd"])
        total += cost
        stages.append(dict(stage=runner.STAGE, protocol=batch["protocol"],
                           assignments=len(report["assignments"]),
                           completed_episodes=report["completed_episodes"],
                           usable_actions=report["usable_actions"],
                           feasibility_passed=report["feasibility_passed"],
                           accounted_usd=str(cost),
                           global_safety_stop=report["global_safety_stop"]))
    budget = Ledger(ledger_root or first.BUDGET).snapshot()
    if Decimal(budget["accounted_usd"]) >= Decimal("8"):
        raise ValueError("conservative $8 stop breached")
    return dict(stages=stages, combined_stage_cost_usd=str(total),
                conservative_budget=budget, behavioral=behavioral,
                strict_holdout_lead=behavioral["strict_holdout_lead"],
                caveat="Fifteen opportunity-conditioned synthetic payoff games on one model. A passing action gate is not independent model replication or a real-election claim; two-compromise choice has a known coalition-size/welfare confound.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_root", type=Path)
    parser.add_argument("first_archive", type=Path)
    parser.add_argument("second_root", type=Path)
    parser.add_argument("second_archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(readout(args.first_root, args.first_archive,
                             args.second_root, args.second_archive), indent=2))


if __name__ == "__main__":
    main()
