"""Offline successor cases/bounds; no qualification inheritance or allocation.

Same scientific generator and two-sided screen as the closed accountability
pilot, with prospectively fixed fresh frames. Never substitute profiles after
responses. A future successor must freeze source, evidence, seed inventory,
recovery admission/timing and accounting before paid calls.
"""
from dataclasses import replace
from decimal import Decimal
from functools import cache
import hashlib
import json
import os
from pathlib import Path
from random import Random

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_deepseek_route as route
from paper3 import retrospective_electorates as design
from paper3 import retrospective_keyed_interface as interface
from paper3 import retrospective_serial_recovery as recovery

FRAME_SEEDS = (3431001, 3431002)
DECISION_SEED_BASE = 3440000
ORDER_SEED = 3449999


def seed_audit(root):
    """Read-only collision check against historical manifests and wire seeds."""
    root = Path(root)
    planned = {ORDER_SEED, *FRAME_SEEDS,
               *(a["seed_base"] + i for a in assignments() for i in range(30))}
    observed, inventory = set(), []

    def walk(value, key=""):
        if type(value) is dict:
            for name, item in value.items():
                walk(item, name)
        elif type(value) is list:
            for item in value:
                walk(item, key)
        elif type(value) is int and "seed" in key.lower():
            observed.add(value)

    for base, directories, names in os.walk(root / "results/paper3"):
        directories[:] = [d for d in directories if not any(s in d for s in
            ("portable", "bundle", "export", "replay", "__pycache__", "code"))]
        for name in names:
            p = Path(base) / name
            if name == "manifest.json" or p.parent.name == "calls" and name.endswith(".json"):
                raw = p.read_bytes()
                value = json.loads(raw)
                walk(value.get("request", value) if p.parent.name == "calls" else value)
                inventory.append((str(p.relative_to(root)), hashlib.sha256(raw).hexdigest()))
    overlap = planned & observed
    institution.require(not overlap, "historical seed collision; do not allocate")
    digest = hashlib.sha256(json.dumps(sorted(inventory), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return dict(planned=sorted(planned), overlap=[], historical_files=len(inventory),
                inventory_sha256=digest)


@cache
def pairs():
    rows = []
    for i, seed in enumerate(FRAME_SEEDS):
        pair = design.generate(seed)
        rows.append(replace(pair,
            aligned=replace(pair.aligned, game_id=f"electorate-{2 * i:03d}"),
            conflict=replace(pair.conflict, game_id=f"electorate-{2 * i + 1:03d}")))
    return tuple(rows)


@cache
def assignments():
    rows = [dict(id=f"serial-accountability-{i}-{stratum}-{arm}", seed=pair.seed,
                 stratum=stratum, arm=arm, game=getattr(pair, stratum),
                 intended_calls=30, seed_base=DECISION_SEED_BASE + 64 * i)
            for i, pair in enumerate(pairs()) for stratum in ("aligned", "conflict")
            for arm in institution.ARMS]
    Random(ORDER_SEED).shuffle(rows)
    institution.require(len(rows) == 16 and len({r["id"] for r in rows}) == 16,
                        "sixteen prospectively assigned full episodes")
    return tuple(rows)


def action_request(assignment, actor, identity, term, stage, context, index):
    institution.require(type(index) is int and 0 <= index < 30, "logical action index")
    game = assignment["game"]
    messages = interface.messages(game, assignment["arm"], actor, identity, term, stage, context)
    return route.request(interface.structured(messages, game, stage), assignment["seed_base"] + index)


@cache
def legal_history_bounds():
    rows = []
    for assignment in assignments():
        maxima = [0] * 30
        width = len(assignment["game"].utilities[0][0][0])
        for policy, passing in [(p, True) for p in range(width)] + [(0, False)]:
            def ask(actor, identity, term, stage, context, index):
                request = action_request(assignment, actor, identity, term, stage, context, index)
                maxima[index] = max(maxima[index], route.reservation(request)["input_token_bound"])
                if stage in ("draft", "final"):
                    return dict(policy=policy if term == 0 else width - 1, message="\\" * 128)
                if stage == "response":
                    return dict(support=False, counter_policy=width - 1, message="\\" * 128)
                return dict(vote=actor < 4 if passing else False)
            institution.episode(assignment["game"], assignment["arm"], ask)
        costs = [(Decimal(bound) * route.PRICE_IN + Decimal(route.OUTPUT_BOUND) * route.PRICE_OUT)
                 / 1000000 for bound in maxima]
        rows.append(dict(id=assignment["id"], frame_seed=assignment["seed"],
                         input_bounds=tuple(maxima), base_usd=str(sum(costs)),
                         largest_attempt_usd=str(max(costs))))
    batches = []
    for i, seed in enumerate(FRAME_SEEDS):
        local = [r for r in rows if r["frame_seed"] == seed]
        base = sum(Decimal(r["base_usd"]) for r in local)
        largest = max(Decimal(r["largest_attempt_usd"]) for r in local)
        proof = recovery.reservation_bound(base, largest)
        institution.require(len(local) == 8 and
            Decimal(proof["full_path_usd"]) <= recovery.PROPOSED_STAGE_CAP,
            "complete block plus every possible permitted reissue must fit proposed cap")
        batches.append(dict(index=i, seed=seed, base_calls=240, maximum_calls=265,
            base_usd=str(base), largest_attempt_usd=str(largest), **proof))
    return dict(assignments=tuple(rows), batches=tuple(batches), base_calls=480,
        maximum_calls=530, declared_attempt_slots=960,
        maximum_input_bound=max(max(r["input_bounds"]) for r in rows), output_bound=route.OUTPUT_BOUND,
        qualification_inherited=False, allocation_authorized=False, old_run_reopen_authorized=False,
        limitation="Offline byte bounds, not expected bills or a model result. Each physical reissue reserves full price; no inferred free429. Fresh qualification replay/config equality, transport-policy approval and separate source/evidence freeze are still required.")
