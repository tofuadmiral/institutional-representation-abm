"""Offline all-assignment scientific readout AFTER physical/journal replay.

No transport, preparation, source freeze, financial release or launch authority.
Both prospectively assigned frame blocks remain, including an explicitly unrun
block. Completed first terms may be observed with unfinished second terms.
Only the public journal audit supplies observations; cached summaries are unused.
"""
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_deepinfra_journal_v2 as replay


def audit(assignments, blocks, protocol, *, verify, minimum_effect, aligned_fraction):
    """Two fixed frame blocks, audited independently, then joined without filtering.

Each block explicitly supplies seed, root (None means NOT LAUNCHED), ledger,
stage. None never licenses another launch or substitutes
for checking a possibly started process. Caller must establish that provenance.
Any present but interrupted/invalid block raises, retaining its source evidence;
it cannot be replaced by a null block or a cached result.
"""
    frames = science.validate(assignments, {a["id"]: (None, None) for a in assignments})
    institution.require(type(blocks) is tuple and len(blocks) == 2 and
        all(type(b) is dict and set(b) == {"seed", "root", "ledger", "stage"}
            and type(b["seed"]) is int for b in blocks) and
        tuple(sorted(b["seed"] for b in blocks)) == frames, "both prospectively assigned frame blocks")
    journal._guard(verify, protocol)
    present = [b for b in blocks if b["root"] is not None]
    institution.require(len({str(Path(b["root"]).resolve()) for b in present}) == len(present) and
        len({b["stage"] for b in present}) == len(present), "distinct block roots and financial stages")
    observations, block_reports = {}, []
    physical_cost = Decimal(0)
    for block in blocks:
        items = tuple(a for a in assignments if a["seed"] == block["seed"])
        institution.require(len(items) == 8, "entire eight-assignment frame block")
        if block["root"] is None:
            observations.update({a["id"]: (None, None) for a in items})
            block_reports.append(dict(seed=block["seed"], status="not_launched",
                assigned_ids=tuple(a["id"] for a in items), evidence=None))
            continue
        evidence = replay.audit(block["root"], block["ledger"], block["stage"], items, protocol,
            verify=verify)
        result = evidence["report"]
        rows = result["assignments"]
        institution.require(type(rows) is tuple and len(rows) == 8 and
            tuple(r["id"] for r in rows) == tuple(a["id"] for a in items) and result["assigned"] == 8,
            "replayed complete block inventory/order")
        for assignment, row in zip(items, rows, strict=True):
            institution.require(row["arm"] == assignment["arm"] and
                type(row["seed_base"]) is int and row["seed_base"] == assignment["seed_base"] and
                journal.canonical(row["game"]) == journal.canonical(asdict(assignment["game"])) and
                type(row["terms"]) is list and len(row["terms"]) == 2,
                "replayed economic game, arm, paired seed and both terms")
            observations[row["id"]] = tuple(row["terms"])
        cost = Decimal(evidence["physical_accounted_usd"])
        institution.require(cost.is_finite() and cost >= 0, "full physical accounting")
        physical_cost += cost
        block_reports.append(dict(seed=block["seed"], status="audited_terminal",
            assigned_ids=tuple(a["id"] for a in items), evidence=evidence))
    journal._guard(verify, protocol)
    analysis = science.analyze(assignments, observations,
        minimum_effect=minimum_effect, aligned_fraction=aligned_fraction)
    return dict(protocol=protocol, blocks=tuple(block_reports), analysis=analysis,
        full_physical_accounted_usd=str(physical_cost), assigned=16,
        actual_new_model_calls=0, allocation_authorized=False, frozen_protocol=False,
        publication_evidence=False,
        limitation="Audited selected-case readout only. Unrun cases remain missing; "
        "source/authority/qualification freeze and independent validation are separate. "
        "A behavioral lead is not proof of motive or a population/publication result.")
