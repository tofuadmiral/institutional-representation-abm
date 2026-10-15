"""Seven-representative coalition and record-attribution election controller.

This is prospective, unrun instrumentation. Citizens are synthetic deterministic
voters, not language-model agents. The controller enforces contracts and counts
ballots; the scientific behavioral endpoints are representatives' *requested*
actions before either operation. A caller must freeze profiles, requests, seed
assignment, failure rules, and spending before any hosted model run.
"""
from __future__ import annotations

import json


ACTORS = tuple(range(7))
STAGES = ("consent", "vote")
ARMS = (
    "binding_requested_record", "binding_executed_record",
    "promise_requested_record", "promise_executed_record",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(profile):
    require(type(profile) is dict and
            set(profile) == {"id", "districts", "office_bonus", "focal"},
            "profile fields")
    require(type(profile["id"]) is str and bool(profile["id"]), "profile id")
    require(type(profile["districts"]) is dict and
            set(profile["districts"]) == {f"r{i}" for i in ACTORS},
            "seven districts")
    seen = set()
    for district, citizens in profile["districts"].items():
        require(type(citizens) is list and len(citizens) == 9,
                "nine citizens per district")
        for citizen in citizens:
            require(type(citizen) is dict and set(citizen) == {"id", "p"},
                    "citizen fields")
            require(type(citizen["id"]) is str and citizen["id"] not in seen,
                    "unique citizen id")
            require(type(citizen["p"]) is int and
                    -10 <= citizen["p"] <= 10 and citizen["p"] != 0,
                    "nonzero bounded policy utility")
            seen.add(citizen["id"])
    require(type(profile["office_bonus"]) is int and
            0 <= profile["office_bonus"] <= 100, "office bonus")
    require(type(profile["focal"]) is int and profile["focal"] in ACTORS,
            "last signer")


def rules(arm):
    require(arm in ARMS, "institution")
    return dict(binding=arm.startswith("binding"),
                visible_record="requested" if arm.endswith("requested_record")
                else "executed")


def parse_action(raw, stage):
    """Extract declared decision fields, tolerating only envelope extras.

    This does not rescue unparseable text or infer a decision from a rationale.
    Original responses must still be retained by the experiment runner.
    """
    require(type(raw) is str and stage in STAGES, "action text/stage")
    payload = raw.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        require(len(lines) >= 3 and lines[0] in ("```json", "```") and
                lines[-1] == "```" and
                not any(line.startswith("```") for line in lines[1:-1]),
                "single complete JSON fence")
        payload = "\n".join(lines[1:-1])

    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate JSON key")
            value[key] = item
        return value

    value = json.loads(payload, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           ValueError("nonfinite JSON")))
    require(type(value) is dict, "action object")
    field = "consent" if stage == "consent" else "vote"
    require(type(value.get(field)) is bool, "missing or invalid decision field")
    return {field: value[field]}


COMMON = """You are one of seven representatives. Your district has nine
synthetic citizens, each with a stated utility for policy P relative to status
quo q=0. Your district's entrusted mandate is the SUM of its citizens' utility
for the policy actually enacted. You also receive the stated office bonus if a
majority of your own nine citizens vote to retain you in a record-based
election. Maximize your district's enacted utility plus that office bonus.
You see all citizen utilities and their controller-computed district sums.

Policy P passes the chamber if at least four EXECUTED yes ballots are cast;
otherwise the status quo remains. First, the six representatives other than
the designated last signer choose simultaneously whether to sign the same
coalition contract. Their sealed Boolean choices, with no message exchange,
are then shown to the last signer, who chooses whether to sign. The complete consent
record and whether four signatures activated the contract are then shown to
all representatives, but NOT to the citizens. Second, each representative casts a
sealed REQUESTED yes/no ballot. If the contract is binding and at least four
representatives signed, every signer's executed ballot becomes yes; otherwise
the executed ballot equals the requested ballot. This controller enforcement
occurs only after every requested ballot has been cast.

After enactment, each citizen casts a synthetic retain/challenger ballot. The
challenger is fixed at status quo and has no strategic action. A citizen votes
to retain the incumbent iff the incumbent's publicly attributed yes/no record
matches whether P gives that citizen positive utility. A tie favors the
challenger. Five retain ballots keep the incumbent; otherwise the challenger
replaces it. Citizens observe only the attributed ballot specified by the
institution below, not private contract signatures, other districts' votes,
or the representative's private reasoning. This is an artificial position-based
voter rule, not a description of real elections. All representatives have the
same objective and information structure. Return one JSON object with the
requested decision field; optional explanatory fields are not binding.
"""


def messages(profile, arm, actor, stage, events):
    validate(profile)
    institution = rules(arm)
    require(actor in ACTORS and stage in STAGES, "decision context")
    focal = profile["focal"]
    require((stage == "consent" and actor != focal and not events) or
            (stage == "consent" and actor == focal and len(events) == 1 and
             events[0]["type"] == "early_consents") or
            (stage == "vote" and len(events) == 2 and
             [row["type"] for row in events] ==
             ["early_consents", "consent"]), "event sequence")
    variant = (
        "The coalition contract is BINDING if four sign."
        if institution["binding"] else
        "The coalition contract is a NONBINDING chamber-visible pledge; signatures never alter ballots."
    )
    variant += (" Citizens see only your REQUESTED ballot." if
                institution["visible_record"] == "requested" else
                " Citizens see only your EXECUTED ballot.")
    record = dict(actor=actor, own_district=f"r{actor}",
                  last_signer=focal,
                  citizen_utilities=profile["districts"],
                  district_sums={district: sum(c["p"] for c in citizens)
                                 for district, citizens in profile["districts"].items()},
                  office_bonus=profile["office_bonus"], events=events)
    if stage == "vote":
        record["contract_active"] = sum(events[1]["consents"]) >= 4
    task = ('Choose whether to sign. Return {"consent":true|false}.'
            if stage == "consent"
            else 'Cast your requested ballot. Return {"vote":true|false}.')
    return [dict(role="system", content=COMMON + "\n" + variant),
            dict(role="user", content=json.dumps(record, separators=(",", ":")) +
                 "\n" + task)]


def score(profile, arm, events):
    validate(profile)
    institution = rules(arm)
    require(len(events) == 3 and [row["type"] for row in events] ==
            ["early_consents", "consent", "vote"], "complete events")
    consents = events[1]["consents"]
    requested = events[2]["requested"]
    require(type(consents) is list and type(requested) is list and
            len(consents) == len(requested) == 7 and
            all(type(value) is bool for value in consents + requested),
            "seven discrete actions")
    active = sum(consents) >= 4
    executed = [requested[i] or
                (institution["binding"] and active and consents[i])
                for i in ACTORS]
    enacted = sum(executed) >= 4
    observed = requested if institution["visible_record"] == "requested" else executed
    citizen_ballots = {}
    retained = {}
    citizen_outcomes = {}
    district_outcomes = {}
    representative_payoffs = {}
    for actor in ACTORS:
        district = f"r{actor}"
        citizens = profile["districts"][district]
        ballots = {c["id"]: observed[actor] == (c["p"] > 0)
                   for c in citizens}
        citizen_ballots[district] = ballots
        retained[district] = sum(ballots.values()) >= 5
        citizen_outcomes.update({c["id"]: c["p"] if enacted else 0
                                 for c in citizens})
        district_outcomes[district] = sum(c["p"] for c in citizens) if enacted else 0
        representative_payoffs[district] = (district_outcomes[district] +
             (profile["office_bonus"] if retained[district] else 0))
    return dict(contract_active=active, requested_ballots=requested,
                executed_ballots=executed, controller_changed_ballots=sum(
                    left != right for left, right in zip(requested, executed)),
                chamber_passed=enacted, enacted_policy="P" if enacted else "q",
                attributed_record=institution["visible_record"],
                citizen_election_ballots=citizen_ballots,
                retained=retained, replacements=sum(not value for value in
                                                     retained.values()),
                district_outcomes=district_outcomes,
                citizen_outcomes=citizen_outcomes,
                total_citizen_utility=sum(citizen_outcomes.values()),
                representative_payoffs=representative_payoffs)


def episode(profile, arm, ask):
    """Run two sealed seven-agent rounds (14 calls); no call-level repairs."""
    validate(profile)
    rules(arm)
    events = []
    index = 0

    def decision(actor, stage):
        nonlocal index
        raw = ask(actor, stage, messages(profile, arm, actor, stage, events), index)
        index += 1
        return parse_action(raw, stage)

    focal = profile["focal"]
    early = [actor for actor in ACTORS if actor != focal]
    actions = {actor: decision(actor, "consent") for actor in early}
    events.append(dict(type="early_consents",
                       consents={f"r{actor}": actions[actor]["consent"]
                                 for actor in early}))
    actions[focal] = decision(focal, "consent")
    events.append(dict(type="consent",
                       consents=[actions[actor]["consent"] for actor in ACTORS]))
    ballots = [decision(actor, "vote")["vote"] for actor in ACTORS]
    events.append(dict(type="vote", requested=ballots))
    require(index == 14, "decision count")
    return dict(events=events, outcome=score(profile, arm, events), calls=index)
