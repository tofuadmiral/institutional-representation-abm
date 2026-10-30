import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.paper3_bonsai_budgeted_episode import (
    BoundaryRecorder, CAP, THINKING, MAX_CALLS, fixtures, request_for,
    private_score, render, collective_messages, run_episode, EpisodeBackend,
)
from tests.test_paper3_bonsai_low_effort import Tokenizer


def test_fresh_balanced_cases_and_fixed_budget():
    cases, p = fixtures()
    assert p.key == "seed1103-leader0" and p.formateur == 0
    assert [c["expected"]["accept"] for c in cases] == [True, False, False, True]
    assert [c["expected"]["principal_utility_if_accepted"] for c in cases][1:3] == [-4, -12]
    assert len({c["seed"] for c in cases}) == 4
    assert MAX_CALLS * CAP == 52224
    assert request_for("model", [], 1)["enable_thinking"] is True
    assert request_for("model", [], 1)["thinking_budget"] == 1024


def installed_controller():
    # Execute only the installed pure-Python class; no MLX import or model call.
    path = Path("results/paper3/runtimes/bonsai2/lib/python3.13/site-packages/mlx_vlm/utils.py")
    if not path.exists():
        pytest.skip("optional pinned local runtime unavailable")
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ThinkingBudgetCriteria")
    scope = dict(Optional=__import__("typing").Optional, List=list,
                 mx=SimpleNamespace(array=lambda x: x))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), scope)
    tokenizer = SimpleNamespace(encode=lambda text, **kw: [{"<think>": 1, "</think>": 2, "\n": 3}[text]])
    return scope["ThinkingBudgetCriteria"](tokenizer, THINKING, "</think>", "<think>", True)


def simulate(tokens, eos=True):
    c, b = installed_controller(), BoundaryRecorder()
    for i, sampled in enumerate(tokens):
        # Mirror AR order: use previous schedule, controller sees emitted token,
        # observer reads it before generator resumes and applies the next override.
        token = c.apply_forced_token([sampled])[0]
        c(token)
        b.observe(SimpleNamespace(token=token, generation_tokens=i + 1, finish_reason=None), c)
    if eos:
        c(99)
        b.observe(SimpleNamespace(token=99, generation_tokens=len(tokens) + 1, finish_reason="stop"), c)
    else:
        b.observe(SimpleNamespace(token=b.tokens[-1], generation_tokens=len(tokens), finish_reason="length"), c)
    return b


def test_installed_counter_stream_forcing_and_duplicate_terminal():
    b = simulate([9] * 1100)
    summary = b.summary(2)
    assert summary["closing_positions"] == [1026]
    assert [s["position"] for s in summary["emitted_forced_tokens"]] == [1025, 1026]
    assert summary["forced_output_tokens"] == 2
    assert summary["sampled_output_tokens"] == 1099
    assert summary["closure_origin"] == "forced"
    natural = simulate([9, 2, 7]).summary(2)
    assert natural["closure_origin"] == "natural" and natural["forced_output_tokens"] == 0
    capped = simulate([9] * 1025, eos=False).summary(2)
    assert len(capped["schedules"]) == 1 and capped["forced_output_tokens"] == 0
    assert capped["closure_origin"] == "absent"
    assert simulate([1] * CAP, eos=False).summary(2)["closure_origin"] == "absent"
    b.tokens[1026] = 8
    with pytest.raises(ValueError, match="not emitted"):
        b.summary(2)


def good_record(reply):
    return dict(cached_tokens=0, prompt_token_ids=[1], generated_token_ids=[9, 2, 7, 99],
        boundary=dict(sampled_output_tokens=4, forced_output_tokens=0),
        response=dict(usage=dict(prompt_tokens=1, completion_tokens=4),
            choices=[dict(finish_reason="stop", message=dict(content="brief thought</think>" + json.dumps(reply)))]))


def test_gate_rejects_wrong_payoff_action_schema_markers_and_cutoff():
    case = fixtures()[0][0]
    assert private_score(good_record(case["expected"]), case)["exact"]
    for bad in ({**case["expected"], "principal_utility_if_accepted": 999},
                {**case["expected"], "accept": False}, {**case["expected"], "extra": 1},
                {**case["expected"], "accept": 1}):
        assert not private_score(good_record(bad), case)["exact"]
    for content, finish in (("<think>reason</think>{}", "stop"), ("unfinished", "length")):
        record = good_record(case["expected"])
        record["response"]["choices"][0] = dict(finish_reason=finish, message=dict(content=content))
        assert private_score(record, case)["status"] == "failed"


def test_dynamic_tokenization_and_message_transform_preserve_events():
    messages = [dict(role="system", content="rules"), dict(role="user", content='{}\nmessage (string)')]
    saved = copy.deepcopy(messages)
    changed = collective_messages(messages)
    assert messages == saved and "400 characters" in changed[-1]["content"]
    assert json.loads(changed[-1]["content"].split("\n")[0]) == {}
    render(Tokenizer(), Tokenizer(), changed)
    class Wrong(Tokenizer):
        def encode(self, *args, **kwargs):
            return [3]
    with pytest.raises(ValueError):
        render(Tokenizer(), Wrong(), changed)


class ScriptedNative:
    def __init__(self, fail_at=None):
        self.calls, self.fail_at = [], fail_at

    def call(self, messages, seed, base):
        i = len(self.calls)
        assert seed == 113000 + i
        self.calls.append(messages)
        task = messages[-1]["content"].split("\n", 1)[1]
        if "support (boolean)" in task:
            reply = dict(support=False, package=3, first="B", message="reject")
        elif "package (integer" in task:
            reply = dict(package=3, first="B", message="offer")
        elif "sign (boolean" in task:
            reply = dict(sign=False)
        elif "obligation_due (boolean" in task:
            reply = dict(obligation_due=False, vote=False)
        else:
            reply = dict(vote=False)
        record = good_record(reply)
        if i == self.fail_at:
            record["response"]["choices"][0]["finish_reason"] = "length"
        return str(i), record


def test_complete_no_deal_no_passage_is_valid_and_failure_never_filled():
    p = fixtures()[1]
    native = ScriptedNative()
    result = run_episode(EpisodeBackend(native, None), p)
    assert result["status"] == "completed" and len(native.calls) == 30
    assert result["state"]["signers"] == []
    assert not result["first_passed"] and not result["second_passed"]
    assert set(result["realized_utility"].values()) == {0}
    # Simultaneous responses share the same prior official events.
    assert len({json.dumps(json.loads(m[-1]["content"].split("\n")[0])["events"], sort_keys=True)
                for m in native.calls[1:8]}) == 1
    failed = ScriptedNative(fail_at=2)
    result = run_episode(EpisodeBackend(failed, None), p)
    assert result["status"] == "failed" and len(result["call_keys"]) == 3
    assert "realized_utility" not in result and len(failed.calls) == 3


def test_independent_audit_agrees_with_installed_controller_and_detects_request_drift():
    from analysis.paper3_budgeted_episode_audit import expected_boundary, Replay
    for tokens, eos in (([9] * 1100, True), ([9, 2, 7], True),
                        ([9] * 1025, False), ([1] * CAP, False)):
        recorded = simulate(tokens, eos=eos)
        assert expected_boundary(recorded.tokens, 1, 2, 3, "stop" if eos else "length") == recorded.summary(2)
    messages = fixtures()[0][0]["messages"]
    record = dict(request=request_for("model", messages, 9))
    replay = Replay(dict(model="model"), {"key": record}, ["key"])
    assert replay.call(messages, 9, None) == ("key", record)
    replay = Replay(dict(model="model"), {"key": record}, ["key"])
    with pytest.raises(ValueError, match="request replay mismatch"):
        replay.call(messages, 10, None)


def test_raw_text_and_prompt_tokens_cannot_drift_silently():
    from analysis.paper3_budgeted_episode_audit import verify_tokenization
    class Decoder(Tokenizer):
        def decode(self, tokens, **kwargs):
            return bytes(tokens).decode()
    t = Decoder()
    messages = fixtures()[0][0]["messages"]
    prompt, ids = render(t, t, messages)
    row = dict(request=dict(messages=messages), rendered_prompt=prompt, prompt_token_ids=ids,
               generated_token_ids=list(b"raw") + [999],
               response=dict(choices=[dict(finish_reason="stop", message=dict(content="raw"))]))
    verify_tokenization(row, t, t, {999})
    for key, value, error in (("prompt_token_ids", [3], "prompt/token"),
                              ("generated_token_ids", list(b"raw"), "EOS")):
        with pytest.raises(ValueError, match=error):
            verify_tokenization({**row, key: value}, t, t, {999})
    bad = copy.deepcopy(row)
    bad["response"]["choices"][0]["message"]["content"] = "different"
    with pytest.raises(ValueError, match="raw response"):
        verify_tokenization(bad, t, t, {999})
