import itertools
import pytest

from jev_study.bill_choice import make_cases, score, request_for


def test_fixtures_have_unique_oracle_and_no_label_leakage():
    cases = make_cases()
    assert len(cases) == 96
    for _, paired in itertools.groupby(cases, key=lambda c: c["base_seed"]):
        rows = list(paired)
        indices = []
        for c in rows:
            keys = c["preference_keys"]
            assert len(set(keys.values())) == 4
            assert c["expected"] == max(keys, key=keys.get)
            assert "expected" not in c["request"]
            indices.append(c["label_to_policy_index"][c["expected"]])
        assert len(set(indices)) == 1


def test_scores_probabilities_not_confidence_and_keeps_zero_probability_errors():
    c = make_cases()[0]
    target = c["expected"]
    options = c["request"]["questions"]["bill"]["criteria"]
    response = dict(answers=dict(bill=dict(type="choice", choice=target, confidence=0.1,
        probabilities={k: float(k == target) for k in options})))
    r = score(c, response)
    assert r["correct"] and r["brier"] == 0 and r["selected_probability"] == 1
    wrong = next(k for k in options if k != target)
    response["answers"]["bill"].update(choice=wrong, probabilities={k: float(k == wrong) for k in options})
    r = score(c, response)
    assert r["infinite_log_loss"] and r["log_loss"] is None and r["brier"] == 2
    response["answers"]["bill"]["probabilities"][wrong] = 0.2
    with pytest.raises(ValueError):
        score(c, response)


def test_live_request_requires_version_and_excludes_oracle():
    case = make_cases()[0]
    with pytest.raises(ValueError):
        request_for(case, "jev-latest")
    request = request_for(case, "version-for-unit-test-only")
    assert set(request) == {"model", "state", "questions"}
