"""Fresh prospective eighteen-call qualification; no network/model calls.

Twelve exact factual reports plus six legal strategic actions. Facts test
arithmetic and institutional state, never agreement with the hypothesis.
Strategic actions require validity, not any preferred policy or vote.
"""
from copy import deepcopy
from dataclasses import replace
import json

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_interface as interface

FRAME_SEED = 3100001


def _script(game, arm, first_policy):
    contexts = {}

    def ask(actor, identity, term, stage, context, index):
        contexts[(term, stage, actor)] = dict(actor=actor, identity=identity,
                                             term=term, stage=stage, context=deepcopy(context))
        policy = first_policy if term == 0 else 1
        if stage in ("draft", "final"):
            return dict(policy=policy, message="qualification hypothetical")
        if stage == "response":
            return dict(support=True, counter_policy=policy, message="hypothetical response")
        return dict(vote=actor < 4)

    return institution.episode(game, arm, ask), contexts


def _object(properties):
    return dict(type="object", properties=properties, required=list(properties),
                additionalProperties=False)


def _fact_schema(expected):
    types = {bool: "boolean", int: "integer", str: "string", type(None): "null"}
    return _object({key: dict(type=["integer", "null"] if key == "successor_score" else
                             types[type(value)]) for key, value in expected.items()})


def _fact_messages(game, arm, saved, task, assumptions):
    messages = interface.messages(game, arm, saved["actor"], saved["identity"],
                                  saved["term"], saved["stage"], saved["context"])
    value = json.loads(messages[1]["content"])
    value["task"] = "Factual qualification only, not a strategic action: " + task
    value["hypothetical_assumptions"] = assumptions
    messages[1]["content"] = json.dumps(value, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False)
    return messages


def cases():
    pair = design.generate(FRAME_SEED)
    profile = pair.conflict
    focal, first_policy = next((actor, policy) for actor, policy in
        pair.exposed
        if 0 < sum(row[policy] for row in profile.utilities[0][actor]) < profile.office_value)
    negative_focal, negative_policy = next((actor, policy) for actor, policy in pair.exposed
        if sum(row[policy] for row in profile.utilities[0][actor]) < 0)
    # Qualification role schedule deliberately exercises a removed chair.
    # This does not select or alter any discovery electorate/role schedule.
    game = replace(profile, game_id="qualification-accountability-v1",
                   chairs=((focal + 1) % 7, focal))
    rows = []
    scripts = {}
    for arm in institution.ARMS:
        actor, policy = ((focal, first_policy) if arm.endswith("majority") else
                         (negative_focal, negative_policy))
        episode, contexts = _script(game, arm, policy)
        scripts[arm] = (episode, contexts)
        before_vote = contexts[(0, "vote", actor)]
        terminal_vote = contexts[(1, "vote", actor)]
        assessment = episode.terms[0].assessments[actor]
        expected = dict(district_sum=assessment.district_sum,
                        citizens_better=sum(value > 0 for value in
                                            episode.terms[0].citizen_utilities[actor]),
                        citizens_worse=sum(value < 0 for value in
                                           episode.terms[0].citizen_utilities[actor]),
                        majority_passed=assessment.majority_passed,
                        sum_passed=assessment.sum_passed,
                        incumbent_retained=episode.terms[0].tenure_retained[actor])
        facts = [("assessment", before_vote, expected,
                  "Report district_sum, citizens_better, citizens_worse, majority_passed, "
                  "sum_passed and incumbent_retained.",
                  dict(final_policy_passes=True))]
        peers = ((True,) * 6 if arm == "advisory_majority" else
                 (True,) * 2 + (False,) * 4 if arm == "binding_sum" else
                 (True,) * 3 + (False,) * 3)
        scores = institution.conditional_ballot_scores(game, arm, actor, policy, peers)
        facts.append(("counterfactual", before_vote,
                      dict(score_if_yes=scores[True], score_if_no=scores[False]),
                      "Report the original incumbent's score_if_yes and score_if_no.",
                      dict(other_six_ballots=list(peers),
                           second_term_enacted_policy=0,
                           note="These are hypothetical peer ballots, not observed sealed votes.")))
        facts.append(("terminal", terminal_vote,
                      dict(acting_identity=episode.terms[1].occupants[actor],
                           original_incumbent_score=episode.initial_incumbent_scores[actor],
                           successor_score=episode.successor_scores[actor], third_term_bonus=0),
                      "Report acting_identity, original_incumbent_score, successor_score "
                      "(null if no successor acts), and third_term_bonus.",
                      dict(second_term_final_policy_passes=True)))
        for name, saved, expected, task, assumptions in facts:
            rows.append(dict(id=f"{arm}-{name}", kind="fact", game=game, arm=arm,
                             actor=actor, term=saved["term"], stage=saved["stage"],
                             messages=_fact_messages(game, arm, saved, task, assumptions),
                             parameters=_fact_schema(expected), expected=expected))
    action_slots = (("advisory_majority", 0, "draft", game.chairs[0]),
                    ("binding_sum", 0, "response", focal),
                    ("binding_majority", 0, "final", game.chairs[0]),
                    ("advisory_sum", 0, "vote", focal),
                    ("binding_majority", 1, "draft", focal),
                    ("advisory_sum", 1, "vote", focal))
    for arm, term, stage, actor in action_slots:
        saved = scripts[arm][1][(term, stage, actor)]
        rows.append(dict(id=f"action-{arm}-{term}-{stage}", kind="action", game=game,
                         arm=arm, actor=actor, term=term, stage=stage,
                         messages=interface.messages(game, arm, actor, saved["identity"],
                                                     term, stage, saved["context"]),
                         parameters=interface.schema(game, stage), expected=None))
    institution.require(len(rows) == 18 and len({row["id"] for row in rows}) == 18,
                        "qualification inventory")
    return tuple(rows)


def structured(case):
    return dict(messages=deepcopy(case["messages"]),
                tools=[dict(type="function", function=dict(name=interface.TOOL_NAME,
                    description="Record the requested factual report or institutional action.",
                    parameters=deepcopy(case["parameters"])))], tool_choice="auto")


def score(case, trace):
    # This is only envelope/substantive scoring. The runner must also check
    # complete pinned transport, actual native reasoning and certified billing.
    try:
        action = interface.envelope.arguments(trace)
        if case["kind"] == "fact":
            expected = case["expected"]
            institution.require(set(action) == set(expected) and all(
                (type(action[key]) in (int, type(None)) if key == "successor_score" else
                 type(action[key]) is type(value)) for key, value in expected.items()),
                "factual field/type mismatch")
            exact = action == expected
        else:
            interface.decode(case["game"], case["stage"], trace)
            exact = True  # Legality, never hypothesis-favorable strategy.
        return dict(valid_action=True, exact=exact, action=action, failure=None)
    except (ValueError, TypeError, KeyError) as exc:
        return dict(valid_action=False, exact=False, action=None, failure=str(exc))
