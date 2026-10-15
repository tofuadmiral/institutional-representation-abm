"""Fresh candidate inventory/pricing, OFFLINE only; no preparation or calls.

Seeds are fixed here before model outcomes. The existing exogenous conditional
generator is unchanged. This is a design draft, not human launch/budget approval
or a frozen confirmatory protocol. No historical case is replaced/reopened.
"""
from dataclasses import replace
from decimal import Decimal
from functools import cache
import os
from pathlib import Path
from random import Random

from experiments import paper3_transport_diagnostic as t
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as analysis
from paper3 import retrospective_electorates as electorates
from paper3 import retrospective_score_ledger_budget as budget

FRAME_SEEDS = (3841001, 3841002)
DECISION_SEED_BASE = 3850000
ORDER_SEED = 3842001
REISSUES_PER_BLOCK = 1  # Candidate only, requires explicit prospective freezing.


@cache
def pairs():
    result = []
    for index, seed in enumerate(FRAME_SEEDS):
        pair = electorates.generate(seed)
        result.append(replace(pair,
            aligned=replace(pair.aligned, game_id=f"anticipation-electorate-{2 * index:03d}"),
            conflict=replace(pair.conflict, game_id=f"anticipation-electorate-{2 * index + 1:03d}")))
    return tuple(result)


def assignments():
    result = [dict(id=f"anticipation-{index}-{stratum}-{arm}", seed=pair.seed,
        stratum=stratum, arm=arm, game=getattr(pair, stratum), intended_calls=30,
        seed_base=DECISION_SEED_BASE + 64 * index)
        for index, pair in enumerate(pairs()) for stratum in analysis.STRATA
        for arm in institution.ARMS]
    Random(ORDER_SEED).shuffle(result)
    result = tuple(result)
    analysis.validate(result, {a["id"]: (None, None) for a in result})
    return result


def seed_audit(repo, *, current_freeze=None, expected_protocol=None):
    """Read historical manifest/call inventory; raises on collisions/read errors.

Caller must recheck this inventory at freeze/admission. No inference receipt,
authority, experiment result or actual run file is written by this function.
"""
    repo = Path(repo)
    history = repo / "results/paper3"
    institution.require(history.is_dir(), "historical root missing; no empty-inventory inference")
    excluded = None
    if current_freeze is not None:
        import json
        excluded = Path(current_freeze).resolve(strict=True)
        institution.require(excluded != history.resolve() and excluded.is_relative_to(history.resolve()),
                            "exclude only exact current freeze, not historical root")
        manifest = t.load(excluded / "manifest.json")
        digest = t.sha(json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True, allow_nan=False).encode())
        institution.require(manifest.get("format") == "paper3-anticipation-freeze-v1" and
            type(expected_protocol) is str and digest == expected_protocol,
            "current-freeze exclusion requires exact external protocol pin")
    else:
        institution.require(expected_protocol is None, "protocol without current freeze")
    planned = {ORDER_SEED, *FRAME_SEEDS,
        *(a["seed_base"] + i for a in assignments() for i in range(30))}
    observed, inventory = set(), []
    def walk(value, key=""):
        if type(value) is dict:
            for name, child in value.items():
                walk(child, name)
        elif type(value) is list:
            for child in value:
                walk(child, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)
    def unreadable(error):
        raise error
    for base, dirs, files in os.walk(history, onerror=unreadable):
        dirs[:] = [name for name in dirs if (Path(base) / name).resolve() != excluded and
            not any(fragment in name for fragment in
            ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
            if name == "manifest.json" or (path.parent.name == "calls" and name.endswith(".json")):
                value = t.load(path)
                walk(value.get("request", value) if path.parent.name == "calls" else value)
                inventory.append((str(path.relative_to(repo)), t.sha(path.read_bytes())))
    institution.require(not planned & observed, "historical frame/request/order seed collision")
    return dict(planned=tuple(sorted(planned)), overlap=(), historical_files=len(inventory),
                inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()),
                allocation_authorized=False, frozen_protocol=False)


def full_bound():
    """Price both ENTIRE eight-episode blocks, before any outcome selection."""
    inventory = assignments()
    blocks = tuple(dict(frame_seed=seed, **budget.block_bound(
        tuple(a for a in inventory if a["seed"] == seed), REISSUES_PER_BLOCK)) for seed in FRAME_SEEDS)
    return dict(blocks=blocks, logical_calls=sum(b["logical_calls"] for b in blocks),
        maximum_physical_calls=sum(b["maximum_physical_calls"] for b in blocks),
        full_reservation_usd=str(sum(Decimal(b["full_reservation_usd"]) for b in blocks)),
        allocation_authorized=False, frozen_protocol=False, publication_evidence=False,
        limitation="Worst-case reservation, not expected price. Both blocks, arms and "
        "two-term scope must remain; no outcome-conditioned case substitution or budget shrinking.")
