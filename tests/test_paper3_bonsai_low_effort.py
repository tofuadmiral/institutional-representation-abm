import copy
import json
import pytest

from experiments.paper3_bonsai_low_effort import low_request, render_checked, score, LOW_INSTRUCTION, CASES


class Tokenizer:
    def apply_chat_template(self, messages, reasoning_effort, **kwargs):
        assert kwargs == dict(tokenize=False, add_generation_prompt=True, enable_thinking=True)
        return "<|im_start|>system\n" + (LOW_INSTRUCTION if reasoning_effort == "low" else "") + json.dumps(messages) + "<think>\n"

    def encode(self, text, **kwargs):
        return list(text.encode())


def test_low_changes_only_effort_not_source_task_seed_or_cap():
    old = dict(messages=[dict(role="user", content="unchanged task")], seed=17,
               max_tokens=8192, enable_thinking=True, reasoning_effort="medium", temperature=1.0)
    saved = copy.deepcopy(old)
    new = low_request(old)
    assert old == saved
    assert new == {**old, "reasoning_effort": "low"}
    assert len(CASES) == len({case[1] for case in CASES}) == 3
    with pytest.raises(ValueError):
        low_request({**old, "enable_thinking": False})
    with pytest.raises(ValueError):
        low_request({**old, "max_tokens": 4096})


def test_prompt_check_detects_extra_edits_and_tokenizer_drift():
    tokenizer = Tokenizer()
    messages = [dict(role="system", content="rules"), dict(role="user", content="task")]
    prompt = tokenizer.apply_chat_template(messages, reasoning_effort="medium",
        tokenize=False, add_generation_prompt=True, enable_thinking=True)
    old = dict(request=dict(messages=messages), rendered_prompt=prompt, prompt_token_ids=tokenizer.encode(prompt))
    low, ids = render_checked(tokenizer, tokenizer, old)
    assert low.endswith("<think>\n") and ids == tokenizer.encode(low)
    with pytest.raises(ValueError, match="medium prompt"):
        render_checked(tokenizer, tokenizer, {**old, "rendered_prompt": "different"})

    class BadTemplate(Tokenizer):
        def apply_chat_template(self, messages, reasoning_effort, **kwargs):
            value = super().apply_chat_template(messages, reasoning_effort, **kwargs)
            return value + "extra" if reasoning_effort == "low" else value

    class BadTokens(Tokenizer):
        def encode(self, *args, **kwargs):
            return [9]

    with pytest.raises(ValueError, match="more than"):
        render_checked(BadTemplate(), tokenizer, old)
    with pytest.raises(ValueError, match="base tokenizer"):
        render_checked(tokenizer, BadTokens(), old)


def test_feasibility_is_schema_not_preferred_action_and_rejects_truncation():
    schema = dict(package="int", first="str", message="str", support="bool")
    reply = dict(package=3, first="B", message="No agreement", support=False)
    record = dict(cached_tokens=0, prompt_token_ids=[1], generated_token_ids=[2],
        response=dict(usage=dict(prompt_tokens=1, completion_tokens=1),
        choices=[dict(finish_reason="stop", message=dict(content="reasoning</think>" + json.dumps(reply)))]))
    assert score(record, schema) == dict(status="completed", feasible=True, reply=reply)
    for raw, finish in (("reasoning</think>" + json.dumps(reply), "length"),
                        (json.dumps(reply), "stop"),
                        ("reasoning</think>" + json.dumps({**reply, "message": "x" * 401}), "stop"),
                        ("reasoning</think>" + json.dumps({**reply, "first": "A0"}), "stop"),
                        ("reasoning</think>" + json.dumps({**reply, "package": True}), "stop")):
        bad = copy.deepcopy(record)
        bad["response"]["choices"] = [dict(finish_reason=finish, message=dict(content=raw))]
        assert score(bad, schema)["feasible"] is False
