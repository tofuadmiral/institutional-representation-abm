import copy
import inspect
import json

import pytest

from paper3 import agenda_rights as game
from experiments import paper3_bonsai_agenda as study
from analysis.paper3_agenda_audit import Replay
from tests.test_paper3_bonsai_budgeted_episode import good_record


def test_spatial_certificates_and_true_outside_option():
    p, control = game.profiles()
    assert p["utilities"]["r0"]["p3"] == 107
    assert p["utilities"]["r0"]["p1"] == 90
    assert p["utilities"]["r0"]["p6"] == 44
    assert p["utilities"]["r1"]["p3"] == -59 and p["utilities"]["r1"]["p6"] == 4
    assert sum(row["p6"] > row["p3"] for row in p["utilities"].values()) == 4
    assert sum(row["p1"] > row["p3"] for row in p["utilities"].values()) == 5
    for pol in ("p1", "p3"):
        assert sum(row[pol] > 0 for row in p["utilities"].values()) == 5
    assert game.metrics(p, "p3")["mean_regret"] == pytest.approx(.41224750769873164)
    assert game.metrics(p, "p1")["mean_regret"] == pytest.approx(.18411345858364242)
    for profile in (p, control):
        points = {x["policy_id"]: x["coordinates"] for x in profile["catalog"]}
        for actor, principal in profile["principals"].items():
            for pid, point in points.items():
                actual = sum(principal["weights"][j] * (point[j] - principal["ideal"][j])**2 for j in (0,1))
                assert actual == profile["losses"][actor][pid]
                assert profile["utilities"][actor][pid] == profile["losses"][actor]["q"] - actual
    for row in control["utilities"].values():
        ordered = [row["q"]] + [row[f"p{i}"] for i in range(1,8)]
        assert all(x < y for x,y in zip(ordered, ordered[1:]))


@pytest.mark.parametrize("arm", game.ARMS)
def test_selector_and_ratification_all_tally_boundaries(arm):
    p = game.profiles()[0]
    for amendment_yes in range(8):
        votes = {r: "p1" if i < amendment_yes else "p3" for i,r in enumerate(game.ROLES)}
        for ratify_yes in range(8):
            # Opposite answers for the two policies catch illicit ballot reuse.
            cards = {r: {"p3": i < ratify_yes, "p1": i >= ratify_yes} for i,r in enumerate(game.ROLES)}
            for leader in ("p1", "p3"):
                result = game.resolve(p, arm, "p3", "p1", votes, leader, cards)
                selected = leader if arm == "D" else "p1" if amendment_yes >= 4 else "p3"
                yes = ratify_yes if selected == "p3" else 7 - ratify_yes
                assert result == dict(selected=selected, ratification_yes=yes, passed=yes>=4, outcome=selected if yes>=4 else "q")


def test_single_candidate_and_missing_votes():
    p = game.profiles()[0]
    ballots = {r:"p1" for r in game.ROLES}
    cards = {r:{"p1":True} for r in game.ROLES}
    assert game.resolve(p, "B", "p1", "p1", ballots, "p1", cards)["outcome"] == "p1"
    del cards["r6"]
    with pytest.raises(ValueError):
        game.resolve(p, "B", "p1", "p1", ballots, "p1", cards)


@pytest.mark.parametrize("raw,stage", [
    ('{"policy_id":"missing","message":""}', "opening"),
    ('{"policy_id":true,"message":""}', "opening"),
    ('{"policy_id":"p1","message":1}', "opening"),
    ('{"policy_id":"p1","policy_id":"p3","message":""}', "opening"),
    ('{"votes":{"p1":1,"p3":false}}', "ratification"),
    ('{"votes":{"p1":true}}', "ratification"),
    ('{"votes":{"p1":true,"p3":false,"q":false}}', "ratification"),
    ('{"votes":{"p1":true,"p1":false,"p3":true}}', "ratification"),
    ('{"policy_id":"p1","reason":"extra"}', "pairwise"),
])
def test_strict_actions_no_repair(raw, stage):
    with pytest.raises(ValueError):
        game.validate_action(raw, stage, ["p1","p3"])


def test_gate_balanced_and_no_forgiveness():
    cases = game.gate_cases()
    assert len(cases) == 8 and len({c["seed"] for c in cases}) == 8
    assert sum(c["expected"]["selected_policy"] == "policy_k" for c in cases) == 4
    for case in cases:
        context = json.loads(case["messages"][-1]["content"].split("\n", 1)[0])
        counts = list(context["pairwise_ballots"].values()).count(context["amendment"])
        selected = context["leader_choice"] if case["arm"] == "D" else context["amendment"] if counts >= 4 else context["locked_proposal"]
        assert selected == case["expected"]["selected_policy"]
        assert case["expected"]["votes"] == {p: context["own_principal_utilities"][p] > 0 for p in ("policy_k", "policy_m")}
        assert study.score_gate(good_record(case["expected"]), case)["exact"]
        wrong = copy.deepcopy(case["expected"])
        wrong["votes"]["policy_k"] = not wrong["votes"]["policy_k"]
        assert not study.score_gate(good_record(wrong), case)["exact"]
        for kind in ("cutoff", "reopen", "wrong_selector", "numeric_boolean"):
            record = good_record(case["expected"])
            if kind == "cutoff":
                record["response"]["choices"][0]["finish_reason"] = "length"
            elif kind == "reopen":
                record["response"]["choices"][0]["message"]["content"] = "<think>again</think>{}"
            else:
                reply = copy.deepcopy(case["expected"])
                if kind == "wrong_selector":
                    reply["selected_policy"] = "policy_m" if reply["selected_policy"] == "policy_k" else "policy_k"
                else:
                    reply["votes"]["policy_k"] = 1
                record = good_record(reply)
            assert not study.score_gate(record, case)["exact"]


class Scripted:
    def __init__(self, spec, bad_at=None, cutoff_at=None, long_at=None):
        self.spec, self.calls, self.records = spec, [], {}
        self.bad_at, self.cutoff_at, self.long_at = bad_at, cutoff_at, long_at

    def call(self, messages, seed, base):
        i = len(self.calls)
        assert seed == self.spec["seed"] + i
        self.calls.append(copy.deepcopy(messages))
        context = json.loads(messages[-1]["content"].split("\n",1)[0])
        p, actor, stage = context["profile"], context["representative"], context["stage"]
        policy = "p7" if p["name"] == "common_interest" else "p3" if self.spec["arm"] == "D" else "p1"
        if stage == "ratification":
            reply = dict(votes={pid:p["utilities"][actor][pid] > 0 for pid in context["candidate_policy_ids"]})
        elif stage == "pairwise":
            reply = dict(policy_id=policy)
        else:
            reply = dict(policy_id=policy, message="x" * 477 if i == self.long_at else "proposal")
        if i == self.bad_at:
            reply = dict(policy_id="invalid", message="invalid")
        row = good_record(reply)
        if i == self.cutoff_at:
            row["response"]["choices"][0]["finish_reason"] = "length"
        row["request"] = study.request_for("model", messages, seed)
        self.records[str(i)] = row
        return str(i), row


@pytest.mark.parametrize("index", range(4))
def test_full_episode_simultaneity_replay_and_anticipation(index):
    spec = study.specifications()[index]
    native = Scripted(spec, long_at=2)
    result = study.run_one(native, None, spec)
    assert result["status"] == "completed" and len(native.calls) == 25
    expected = "p7" if spec["profile"]["name"] == "common_interest" else "p3" if spec["arm"] == "D" else "p1"
    assert result["resolution"]["outcome"] == expected
    # A=P is legitimate and replay has no selector effect, despite adapted proposals.
    assert result["replay"]["D"]["outcome"] == result["replay"]["B"]["outcome"] == expected
    assert sum(a["overlong_message"] for a in result["actions"]) == 1
    for start,stop,stages in ((1,8,["opening"]), (10,17,["opening","responses","locked_proposal","amendment"]),
                             (18,25,["opening","responses","locked_proposal","amendment","pairwise","leader_selection"])):
        histories = [json.loads(m[-1]["content"].split("\n",1)[0])["official_events"] for m in native.calls[start:stop]]
        assert all(h == histories[0] for h in histories)
        assert [e["stage"] for e in histories[0]] == stages
    revised = json.loads(native.calls[8][-1]["content"].split("\n",1)[0])
    assert len(revised["official_events"][1]["actions"]["r1"]["message"]) == 477
    replay = Replay(dict(model="model"), native.records, result)
    assert study.run_one(replay, None, spec) == result
    altered = copy.deepcopy(native.records)
    altered["3"]["request"]["messages"][0]["content"] += "changed"
    with pytest.raises(RuntimeError, match="replay mismatch"):
        study.run_one(Replay(dict(model="model"), altered, result), None, spec)


@pytest.mark.parametrize("failure", ("bad_at", "cutoff_at"))
def test_failed_episode_has_no_fabricated_payoff(failure):
    spec = study.specifications()[0]
    native = Scripted(spec, **{failure:13})
    result = study.run_one(native, None, spec)
    assert result["status"] == "failed" and len(result["call_keys"]) == 14
    assert "resolution" not in result and "metrics" not in result
    replay = Replay(dict(model="model"), native.records, result)
    assert study.run_one(replay, None, spec) == result


def test_inference_policy_copy_preserves_predecessor_and_hard_cap():
    old_source = inspect.getsource(study.old.BudgetBackend.call)
    new_source = inspect.getsource(study.BudgetBackend.call)
    assert new_source == old_source.replace('raise ValueError("interrupted call is not retried")', 'raise RuntimeError("interrupted call is not retried")')
    assert study.old.MAX_CALLS == 34 and study.MAX_CALLS == 108
    assert study.CAP * study.MAX_CALLS == 165888
    assert study.request_for("model", [], 0) == study.old.request_for("model", [], 0)
    assert len(game.gate_cases()) + len(study.specifications()) * 25 == 108
