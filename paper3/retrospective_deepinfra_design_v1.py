"""Approved fresh inventory and worst-case bounds; not a freeze or launch.

Same conditional games, four economic arms, seven representatives/63 citizens,
both terms and two-sided scientific screen. Only fresh seeds and the approved
transport/accounting policy differ. Never tune cases to observed responses.
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
from paper3 import retrospective_deepinfra_recovery_policy_v1 as policy
from paper3 import retrospective_electorates as electorates
from paper3 import retrospective_deepinfra_requests_v1 as requests

FRAME_SEEDS = (2026102102, 2026102103)
ORDER_SEED = 2026102104
DECISION_SEED_BASE = 2026102300
FORMAT = "paper3-deepinfra-accountability-freeze-v1"


@cache
def pairs():
    return tuple(replace(pair,
        aligned=replace(pair.aligned, game_id=f"anticipation-electorate-{2 * i:03d}"),
        conflict=replace(pair.conflict, game_id=f"anticipation-electorate-{2 * i + 1:03d}"))
        for i, pair in enumerate(electorates.generate(seed) for seed in FRAME_SEEDS))


def assignments():
    items = [dict(id=f"deepinfra-r1-{i}-{stratum}-{arm}", seed=pair.seed,
        stratum=stratum, arm=arm, game=getattr(pair, stratum), intended_calls=30,
        seed_base=DECISION_SEED_BASE + 64 * i)
        for i, pair in enumerate(pairs()) for stratum in analysis.STRATA for arm in institution.ARMS]
    Random(ORDER_SEED).shuffle(items)
    result = tuple(items)
    analysis.validate(result, {a["id"]: (None, None) for a in result})
    return result


@cache
def full_bound():
    inventory = assignments()
    blocks = tuple(dict(frame_seed=seed, **requests.block_bound(
        tuple(a for a in inventory if a["seed"] == seed), policy.MAX_REISSUES_PER_BLOCK)) for seed in FRAME_SEEDS)
    return dict(blocks=blocks, logical_calls=sum(b["logical_calls"] for b in blocks),
        maximum_physical_calls=sum(b["maximum_physical_calls"] for b in blocks),
        full_reservation_usd=str(sum(Decimal(b["full_reservation_usd"]) for b in blocks)),
        allocation_authorized=False, frozen_protocol=False, publication_evidence=False,
        limitation="Whole-study worst-case reservation, not expected spending. No case, "
                   "arm, horizon, output ceiling or recovery budget may shrink to fit funding.")


def seed_audit(repo, *, current_freeze=None, expected_protocol=None):
    """Read-only historical closure; an excluded current root needs its exact pin."""
    history = Path(repo) / "results/paper3"
    institution.require(history.is_dir(), "historical root missing")
    excluded = None
    if current_freeze is not None:
        excluded = Path(current_freeze).resolve(strict=True)
        institution.require(excluded != history.resolve() and excluded.is_relative_to(history.resolve()),
                            "exclude only exact current freeze")
        manifest = t.load(excluded / "manifest.json")
        institution.require(manifest.get("format") == FORMAT and type(expected_protocol) is str and
            t.sha(t.canonical(manifest).encode()) == expected_protocol,
            "current-freeze exclusion requires exact protocol")
    else:
        institution.require(expected_protocol is None, "protocol without current freeze")
    planned = {ORDER_SEED, *FRAME_SEEDS, *(a["seed_base"] + i for a in assignments() for i in range(30))}
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
            not any(fragment in name for fragment in ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in files:
            path = Path(base) / name
            if name == "manifest.json" or (path.parent.name == "calls" and name.endswith(".json")):
                value = t.load(path)
                walk(value.get("request", value) if path.parent.name == "calls" else value)
                inventory.append((str(path.relative_to(repo)), t.sha(path.read_bytes())))
    institution.require(not planned & observed, "historical frame/request/order seed collision")
    return dict(planned=tuple(sorted(planned)), overlap=(), historical_files=len(inventory),
        inventory_sha256=t.sha(t.canonical(sorted(inventory)).encode()), allocation_authorized=False, frozen_protocol=False)
