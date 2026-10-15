"""Unfrozen single-function interface; no route, credentials or model calls.

Parsing reuses the preserved generic one-call SSE parser. Provider, billing,
native reasoning and completion checks belong to a future qualified runner.
Offline schema tests do not establish provider support.
"""
from copy import deepcopy
from dataclasses import asdict
import json

from paper3 import constituent_b_tool_interface as envelope
from paper3 import retrospective_accountability as institution

TOOL_NAME = envelope.TOOL_NAME
STAGES = ("draft", "response", "final", "vote")
SYSTEM = """You are a representative in a finite, two-term legislative simulation.
Your constituents entrust you with their district's cumulative utility sum.
All seven districts contain nine citizens. Citizen utility is not office value.
The incumbent's stipulated decision score is its district's term-one plus
term-two utility sum, plus B if that incumbent keeps office in term two.
District utility remains credited even after removal. Office value is a
simulation incentive, not a fact about your real motives. A successor's score
is its district's terminal term-two utility sum, without another office bonus.
Both constituency outcomes and office scores are recorded separately.

Each term has a chair draft, six sealed responses/counteroffers, a chair final
offer, and seven sealed policy ballots. Four yes votes enact the final policy;
otherwise policy 0 (zero-utility status quo) is enacted. Responses are public
after their stage closes. Policy ballots never get overridden. Earlier sealed
responses or ballots are not available while that same stage is still running.
Both assessment scoreboards are disclosed regardless of the selected criterion.
Majority assessment passes if at least five citizens have enacted utility >=0.
Sum assessment passes if the district sum >=0. Ties retain the incumbent.
Advisory assessment never removes anyone. Binding assessment removes an
incumbent that fails its selected assessment, before term two, and the named
successor acts instead. Assessment depends on the district's enacted policy
outcome, not how its representative voted. Policy 0 retains every incumbent.
Term two is terminal: there is no third-term retention or extra office award.

Use the provided role identity and public history. Each request is a fresh
model call; no previous private reasoning or hidden notebook is replayed.
Use native reasoning, then call submit_decision exactly once with the requested
fields. The structured fields, not promises in a message, determine your action.
Messages are public and limited to 128 characters. Text, newlines and tabs are
allowed, but other C0/C1 control characters are not. No output repair is used.
"""


def schema(game, stage):
    institution.validate(game)
    institution.require(stage in STAGES, "action stage")
    policy = dict(type="integer", minimum=0, maximum=len(game.utilities[0][0][0]) - 1)
    message = dict(type="string", maxLength=institution.MAX_MESSAGE,
                   pattern=r"^[^\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]*$")
    if stage in ("draft", "final"):
        properties = dict(policy=policy, message=message)
    elif stage == "response":
        properties = dict(support=dict(type="boolean"), counter_policy=policy, message=message)
    else:
        properties = dict(vote=dict(type="boolean"))
    return dict(type="object", properties=properties, required=list(properties),
                additionalProperties=False)


def messages(game, arm, actor, identity, term, stage, context):
    institution.validate(game)
    institution.rules(arm)
    institution.incumbent(actor)
    institution.require(type(term) is int and term in (0, 1) and stage in STAGES, "term/stage")
    institution.require(type(context) is dict and context.get("game_id") == game.game_id and
                        context.get("arm") == arm and context.get("term") == term and
                        context.get("utilities") == game.utilities and
                        context.get("chairs") == game.chairs and
                        context.get("office_value") == game.office_value,
                        "controller context does not match game")
    expected_assessments = tuple(tuple(asdict(institution.assess(tuple(row[policy]
        for row in district))) for policy in range(len(district[0])))
        for district in game.utilities[term])
    institution.require(context.get("menu_assessments") == expected_assessments,
                        "both scoreboards must match exact utilities")
    history = context.get("history")
    institution.require(type(history) is list and len(history) == term, "public history length")
    expected_occupants = tuple(map(institution.incumbent, institution.ACTORS))
    if term == 1:
        saved = history[0]
        institution.require(type(saved) is dict and
                            all(key in saved for key in ("draft", "responses", "final", "requested")),
                            "predecessor action history")
        previous = institution.resolve_term(game, arm, 0,
            institution.parse_offer(game, saved["draft"]),
            tuple(institution.parse_response(game, item) for item in saved["responses"]),
            institution.parse_offer(game, saved["final"]), saved["requested"])
        institution.require(saved == asdict(previous), "exact predecessor history")
        expected_occupants = previous.next_occupants
    institution.require(context.get("occupants") == expected_occupants, "actual officeholder roster")
    institution.require(context["occupants"][actor] == identity and
                        identity in (institution.incumbent(actor), institution.successor(actor)),
                        "current acting identity")
    institution.require((stage in ("draft", "final")) == (actor == game.chairs[term])
                        or stage == "vote", "chair/nonchair action")
    institution.require((stage == "draft" or "draft" in context) and
                        ((stage not in ("final", "vote")) or "responses" in context) and
                        (stage != "vote" or "final" in context), "stage prerequisites")
    institution.require((stage != "draft" or not {"draft", "responses", "final"} & set(context))
                        and (stage != "response" or not {"responses", "final"} & set(context))
                        and (stage != "final" or "final" not in context) and
                        not {"requested", "executed"} & set(context), "sealed-stage leakage")
    value = deepcopy(context)
    value["acting_district"] = actor
    value["acting_identity"] = identity
    value["response_district_order"] = tuple(a for a in institution.ACTORS if a != game.chairs[term])
    value["stage"] = stage
    value["selected_assessment"] = "majority" if arm.endswith("majority") else "sum"
    value["assessment_binding"] = arm.startswith("binding")
    value["task"] = {"draft": "Offer one policy and a public message.",
                     "response": "State support for the draft and propose one counter-policy.",
                     "final": "Choose the final policy after reading the public responses.",
                     "vote": "Cast your independent yes/no ballot on the final policy."}[stage]
    return [dict(role="system", content=SYSTEM), dict(role="user", content=json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))]


def structured(messages_value, game, stage):
    """Request fragment, not a complete provider-qualified API request."""
    institution.require(type(messages_value) is list and len(messages_value) == 2,
                        "two messages")
    return dict(messages=deepcopy(messages_value), tools=[dict(type="function", function=dict(
        name=TOOL_NAME, description="Record the representative's institutional action.",
        parameters=schema(game, stage)))],
        tool_choice="auto")


def decode(game, stage, trace):
    action = envelope.arguments(trace)
    if stage in ("draft", "final"):
        return asdict(institution.parse_offer(game, action))
    if stage == "response":
        return asdict(institution.parse_response(game, action))
    institution.require(stage == "vote", "action stage")
    return dict(vote=institution.parse_vote(action))
