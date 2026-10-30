"""Offline tests with fabricated streams only; not research evidence."""
import json
from decimal import Decimal

import pytest

from paper3 import agenda_rights as game
from experiments import paper3_deepseek_disclosure_a3 as run
from experiments import paper3_deepseek_fresh_profiles as base
from paper3.audit_runtime import PilotStore

SECRET = "sk-test-secret"


def chunk(**fields):
    return "data: " + json.dumps(fields)


def stream(content, reasoning="considering", finish="stop", done=True, model=run.MODEL,
           provider=run.PROVIDER_NAME, cost=0.0002, usage=True):
    lines = [": OPENROUTER PROCESSING",
             chunk(id="gen-abc", model=model, provider=provider,
                   choices=[dict(index=0, delta=dict(reasoning=reasoning), finish_reason=None)]),
             ": OPENROUTER PROCESSING",
             chunk(id="gen-abc", model=model, provider=provider,
                   choices=[dict(index=0, delta=dict(content=content), finish_reason=finish)])]
    if usage:
        lines.append(chunk(id="gen-abc", model=model, provider=provider,
                           choices=[dict(index=0, delta=dict(content=""), finish_reason=finish)],
                           usage=dict(prompt_tokens=120, completion_tokens=60, cost=cost,
                                      completion_tokens_details=dict(reasoning_tokens=40))))
    if done:
        lines.append("data: [DONE]")
    return lines


def ok(lines):
    return dict(http_status=200, lines=lines, generation_id="gen-abc", error=None)


def reset(lines=()):
    return dict(http_status=200, lines=list(lines), generation_id="gen-abc", error="ConnectionResetError")


def gen_ok(cost=0.0003):
    return lambda gid, secret: dict(model=run.MODEL, provider_name=run.PROVIDER_NAME, total_cost=cost)


def store(tmp_path, name="shard"):
    return PilotStore(tmp_path / name, dict(test=name), [])


def a_case(seed=1):
    return dict(name="c", seed=seed, messages=[dict(role="system", content="s"), dict(role="user", content="u")])


def test_assemble_skips_keepalives_and_requires_terminal_usage():
    response, complete = run.assemble(stream('{"policy_id":"p1","message":"hi"}'))
    assert complete
    assert response["choices"][0]["message"]["content"] == '{"policy_id":"p1","message":"hi"}'
    assert response["choices"][0]["message"]["reasoning"] == "considering"
    assert response["provider"] == run.PROVIDER_NAME and response["usage"]["cost"] == 0.0002
    assert not run.assemble(stream("x", done=False))[1]
    assert not run.assemble(stream("x", usage=False))[1]
    assert not run.assemble(stream("x", finish=None))[1]
    errored = stream("x")[:-1] + [chunk(error=dict(message="boom"), choices=[dict(delta={}, finish_reason="error")])]
    assert not run.assemble(errored)[1]


def test_request_streams_with_usage_and_keeps_frozen_routing():
    request = run.request_for(a_case())
    frozen = base.request_for(a_case())
    assert request["stream"] is True and request["usage"] == dict(include=True)
    assert {k: v for k, v in request.items() if k not in ("stream", "usage")} == \
        {k: v for k, v in frozen.items() if k != "stream"}
    assert request["provider"]["allow_fallbacks"] is False


def test_answered_call_is_verified_and_answer_checked(tmp_path):
    backend = run.Backend(store(tmp_path), SECRET, "episodes",
                          transport=lambda wire, s: ok(stream('{"policy_id":"p1"}')), generation=gen_ok())
    key, raw = run.answer(backend, a_case())
    row = json.loads((tmp_path / "shard/calls" / (key + ".json")).read_text())
    assert raw == '{"policy_id":"p1"}'
    assert row["outcome"] == "answered" and row["verified_cost_usd"] == "0.0002" and row["attempt"] == 1
    assert SECRET not in json.dumps(row)


def test_single_declared_reissue_after_certified_transport_failure(tmp_path):
    sent = []
    def transport(wire, secret):
        sent.append(wire)
        return reset(stream("{}")[:2]) if len(sent) == 1 else ok(stream('{"policy_id":"p2"}'))
    backend = run.Backend(store(tmp_path), SECRET, "episodes", transport=transport, generation=gen_ok(0.0005))
    key, raw = run.answer(backend, a_case())
    assert raw == '{"policy_id":"p2"}' and len(sent) == 2 and sent[0] == sent[1]
    rows = sorted(backend.rows(), key=lambda r: r["attempt"])
    assert [r["outcome"] for r in rows] == ["transport_certified", "answered"]
    assert rows[0]["certified_cost_usd"] == "0.0005" and rows[0]["transport_error"] == "ConnectionResetError"
    assert backend.halt is None
    # Replaying reads the recorded rows; no new transmission.
    again = run.Backend(backend.store, SECRET, "episodes", transport=lambda *a: pytest.fail("resent"))
    assert run.answer(again, a_case())[1] == raw


def test_two_transport_failures_fail_only_the_episode(tmp_path):
    backend = run.Backend(store(tmp_path), SECRET, "episodes",
                          transport=lambda wire, s: reset(), generation=gen_ok())
    with pytest.raises(run.TransportFailed):
        run.answer(backend, a_case())
    assert backend.halt is None and len(backend.rows()) == 2
    assert not (tmp_path / "batch_stop.json").exists()


def test_uncertified_charge_halts_shard_but_not_batch(tmp_path):
    backend = run.Backend(store(tmp_path), SECRET, "episodes",
                          transport=lambda wire, s: reset(), generation=lambda gid, s: None)
    with pytest.raises(base.Halt):
        run.answer(backend, a_case())
    assert backend.halt.startswith("uncertified")
    row = backend.rows()[0]
    assert run.row_cost(row) == Decimal(row["reserved_usd"])
    assert not (tmp_path / "batch_stop.json").exists()


def test_routing_mismatch_halts_every_shard(tmp_path):
    backend = run.Backend(store(tmp_path), SECRET, "episodes",
                          transport=lambda wire, s: ok(stream("{}", provider="OtherCloud")), generation=gen_ok())
    with pytest.raises(base.Halt):
        run.answer(backend, a_case())
    assert (tmp_path / "batch_stop.json").exists()
    other = run.Backend(store(tmp_path, "other"), SECRET, "episodes",
                        transport=lambda *a: pytest.fail("admitted after stop"))
    with pytest.raises(base.Halt):
        run.answer(other, a_case())


def test_interrupted_started_call_is_never_regenerated(tmp_path):
    backend = run.Backend(store(tmp_path), SECRET, "episodes", transport=lambda *a: pytest.fail("sent"))
    request = run.request_for(a_case())
    key = run.digest(dict(request=request, phase="episodes", protocol=backend.store.protocol_hash, attempt=1))
    backend.store.save("calls", key, dict(status="started", reserved_usd="0.03"))
    with pytest.raises(base.Halt):
        run.answer(backend, a_case())


def test_budget_ceiling_blocks_admission(tmp_path, monkeypatch):
    monkeypatch.setitem(run.LIMITS, "episodes", (120, Decimal("0.001")))
    backend = run.Backend(store(tmp_path), SECRET, "episodes", transport=lambda *a: pytest.fail("sent"))
    with pytest.raises(base.Halt):
        run.answer(backend, a_case())
    assert backend.rows() == []


def test_gate_cases_expected_answers_and_scoring():
    cases = run.gate_cases()
    assert len(cases) == 8 and len({c["seed"] for c in cases}) == 8
    for case in cases:
        system = case["messages"][0]["content"]
        assert "1/2" in system and "has occurred" not in system
        context = json.loads(case["messages"][1]["content"].split("\n", 1)[0])
        tally = sum(v == "policy_m" for v in context["pairwise_ballots"].values())
        majority = "policy_m" if tally >= 4 else "policy_k"
        exp = case["expected"]
        assert exp["selected_if_leader_rule"] == context["leader_choice"]
        assert exp["selected_if_ballot_rule"] == majority
        u = context["own_principal_utilities"]
        assert Decimal(exp["expected_utility"]) == (Decimal(u[context["leader_choice"]]) + u[majority]) / 2
        good = dict(exp)
        assert run.gate_score(json.dumps(good), exp)["exact"]
        assert not run.gate_score(json.dumps(dict(good, expected_utility="999")), exp)["exact"]
        assert not run.gate_score(json.dumps(dict(good, expected_utility=float(Decimal(exp["expected_utility"])))), exp)["valid"]
        assert not run.gate_score("oops", exp)["valid"]
    assert {c["expected"]["selected_if_leader_rule"] != c["expected"]["selected_if_ballot_rule"] for c in cases} == {True, False}


def fake_model(wire, secret):
    """Valid answers for gate and legislature requests from the request itself."""
    request = json.loads(wire)
    context = json.loads(request["messages"][1]["content"].split("\n", 1)[0])
    if "leader_choice" in context and "stage" not in context:
        tally = sum(v == "policy_m" for v in context["pairwise_ballots"].values())
        majority = "policy_m" if tally >= 4 else "policy_k"
        u = context["own_principal_utilities"]
        answer = dict(selected_if_leader_rule=context["leader_choice"], selected_if_ballot_rule=majority,
                      expected_utility=str((Decimal(u[context["leader_choice"]]) + u[majority]) / 2))
    else:
        stage = context["stage"]
        candidates = context.get("candidate_policy_ids") or [p["policy_id"] for p in context["profile"]["catalog"]]
        if stage == "ratification":
            answer = dict(votes={p: True for p in candidates})
        elif stage == "pairwise":
            answer = dict(policy_id=candidates[-1])
        else:
            answer = dict(policy_id=candidates[min(1, len(candidates) - 1)], message="fine")
    return ok(stream(json.dumps(answer)))


def test_gate_then_shard_end_to_end_with_fabricated_model(tmp_path):
    gate = run.run_gate(tmp_path, SECRET, transport=fake_model, generation=gen_ok())
    assert gate["passed"] and gate["exact"] == 8
    terminal = run.run_shard(tmp_path, 1, SECRET, transport=fake_model, generation=gen_ok())
    assert terminal["halt"] is None and terminal["calls"] == 91
    assert set(terminal["conditions"].values()) == {"completed"}
    late = json.loads((tmp_path / "profile-1/sessions/late-BD.json").read_text())
    assert late["branch_order"] == ["B", "D"] and late["status"] == "completed"
    early = json.loads((tmp_path / "profile-1/sessions/early-D.json").read_text())
    # Shared seeds: early D and the late prefix use the same seed at each position.
    rows = {r["request"]["seed"] for r in
            (json.loads(p.read_text()) for p in (tmp_path / "profile-1/calls").glob("*.json"))}
    assert rows == set(range(run.SEED_BASE + 1000, run.SEED_BASE + 1025))
    assert early["status"] == "completed"
    # Terminal shard is not rerun.
    assert run.run_shard(tmp_path, 1, SECRET, transport=lambda *a: pytest.fail("rerun")) == terminal


def test_shard_refuses_without_passed_gate(tmp_path):
    with pytest.raises(base.Halt):
        run.run_shard(tmp_path, 0, SECRET, transport=fake_model, generation=gen_ok())


def test_schedule_rotates_and_budget_fits_authorization():
    orders = [run.schedule(i) for i in range(run.SHARDS)]
    assert all(sorted(c for c, _ in o) == ["early", "early", "late"] for o in orders)
    assert len({tuple(o) for o in orders}) >= 3
    total = run.PRIOR_ADDITIONAL_USD + run.LIMITS["gate"][1] + run.SHARDS * run.LIMITS["episodes"][1]
    assert total <= run.AUTHORIZED_USD
    assert run.frame()[1] == [1004003, 1004007, 1004000, 1004005]
