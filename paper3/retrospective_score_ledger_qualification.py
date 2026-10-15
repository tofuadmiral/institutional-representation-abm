"""Fresh prospective ledger gate: 4 role reports, 8 counterfactuals, 12 actions.

Hand-constructed diagnostic coverage, not a sampled research population.
Expectations come from citizen utilities and specified ballots, not ledger totals.
No inference, allocation, historical reinterpretation or institutional launch.
"""
from functools import cache
import json
from random import Random

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as electorates
from paper3 import retrospective_qualification as original
from paper3 import retrospective_score_ledger as ledger
from paper3 import retrospective_presence_report as presence
from paper3 import retrospective_serialization_retry_qualification as previous
from paper3 import retrospective_contract_route_v2 as route

FRAME_SEED = 3831001
SEED_BASE = 3832000


@cache
def game():
    """Fixed sums/sign coverage; only bounded citizen distributions use the seed."""
    rng = Random(FRAME_SEED)
    totals = (((12, -11, 7), (9, -11, -8), (-8, 16, 6),
               (15, -9, -7), (6, 18, -12), (-13, 11, 8), (17, -6, 9)),
              ((-17, 17, 0), (13, -13, 0), (8, -9, 6),
               (-12, 11, 7), (9, -6, -8), (-7, 14, 5), (16, -8, 9)))
    tables = []
    for term, sums in enumerate(totals):
        districts = []
        for actor, values in enumerate(sums):
            columns = [(0,) * 9]
            for policy, total in enumerate(values, 1):
                if total == 0:
                    column = [1, -1, 2, -2, 3, -3, 4, -4, 0]
                    rng.shuffle(column)
                else:
                    aligned = not (term == 0 and (actor, policy) in ((0, 1), (1, 2)))
                    column = electorates.citizen_column(rng, total, aligned)
                columns.append(tuple(column))
            districts.append(tuple(zip(*columns, strict=True)))
        tables.append(tuple(districts))
    value = institution.Game("qualification-score-ledger-v1", tuple(tables), (6, 0), 20)
    institution.validate(value)
    return value


def _sum(value, term, actor, policy):
    return sum(citizen[policy] for citizen in value.utilities[term][actor])


def _retained(value, arm, actor, policy):
    """Independent primitive rule calculation; no controller/ledger score oracle."""
    if arm.startswith("advisory"):
        return True
    utilities = [citizen[policy] for citizen in value.utilities[0][actor]]
    return (sum(v >= 0 for v in utilities) >= 5 if arm.endswith("majority")
            else sum(utilities) >= 0)


def _original_score(value, actor, first, second, retained):
    return _sum(value, 0, actor, first) + _sum(value, 1, actor, second) + (
        value.office_value if retained else 0)


def _fact(value, arm, saved, name, expected, task, assumptions):
    messages = ledger.messages(value, arm, saved["actor"], saved["identity"],
        saved["term"], saved["stage"], saved["context"])
    content = json.loads(messages[1]["content"])
    content["task"] = "Factual qualification only, not a strategic action: " + task
    content["hypothetical_assumptions"] = assumptions
    messages[1]["content"] = json.dumps(content, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False)
    return dict(id=f"{arm}-{name}", kind="fact", game=value, arm=arm,
        actor=saved["actor"], term=saved["term"], stage=saved["stage"],
        messages=messages, parameters=original._fact_schema(expected), expected=expected)


@cache
def cases():
    value = game()
    rows, scripts = [], {}
    for index, arm in enumerate(institution.ARMS):
        actor, first = (0, 1) if arm.endswith("majority") else (1, 2)
        _, contexts = original._script(value, arm, first)
        scripts[arm] = contexts
        retained = _retained(value, arm, actor, first)
        terminal = contexts[(1, "vote", actor)]
        rows.append(_fact(value, arm, terminal, "terminal",
            dict(acting_identity=terminal["identity"],
                 original_incumbent_score=_original_score(value, actor, first, 1, retained),
                 successor_score=None if retained else _sum(value, 1, actor, 1),
                 third_term_bonus=0), presence.OLD_TASK,
            dict(second_term_final_policy_passes=True)))
        # Enactment requires joining YOUR ballot with six hypothetical peers.
        # Future policy is explicitly stipulated, not predicted or recommended.
        peer_count = (3, 4, 2, 3)[index]
        peers = [True] * peer_count + [False] * (6 - peer_count)
        future = (1, 2, 3, 1)[index]
        expected = {}
        for vote, suffix in ((True, "yes"), (False, "no")):
            enacted = first if peer_count + vote >= 4 else 0
            kept = _retained(value, arm, actor, enacted)
            expected.update({"enacted_policy_if_" + suffix: enacted,
                "original_score_if_" + suffix: _original_score(value, actor, enacted, future, kept),
                "next_identity_if_" + suffix: institution.incumbent(actor) if kept
                                             else institution.successor(actor)})
        rows.append(_fact(value, arm, contexts[(0, "vote", actor)], "first-counterfactual",
            expected, "For each of YOUR hypothetical yes/no ballots, report enacted_policy_if_yes/no, "
            "original_score_if_yes/no and next_identity_if_yes/no. Apply the four-yes threshold "
            "with the six fixed peer ballots. Credit the stipulated second-term district utility "
            "even if the original incumbent is removed; do not treat yes as automatic passage.",
            dict(other_six_ballots=peers, second_term_enacted_policy=future,
                 note="Hypothetical only, not observed sealed votes or a forecast.")))
        peer_count = (2, 3, 4, 3)[index]
        expected = {}
        for vote, suffix in ((True, "yes"), (False, "no")):
            enacted = 1 if peer_count + vote >= 4 else 0
            original_score = _original_score(value, actor, first, enacted, retained)
            expected.update({"enacted_policy_if_" + suffix: enacted,
                "original_score_if_" + suffix: original_score,
                "acting_score_if_" + suffix: original_score if retained
                                            else _sum(value, 1, actor, enacted)})
        rows.append(_fact(value, arm, terminal, "second-counterfactual", expected,
            "For each of YOUR hypothetical yes/no ballots, report enacted_policy_if_yes/no, "
            "original_score_if_yes/no and acting_score_if_yes/no. Apply the four-yes threshold. "
            "Use the already-resolved first-term history and actual officeholder. No third-term bonus.",
            dict(other_six_ballots=[True] * peer_count + [False] * (6 - peer_count),
                 note="Hypothetical only, not observed sealed votes.")))
    slots = (("advisory_majority", 0, "draft", 6), ("binding_sum", 0, "response", 1),
             ("binding_majority", 0, "final", 6), ("advisory_sum", 0, "vote", 1),
             ("binding_majority", 1, "draft", 0), ("advisory_sum", 1, "vote", 1),
             ("advisory_majority", 1, "response", 1), ("binding_sum", 1, "final", 0),
             ("binding_majority", 0, "response", 0), ("advisory_sum", 0, "final", 6),
             ("advisory_majority", 1, "vote", 0), ("binding_sum", 1, "vote", 1))
    for arm, term, stage, actor in slots:
        saved = scripts[arm][(term, stage, actor)]
        fragment = ledger.structured(ledger.messages(value, arm, actor, saved["identity"],
            term, stage, saved["context"]), value, stage)
        rows.append(dict(id=f"action-{arm}-{term}-{stage}", kind="action", game=value,
            arm=arm, actor=actor, term=term, stage=stage, messages=fragment["messages"],
            parameters=fragment["tools"][0]["function"]["parameters"], expected=None))
    institution.require(len(rows) == 24 and len({r["id"] for r in rows}) == 24, "ledger gate inventory")
    rows.sort(key=lambda case: not presence.terminal(case))
    return tuple(rows)


def structured(case):
    """Keep ledger instruction and validate its disclosure before typed tooling."""
    ledger.structured(case["messages"], case["game"], case["stage"])
    return presence.structured(case)


def requests():
    return tuple(dict(id="gate-" + case["id"],
        request=route.request(structured(case), SEED_BASE + index),
        context=dict(case_id=case["id"])) for index, case in enumerate(cases()))


score = previous.score  # Same exact grammar, presence decoding and legal-action mapper.
