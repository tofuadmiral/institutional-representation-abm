"""Offline fresh qualification candidate; no calls, inherited passes or allocation.

One candidate frame and eighteen seeds fixed before any responses. Same substantive
factual questions and legal action scoring as the closed gates. Uses the
original script/oracle with keyed payoffs and the frozen dual-channel contract.
Terminal reports use an explicit
presence bit and integer score; only that report wording/encoding changes.
"""
from paper3 import retrospective_presence_report as presence
from dataclasses import replace
from functools import cache

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_electorates as design
from paper3 import retrospective_qualification as original
from paper3 import retrospective_keyed_interface as interface
from paper3 import retrospective_contract_route as route
from paper3 import retrospective_action_contract as contract

FRAME_SEED = 3630001
SEED_BASE = 3640000


@cache
def cases():
    pair = design.generate(FRAME_SEED)
    profile = pair.conflict
    focal, policy = next((actor, p) for actor, p in pair.exposed
                        if 0 < sum(row[p] for row in profile.utilities[0][actor]) < profile.office_value)
    negative, negative_policy = next((actor, p) for actor, p in pair.exposed
                                    if sum(row[p] for row in profile.utilities[0][actor]) < 0)
    game = replace(profile, game_id="qualification-accountability-contract-v1",
                   chairs=((focal + 1) % 7, focal))
    rows, scripts = [], {}
    for arm in institution.ARMS:
        actor, p = (focal, policy) if arm.endswith("majority") else (negative, negative_policy)
        episode, contexts = original._script(game, arm, p)
        scripts[arm] = (episode, contexts)
        before = contexts[(0, "vote", actor)]
        terminal = contexts[(1, "vote", actor)]
        assessment = episode.terms[0].assessments[actor]
        expected = dict(district_sum=assessment.district_sum,
            citizens_better=sum(v > 0 for v in episode.terms[0].citizen_utilities[actor]),
            citizens_worse=sum(v < 0 for v in episode.terms[0].citizen_utilities[actor]),
            majority_passed=assessment.majority_passed, sum_passed=assessment.sum_passed,
            incumbent_retained=episode.terms[0].tenure_retained[actor])
        facts = [("assessment", before, expected,
                  "Report district_sum, citizens_better, citizens_worse, majority_passed, "
                  "sum_passed and incumbent_retained.", dict(final_policy_passes=True))]
        peers = ((True,) * 6 if arm == "advisory_majority" else
                 (True,) * 2 + (False,) * 4 if arm == "binding_sum" else
                 (True,) * 3 + (False,) * 3)
        scores = institution.conditional_ballot_scores(game, arm, actor, p, peers)
        facts.append(("counterfactual", before,
                      dict(score_if_yes=scores[True], score_if_no=scores[False]),
                      "Report the original incumbent's score_if_yes if YOUR OWN ballot is yes, "
                      "and score_if_no if YOUR OWN ballot is no. Keep all six hypothetical peer "
                      "ballots fixed in both scenarios. Determine enactment by the four-yes "
                      "threshold; yes/no are not enact/reject assumptions.",
                      dict(other_six_ballots=list(peers), second_term_enacted_policy=0,
                           note="Hypothetical peer ballots for this factual question only; not observed sealed votes.")))
        facts.append(("terminal", terminal,
                      dict(acting_identity=episode.terms[1].occupants[actor],
                           original_incumbent_score=episode.initial_incumbent_scores[actor],
                           successor_score=episode.successor_scores[actor], third_term_bonus=0),
                      "Report acting_identity, original_incumbent_score, successor_score "
                      "(null if no successor acts), and third_term_bonus.",
                      dict(second_term_final_policy_passes=True)))
        for name, saved, expected, task, assumptions in facts:
            messages = interface.clarify(original._fact_messages(
                game, arm, saved, task, assumptions), game)
            parameters = original._fact_schema(expected)
            if name == "counterfactual":
                for field, vote in (("score_if_yes", "yes"), ("score_if_no", "no")):
                    parameters["properties"][field]["description"] = (
                        "Original incumbent score when its own ballot is " + vote +
                        "; six supplied peer ballots and the second-term enacted policy remain fixed.")
            rows.append(dict(id=f"{arm}-{name}", kind="fact", game=game, arm=arm, actor=actor,
                             term=saved["term"], stage=saved["stage"], messages=messages,
                             parameters=parameters, expected=expected))
    slots = (("advisory_majority", 0, "draft", game.chairs[0]),
             ("binding_sum", 0, "response", focal),
             ("binding_majority", 0, "final", game.chairs[0]),
             ("advisory_sum", 0, "vote", focal),
             ("binding_majority", 1, "draft", focal),
             ("advisory_sum", 1, "vote", focal))
    for arm, term, stage, actor in slots:
        saved = scripts[arm][1][(term, stage, actor)]
        fragment = interface.structured(interface.messages(game, arm, actor,
            saved["identity"], term, stage, saved["context"]), game, stage)
        rows.append(dict(id=f"action-{arm}-{term}-{stage}", kind="action", game=game,
                         arm=arm, actor=actor, term=term, stage=stage,
                         messages=fragment["messages"],
                         parameters=fragment["tools"][0]["function"]["parameters"], expected=None))
    institution.require(len(rows) == 18 and len({row["id"] for row in rows}) == 18,
                        "keyed qualification inventory")
    rows.sort(key=lambda c: not (c["kind"] == "fact" and c["id"].endswith("-terminal")))
    return tuple(rows)


def structured(case):
    fragment = presence.structured(case)
    fragment["messages"] = contract.replace_instruction(fragment["messages"])
    return fragment


def requests():
    return tuple(dict(id="gate-" + case["id"],
                      request=route.request(structured(case), SEED_BASE + index),
                      context=dict(case_id=case["id"])) for index, case in enumerate(cases()))


def score(case, trace):
    """Strict channel-neutral fields; facts exact, strategic actions only legal."""
    try:
        evidence = contract.decision(trace)
        action = evidence["arguments"]
        if case["kind"] == "fact":
            if presence.terminal(case):
                action = presence.decode(action)
            expected = case["expected"]
            institution.require(set(action) == set(expected) and all(
                (type(action[key]) in (int, type(None)) if key == "successor_score" else
                 type(action[key]) is type(value)) for key, value in expected.items()),
                "factual field/type mismatch")
            exact = action == expected
        else:
            contract.decode(case["game"], case["stage"], trace)
            exact = True
        return dict(valid_action=True, exact=exact, action=action,
                    channel=evidence["channel"], failure=None)
    except (ValueError, TypeError, KeyError) as exc:
        return dict(valid_action=False, exact=False, action=None, channel=None, failure=str(exc))
