"""Prospective, offline-only jurisdiction design; no launch or source freeze.

The two blocks combine a display form with a fresh requested seed. They cannot
isolate label effects from stochastic variation. Every arm occurs in each block.
Legacy controller, objectives, action schema and histories are unchanged.
"""
from copy import deepcopy
import json

from paper3 import coalition_contracts as game

ROLE_MAPS = (tuple(range(7)), (4, 1, 6, 0, 5, 2, 3))  # logical -> displayed
POLICY_MAPS = (
    dict(A0="A0", A1="A1", B0="B0", B1="B1"),
    dict(A0="B1", A1="B0", B0="A1", B1="A0"),
)
EX_ANTE_EXPOSED = ((4, 5, 6), (4, 5, 6), (6,), ())


def fixtures():
    """Theory-selected fresh structures, not held-out population evidence."""
    specifications = (
        ("four_signer_exchange", [(9, -3), (8, -2), (-3, 9), (-2, 8),
                                  (-4, -4), (-6, -2), (-2, -6)], 1),
        ("unilateral_majority", [(8, -5), (9, -6), (7, -4), (10, -7),
                                 (-4, 10), (-3, 9), (-5, 11)], 2),
        ("overlapping_majorities", [(6, 4), (4, 6), (8, -3), (9, -4),
                                    (-3, 8), (-4, 9), (-6, -6)], 1),
        ("aligned_fresh", [(i + 4, i + 3) for i in range(7)], 1),
    )
    result = []
    for name, rows, alternative in specifications:
        p = dict(id=name, proposer=0, utilities=[
            dict(A0=a, A1=alternative, B0=b, B1=alternative) for a, b in rows])
        game.validate_profile(p)
        result.append(p)
    return result


def maps(form):
    game.require(type(form) is int and form in (0, 1), "display form")
    return ROLE_MAPS[form], POLICY_MAPS[form].copy()


def display_profile(profile, form):
    game.validate_profile(profile)
    roles, policies = maps(form)
    rows = [None] * 7
    for logical, row in enumerate(profile["utilities"]):
        renamed = {policies[key]: value for key, value in row.items()}
        rows[roles[logical]] = {key: renamed[key] for key in POLICY_MAPS[0]}
    result = dict(id=profile["id"] + f"-form-{form}",
                  proposer=roles[profile["proposer"]], utilities=rows)
    game.validate_profile(result)
    return result


def canonical_utilities(displayed, form):
    roles, _ = maps(form)
    game.require(len(displayed) == 7, "seven outcomes required")
    return [displayed[roles[logical]] for logical in range(7)]


def canonical_offer(offer, form):
    game.validate_offer(offer)
    roles, policies = maps(form)
    role_inverse = {display: logical for logical, display in enumerate(roles)}
    policy_inverse = {display: logical for logical, display in policies.items()}
    projects = [policy_inverse[p] for p in offer["projects"].values()]
    first_project = policy_inverse[offer["projects"][offer["first"]]]
    return dict(projects={p[0]: p for p in projects}, first=first_project[0],
                coalition=sorted(role_inverse[i] for i in offer["coalition"]))


def labelled_messages(messages):
    """Change only payoff table encoding; no new instruction or derived facts."""
    game.require(len(messages) == 2 and messages[1]["role"] == "user", "message shape")
    record_text, separator, question = messages[1]["content"].partition("\n")
    game.require(bool(separator), "missing question")
    record = json.loads(record_text)
    rows = record["utilities_for_all_principals"]
    game.require(type(rows) is list and len(rows) == 7, "original seven-row array required")
    record["utilities_for_all_principals"] = {str(i): row for i, row in enumerate(rows)}
    result = deepcopy(messages)
    result[1]["content"] = json.dumps(record, separators=(",", ":")) + "\n" + question
    return result


def schedule(seed_bases):
    """Caller must audit/freeze eight fresh bases before any eventual inference.

24 episodes, 720 intended requests; paired across arms within eight blocks.
Each form has a different seed: form effects are not separately identified.
"""
    game.require(len(seed_bases) == 8 and all(type(s) is int and s >= 0 for s in seed_bases),
                 "eight nonnegative seed bases required")
    ranges = [set(range(s, s + 30)) for s in seed_bases]
    game.require(sum(map(len, ranges)) == len(set().union(*ranges)), "overlapping seeds")
    result = []
    for fixture_index in range(4):
        for form in range(2):
            block = fixture_index * 2 + form
            arms = game.ARMS[block % 3:] + game.ARMS[:block % 3]
            for arm in arms:
                result.append(dict(id=f"fixture-{fixture_index}-block-{form}-{arm}",
                    fixture_index=fixture_index, form=form, block=block, arm=arm,
                    seed_base=seed_bases[block]))
    return result


def episode(profile, arm, ask):
    """Reuse the unchanged institution; adapt only the outgoing payoff encoding."""
    def labelled_ask(actor, stage, messages, index):
        return ask(actor, stage, labelled_messages(messages), index)
    return game.episode(profile, arm, labelled_ask)
