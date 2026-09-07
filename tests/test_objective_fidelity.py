from __future__ import annotations

import json
from collections import Counter

import pandas as pd
import pytest

from agent_exploration.local_models import CachedChatBackend
from agent_exploration.llm_protocols import (
    PUBLIC_VOTE_EXPOSURE,
    _standardized_argument,
    generate_model_baseline,
    run_model_argument_mechanism,
    run_model_open_deliberation,
    run_model_private_ballot,
    run_model_public_vote_exposure,
)
from agent_exploration.objective_metrics import evaluate_outcome
from agent_exploration.objective_protocols import (
    COALITION_DISCIPLINE,
    DELEGATED_LEADER,
    OPEN_DELIBERATION,
    PRIVATE_BALLOT,
    coalition_discipline,
    delegated_leader,
    open_deliberation,
    private_ballot,
)
from agent_exploration.objective_scenarios import (
    PreferenceScenario,
    generate_objective_task,
)
from agent_exploration.representatives import (
    LocalModelRepresentative,
    _initial_choice_prompt,
    parse_choice,
)
from experiments.objective_fidelity import (
    run_objective_fidelity,
    summarize_objective_fidelity,
)
from experiments.local_baseline_fidelity import (
    assess_baseline_gate,
    run_local_baseline_fidelity,
    summarize_local_baseline,
)
from experiments.llm_institutional_pilot import (
    paired_treatment_effects,
    summarize_action_effects,
)


class FakeBackend:
    model = "fake-local-model"

    def __init__(self, response: str):
        self.response = response
        self.calls = 0
        self.messages = []

    def generate(self, messages, *, temperature=0.0, max_tokens=256):
        self.calls += 1
        self.messages.append(messages)
        return self.response


def test_generated_baseline_actions_minimize_principal_distance():
    task = generate_objective_task(seed=3, scenario=PreferenceScenario.FRAGMENTED)
    metrics = evaluate_outcome(task, private_ballot(task))
    assert metrics["institution"] == PRIVATE_BALLOT
    assert metrics["institutional_drift_mean"] == pytest.approx(0.0)
    assert metrics["preference_retention_rate"] == 1.0


def test_delegation_concentrates_decision_authority_and_can_create_drift():
    task = generate_objective_task(seed=4, scenario=PreferenceScenario.POLARIZED)
    outcome = delegated_leader(task)
    assert outcome.institution == DELEGATED_LEADER
    assert len({a.alternative_id for a in outcome.final_actions}) == 1
    metrics = evaluate_outcome(task, outcome)
    assert metrics["effective_decision_makers"] == 1
    assert metrics["institutional_drift_mean"] > 0
    leader_choice = task.action_for_agent(task.leader_id).alternative_id
    expected_retention = sum(
        action.alternative_id == leader_choice for action in task.initial_actions
    ) / len(task.initial_actions)
    assert metrics["preference_retention_rate"] == expected_retention


def test_default_group_size_is_seven_and_odd_profiles_are_balanced():
    polarized = generate_objective_task(seed=4, scenario=PreferenceScenario.POLARIZED)
    fragmented = generate_objective_task(seed=4, scenario=PreferenceScenario.FRAGMENTED)
    intense = generate_objective_task(seed=4, scenario=PreferenceScenario.INTENSE_MINORITY)

    assert len(polarized.principals) == 7
    assert sorted(Counter(p.group for p in polarized.principals).values()) == [3, 4]
    assert sorted(Counter(p.group for p in fragmented.principals).values()) == [2, 2, 3]
    assert Counter(p.group for p in intense.principals) == {
        "majority": 5,
        "intense_minority": 2,
    }


def test_coalition_discipline_binds_members_to_coalition_platforms():
    task = generate_objective_task(seed=7, scenario=PreferenceScenario.FRAGMENTED)
    outcome = coalition_discipline(task)
    assert outcome.institution == COALITION_DISCIPLINE
    by_coalition = {}
    for action in outcome.final_actions:
        coalition = task.coalition_by_agent[action.agent_id]
        by_coalition.setdefault(coalition, set()).add(action.alternative_id)
    assert all(len(choices) == 1 for choices in by_coalition.values())


def test_deliberation_tolerance_controls_compromise():
    task = generate_objective_task(seed=8, scenario=PreferenceScenario.POLARIZED)
    strict = open_deliberation(task, compromise_tolerance=0.0)
    permissive = open_deliberation(task, compromise_tolerance=2.0)
    assert strict.institution == OPEN_DELIBERATION
    assert strict.metadata["changed_actions"] == 0
    assert permissive.metadata["changed_actions"] > 0


def test_pareto_dominance_is_measured_from_available_alternatives():
    task = generate_objective_task(seed=9, scenario=PreferenceScenario.ALIGNED)
    outcome = delegated_leader(task)
    metrics = evaluate_outcome(task, outcome)
    assert isinstance(metrics["pareto_dominated"], bool)


def test_factorial_runner_is_deterministic_and_matched():
    first = run_objective_fidelity(n_tasks_per_scenario=3, base_seed=10)
    second = run_objective_fidelity(n_tasks_per_scenario=3, base_seed=10)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 4 * 3 * 4
    assert set(first["institution"]) == {
        PRIVATE_BALLOT,
        OPEN_DELIBERATION,
        DELEGATED_LEADER,
        COALITION_DISCIPLINE,
    }
    assert first[first["institution"] == PRIVATE_BALLOT][
        "outcome_loss_delta_vs_private"
    ].eq(0).all()


def test_summary_contains_agent_and_collective_metrics():
    results = run_objective_fidelity(n_tasks_per_scenario=2)
    summary = summarize_objective_fidelity(results)
    assert len(summary) == 4 * 4
    assert {
        "institutional_drift_mean",
        "preference_retention_rate",
        "outcome_loss_mean",
        "outcome_loss_worst_group",
        "outcome_loss_delta_vs_private",
    }.issubset(summary.columns)


def test_local_representative_parses_strict_structured_choice():
    backend = FakeBackend('{"choice":"left","rationale":"closest option"}')
    task = generate_objective_task(seed=2, scenario=PreferenceScenario.POLARIZED)
    representative = LocalModelRepresentative(0, task.principals[0], backend)
    action = representative.choose_initial_action(task.alternatives)
    assert action.alternative_id == "left"
    assert action.principal_id == task.principals[0].principal_id


def test_representative_prompt_exposes_precomputed_loss_and_arbitrary_order():
    task = generate_objective_task(seed=2, scenario=PreferenceScenario.POLARIZED)
    prompt = _initial_choice_prompt(task.principals[0], tuple(reversed(task.alternatives)))
    assert "loss_to_principal" in prompt
    assert "priority weight" in prompt
    assert "weighted_loss_to_principal" in prompt
    assert "precomputed Euclidean distance" in prompt
    assert "arbitrary order" in prompt


def test_choice_parser_rejects_invalid_json_and_unknown_options():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_choice("not-json", {"left"})
    with pytest.raises(ValueError, match="unavailable alternative"):
        parse_choice(json.dumps({"choice": "missing"}), {"left"})


def test_matched_llm_protocols_use_second_binding_vote_in_both_conditions():
    backend = FakeBackend('{"choice":"center","rationale":"minimum loss"}')
    oracle_task = generate_objective_task(
        seed=2, scenario=PreferenceScenario.ALIGNED, num_agents=4
    )
    model_task, baseline_logs = generate_model_baseline(
        oracle_task, backend, seed=2
    )
    private, private_logs = run_model_private_ballot(model_task, backend, seed=2)
    public_votes, public_logs = run_model_public_vote_exposure(
        model_task, backend, seed=2
    )
    open_outcome, open_logs = run_model_open_deliberation(
        model_task, backend, seed=2
    )

    assert backend.calls == 4 * 4
    assert len(baseline_logs) == len(private_logs) == len(public_logs) == len(open_logs) == 4
    assert private.metadata["reconsideration_call"] is True
    assert public_votes.metadata["reconsideration_call"] is True
    assert open_outcome.metadata["reconsideration_call"] is True
    assert private.metadata["peer_messages"] == 0
    assert public_votes.metadata["peer_messages"] == 4 * 3
    assert open_outcome.metadata["peer_messages"] == 4 * 3
    assert public_votes.metadata["peer_arguments"] is False
    assert open_outcome.metadata["peer_arguments"] is True
    assert all(
        log["changed_choice"] is False
        for log in private_logs + public_logs + open_logs
    )
    assert "No peer votes" in backend.messages[4][1]["content"]
    assert "public votes" in backend.messages[8][1]["content"]
    assert "statement" not in backend.messages[8][1]["content"]
    assert "public statements" in backend.messages[12][1]["content"]


def test_argument_probe_counterbalances_minority_order_and_intensity_content():
    task = generate_objective_task(
        seed=5, scenario=PreferenceScenario.INTENSE_MINORITY, num_agents=7
    )
    first_action = task.initial_actions[0]
    hidden = _standardized_argument(task, first_action, intensity_visible=False)
    shown = _standardized_argument(task, first_action, intensity_visible=True)
    assert "priority weight" not in hidden
    assert "weighted loss" in shown

    backend = FakeBackend('{"choice":"center"}')
    _, first_logs = run_model_argument_mechanism(
        task,
        backend,
        seed=5,
        intensity_visible=False,
        minority_last=False,
    )
    _, last_logs = run_model_argument_mechanism(
        task,
        backend,
        seed=5,
        intensity_visible=False,
        minority_last=True,
    )
    groups = {p.principal_id: p.group for p in task.principals}
    for logs, minority_last in ((first_logs, False), (last_logs, True)):
        for log in logs:
            peer_groups = [groups[peer_id] for peer_id in json.loads(log["peer_order"])]
            transition = "|".join(peer_groups)
            if minority_last:
                assert "intense_minority|majority" not in transition
            else:
                assert "majority|intense_minority" not in transition


def test_pilot_summaries_preserve_matched_treatment_contrast():
    outcomes = pd.DataFrame(
        [
            {
                "task_id": "t1",
                "scenario": "polarized",
                "seed": 1,
                "institution": "private_ballot",
                "institutional_drift_mean": 0.0,
                "preference_retention_rate": 1.0,
                "outcome_loss_mean": 0.5,
                "outcome_loss_worst_group": 1.0,
            },
            {
                "task_id": "t1",
                "scenario": "polarized",
                "seed": 1,
                "institution": PUBLIC_VOTE_EXPOSURE,
                "institutional_drift_mean": 0.1,
                "preference_retention_rate": 0.9,
                "outcome_loss_mean": 0.6,
                "outcome_loss_worst_group": 1.05,
            },
            {
                "task_id": "t1",
                "scenario": "polarized",
                "seed": 1,
                "institution": "open_deliberation",
                "institutional_drift_mean": 0.2,
                "preference_retention_rate": 0.8,
                "outcome_loss_mean": 0.7,
                "outcome_loss_worst_group": 1.1,
            },
        ]
    )
    effects = paired_treatment_effects(outcomes)
    assert effects.loc[0, "institutional_drift_mean_open_minus_private"] == 0.2
    assert effects.loc[0, "outcome_loss_mean_open_minus_private"] == pytest.approx(0.2)
    assert effects.loc[
        0, "institutional_drift_mean_public_votes_minus_private"
    ] == pytest.approx(0.1)
    assert effects.loc[
        0, "institutional_drift_mean_arguments_minus_votes"
    ] == pytest.approx(0.1)

    actions = pd.DataFrame(
        {
            "stage": ["binding_vote", "binding_vote"],
            "scenario": ["polarized", "polarized"],
            "institution": ["open_deliberation", "open_deliberation"],
            "principal_group": ["left", "right"],
            "agent_id": [0, 1],
            "changed_choice": [False, True],
            "individual_drift": [0.0, 1.0],
        }
    )
    summary = summarize_action_effects(actions)
    assert summary["positive_fidelity_loss_rate"].sum() == 1.0


def test_completion_cache_avoids_duplicate_local_calls(tmp_path):
    backend = FakeBackend('{"choice":"center"}')
    cached = CachedChatBackend(backend=backend, cache_dir=tmp_path)
    messages = [{"role": "user", "content": "choose"}]
    assert cached.generate(messages) == '{"choice":"center"}'
    assert cached.generate(messages) == '{"choice":"center"}'
    assert backend.calls == 1
    artifacts = list(tmp_path.glob("*.json"))
    assert len(artifacts) == 1
    record = json.loads(artifacts[0].read_text())
    assert record["request"]["model"] == "fake-local-model"


def test_local_baseline_runner_measures_representative_choice_accuracy():
    # All generated aligned principals choose center, so the fake local model
    # is a perfect representative in that controlled scenario.
    backend = FakeBackend('{"choice":"center","rationale":"nearest"}')
    results = run_local_baseline_fidelity(
        backend, n_tasks_per_scenario=1, num_agents=4
    )
    assert len(results) == 4 * 1 * 4
    assert "presented_order" in results.columns
    aligned = results[results["scenario"] == PreferenceScenario.ALIGNED.value]
    assert aligned["exact_choice_match"].all()
    assert aligned["excess_representation_loss"].eq(0).all()

    summary = summarize_local_baseline(results)
    assert set(summary.columns) >= {
        "valid_response_rate",
        "exact_choice_accuracy",
        "valid_choice_accuracy",
        "mean_excess_representation_loss",
    }


def test_local_baseline_records_invalid_responses_and_fails_gate():
    results = run_local_baseline_fidelity(
        FakeBackend("not-json"), n_tasks_per_scenario=1, num_agents=4
    )
    assert not results["response_valid"].any()
    assert not results["exact_choice_match"].any()
    gate = assess_baseline_gate(results)
    assert gate["passed"] is False
    assert gate["invalid_response_rate"] == 1.0


def test_local_baseline_gate_detects_option_position_bias():
    results = pd.DataFrame(
        {
            "oracle_presented_position": [1, 1, 2, 2, 3, 3],
            "exact_choice_match": [True, True, True, True, False, False],
            "response_valid": [True] * 6,
        }
    )
    gate = assess_baseline_gate(results)
    assert gate["passed"] is False
    assert gate["position_accuracy_gap"] == 1.0
