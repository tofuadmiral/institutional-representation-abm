from __future__ import annotations

import json
from collections import Counter

import pandas as pd
import pytest

from agent_exploration.authority import (
    authority_choice_prompt,
    oracle_authority_choice,
    parse_authority_choice,
)
from agent_exploration.local_models import CachedChatBackend
from agent_exploration.llm_protocols import (
    FREEFORM_COMPLETE_MANDATE,
    FREEFORM_INCOMPLETE_MANDATE,
    MODEL_DELEGATED_AUTHORITY,
    PUBLIC_VOTE_EXPOSURE,
    _standardized_argument,
    generate_model_baseline,
    run_model_argument_mechanism,
    run_model_coalition_authority,
    run_model_delegated_authority,
    run_model_freeform_mandate_bridge,
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
from agent_exploration.protected_mandates import (
    construct_protected_mandate,
    oracle_protected_choice,
    protected_authority_prompt,
)
from experiments.objective_fidelity import (
    run_objective_fidelity,
    summarize_objective_fidelity,
)
from experiments.authority_structure_pilot import (
    run_authority_structure_pilot,
    summarize_authority_pilot,
)
from experiments.authority_operation_pilot import (
    run_authority_operation_pilot,
    summarize_authority_operation,
)
from experiments.authority_oracle_landscape import (
    ORACLE_COALITION_AUTHORITY,
    ORACLE_DELEGATED_AUTHORITY,
    run_oracle_landscape,
    summarize_oracle_landscape,
)
from experiments.authority_safeguard_pilot import (
    EXPANDED_ALTERNATIVES,
    aggregate_panel_choices,
    expand_policy_set,
    paired_safeguard_effects,
    run_authority_safeguard_pilot,
    summarize_authority_safeguards,
)
from experiments.local_baseline_fidelity import (
    assess_baseline_gate,
    run_local_baseline_fidelity,
    summarize_local_baseline,
)
from experiments.protected_mandate_pilot import (
    run_protected_mandate_pilot,
    summarize_protected_mandates,
)
from experiments.reviewer_proposal_ablation import (
    compare_proposal_review,
    run_blind_redecision,
)
from experiments.reviewer_instruction_ablation import (
    compare_reviewer_instructions,
    run_neutral_proposal_decisions,
)
from experiments.reviewer_authority_gate import (
    apply_reviewer_authority_rules,
    paired_gate_effects,
    summarize_authority_rules,
)
from experiments.prospective_certificate_gate import (
    AGGREGATE_PRESSURE_VIOLATION,
    BROAD_OVERRIDE as CERTIFICATE_BROAD_OVERRIDE,
    CERTIFICATE_GATE,
    COMPLIANT_SUBOPTIMAL,
    CONFLICT_SCENARIOS,
    ORACLE_CORRECT,
    collect_conflict_tasks,
    collect_multi_eligible_conflict_tasks,
    paired_certificate_effects,
    parse_review_record,
)
from experiments.analyze_certificate_replications import (
    audit_schema_effects,
    multi_state_tradeoffs,
    prevalence_tradeoffs,
)
from experiments.analyze_paper_validations import (
    natural_review_transitions,
    natural_state_summary,
    wilson_interval,
)
from experiments.natural_proposer_validation import (
    PROTECTED_VIOLATION,
    classify_proposal,
    natural_proposer_prompt,
)
from experiments.portfolio_certificate_gate import (
    BUDGET_ONLY,
    COVERAGE_ONLY,
    DUAL_VIOLATION,
    compliant_suboptimal_plan,
    generate_portfolio_task,
    parse_portfolio_review,
    portfolio_oracle,
    unconstrained_portfolio_oracle,
)
from experiments.llm_institutional_pilot import (
    paired_treatment_effects,
    summarize_action_effects,
)
from experiments.action_aware_reviewer_validation import (
    ACTION_AWARE_BROAD,
    EVIDENCE_GATE,
    RETAIN,
    action_aware_review_prompt,
    parse_action_aware_review,
    paired_effects as action_aware_paired_effects,
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


def test_action_aware_review_parser_is_strict_but_normalizes_one_fence():
    raw = (
        '{"disposition":"retain","proposal_policy_id":"p_000",'
        '"proposal_protected_loss":0.25,"max_weighted_loss":0.5,'
        '"proposal_violates_duty_1":false,"recommended_policy_id":"p_000",'
        '"recommended_protected_loss":0.25}'
    )
    strict = parse_action_aware_review(raw, {"p_000"})
    fenced = parse_action_aware_review(f"```json\n{raw}\n```", {"p_000"})

    assert strict.disposition == RETAIN
    assert strict.format_normalized is False
    assert fenced.format_normalized is True
    with pytest.raises(ValueError, match="disposition"):
        parse_action_aware_review(raw.replace(RETAIN, "revise"), {"p_000"})
    with pytest.raises(ValueError, match="missing or unexpected"):
        parse_action_aware_review(raw[:-1] + ',"rationale":"extra"}', {"p_000"})


def test_action_aware_prompt_freezes_three_dispositions_and_original_tables():
    retained = collect_multi_eligible_conflict_tasks(
        tasks_per_scenario=1,
        base_seed=95_000,
    )
    _, _, task, principal_ids, mandate, _ = retained[0]
    proposal = oracle_protected_choice(task, principal_ids, mandate)
    prompt = action_aware_review_prompt(
        task,
        principal_ids,
        mandate,
        proposal,
        list(task.alternatives),
    )

    assert "retain when the proposal already satisfies both ordered duties" in prompt
    assert "replace only when a named alternative is better" in prompt
    assert "escalate when you cannot verify the comparison" in prompt
    assert "protected-loss table" in prompt
    assert "aggregate-loss table" in prompt


def test_action_aware_effects_compare_fixed_response_recombinations():
    rows = []
    for task_id in ("task-1", "task-2"):
        for institution, exact, compliant in (
            (ACTION_AWARE_BROAD, False, False),
            (EVIDENCE_GATE, True, True),
        ):
            rows.append(
                {
                    "task_id": task_id,
                    "proposal_state": ORACLE_CORRECT,
                    "institution": institution,
                    "protected_oracle_match": exact,
                    "constraint_followed": compliant,
                }
            )
    effects = action_aware_paired_effects(pd.DataFrame(rows))

    assert len(effects) == 2
    assert effects["effect"].eq(1.0).all()


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
    intense = generate_objective_task(
        seed=4, scenario=PreferenceScenario.INTENSE_MINORITY
    )

    assert len(polarized.principals) == 7
    assert sorted(Counter(p.group for p in polarized.principals).values()) == [3, 4]
    assert sorted(Counter(p.group for p in fragmented.principals).values()) == [2, 2, 3]
    assert Counter(p.group for p in intense.principals) == {
        "majority": 5,
        "intense_minority": 2,
    }
    assert sorted(Counter(fragmented.coalition_by_agent.values()).values()) == [
        2,
        2,
        3,
    ]


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
    assert (
        first[first["institution"] == PRIVATE_BALLOT]["outcome_loss_delta_vs_private"]
        .eq(0)
        .all()
    )


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
    prompt = _initial_choice_prompt(
        task.principals[0], tuple(reversed(task.alternatives))
    )
    assert "loss_to_principal" in prompt
    assert "priority weight" in prompt
    assert "weighted_loss_to_principal" in prompt
    assert "precomputed Euclidean distance" in prompt
    assert "arbitrary order" in prompt

    choice_only = _initial_choice_prompt(
        task.principals[0],
        task.alternatives,
        include_rationale=False,
    )
    assert "Do not include a rationale" in choice_only


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
    model_task, baseline_logs = generate_model_baseline(oracle_task, backend, seed=2)
    private, private_logs = run_model_private_ballot(model_task, backend, seed=2)
    public_votes, public_logs = run_model_public_vote_exposure(
        model_task, backend, seed=2
    )
    open_outcome, open_logs = run_model_open_deliberation(model_task, backend, seed=2)

    assert backend.calls == 4 * 4
    assert (
        len(baseline_logs)
        == len(private_logs)
        == len(public_logs)
        == len(open_logs)
        == 4
    )
    assert private.metadata["reconsideration_call"] is True
    assert public_votes.metadata["reconsideration_call"] is True
    assert open_outcome.metadata["reconsideration_call"] is True
    assert private.metadata["peer_messages"] == 0
    assert public_votes.metadata["peer_messages"] == 4 * 3
    assert open_outcome.metadata["peer_messages"] == 4 * 3
    assert public_votes.metadata["peer_arguments"] is False
    assert open_outcome.metadata["peer_arguments"] is True
    assert all(
        log["changed_choice"] is False for log in private_logs + public_logs + open_logs
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


def test_freeform_bridge_changes_only_the_recipients_mandate_information():
    task = generate_objective_task(
        seed=5, scenario=PreferenceScenario.INTENSE_MINORITY, num_agents=7
    )
    backend = FakeBackend('{"choice":"center"}')
    incomplete, incomplete_logs = run_model_freeform_mandate_bridge(
        task, backend, seed=5, mandate_complete=False
    )
    complete, complete_logs = run_model_freeform_mandate_bridge(
        task, backend, seed=5, mandate_complete=True
    )

    assert incomplete.institution == FREEFORM_INCOMPLETE_MANDATE
    assert complete.institution == FREEFORM_COMPLETE_MANDATE
    assert [log["peer_order"] for log in incomplete_logs] == [
        log["peer_order"] for log in complete_logs
    ]
    assert [log["peer_statement_records"] for log in incomplete_logs] == [
        log["peer_statement_records"] for log in complete_logs
    ]
    for incomplete_call, complete_call in zip(
        backend.messages[:7], backend.messages[7:]
    ):
        incomplete_prompt = incomplete_call[1]["content"]
        complete_prompt = complete_call[1]["content"]
        assert "priority weight" not in incomplete_prompt
        assert "weighted_loss_to_principal" not in incomplete_prompt
        assert "priority weight" in complete_prompt
        assert "weighted_loss_to_principal" in complete_prompt
        incomplete_peer_text = incomplete_prompt.split(
            "Before voting, you receive", maxsplit=1
        )[1].split("Now cast", maxsplit=1)[0]
        complete_peer_text = complete_prompt.split(
            "Before voting, you receive", maxsplit=1
        )[1].split("Now cast", maxsplit=1)[0]
        assert incomplete_peer_text == complete_peer_text


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


def test_authority_pilot_reuses_one_frozen_set_of_model_choices():
    task = generate_objective_task(seed=7, scenario=PreferenceScenario.FRAGMENTED)
    baseline = pd.DataFrame(
        [
            {
                "task_id": task.task_id,
                "scenario": PreferenceScenario.FRAGMENTED.value,
                "seed": 7,
                "agent_id": action.agent_id,
                "principal_id": action.principal_id,
                "model": "frozen-model",
                "model_choice": action.alternative_id,
                "response_valid": True,
                "rationale": action.rationale,
            }
            for action in task.initial_actions
        ]
    )
    outcomes, actions = run_authority_structure_pilot(baseline)
    outcome_summary, action_summary = summarize_authority_pilot(outcomes, actions)

    assert len(outcomes) == 3
    assert len(actions) == 3 * 7
    assert set(outcomes["institution"]) == {
        PRIVATE_BALLOT,
        DELEGATED_LEADER,
        COALITION_DISCIPLINE,
    }
    assert outcomes["behavioral_reconsideration"].eq(False).all()
    assert actions["behavioral_reconsideration"].eq(False).all()
    private = outcomes[outcomes["institution"] == PRIVATE_BALLOT].iloc[0]
    delegated = outcomes[outcomes["institution"] == DELEGATED_LEADER].iloc[0]
    assert private["effective_decision_makers"] == 7
    assert delegated["effective_decision_makers"] == 1
    assert not outcome_summary.empty
    assert not action_summary.empty


def test_model_authorities_execute_anonymous_weighted_loss_mandates():
    task = generate_objective_task(
        seed=2, scenario=PreferenceScenario.ALIGNED, num_agents=7
    )
    prompt = authority_choice_prompt(
        task,
        [principal.principal_id for principal in task.principals],
        task.alternatives,
    )
    assert "lowest total weighted loss" in prompt
    assert "priority_weight" in prompt
    assert "controlling decision table" in prompt
    assert "exact precomputed total weighted losses" in prompt
    assert "weighted_losses" not in prompt
    assert "ideal_point" in prompt
    assert "principal_group" not in prompt
    assert "aligned" not in prompt
    assert (
        oracle_authority_choice(
            task, [principal.principal_id for principal in task.principals]
        )
        == "center"
    )

    backend = FakeBackend('{"choice":"center"}')
    delegated, delegated_logs = run_model_delegated_authority(task, backend, seed=2)
    coalition, coalition_logs = run_model_coalition_authority(task, backend, seed=2)

    assert delegated.collective_choice_id == "center"
    assert delegated.metadata["authority_node_accuracy"] == 1.0
    assert coalition.collective_choice_id == "center"
    assert coalition.metadata["authority_node_accuracy"] == 1.0
    assert len(delegated_logs) == 1
    assert len(coalition_logs) == 3
    assert backend.calls == 4


def test_authority_decision_table_preserves_randomized_policy_order():
    task = generate_objective_task(
        seed=2, scenario=PreferenceScenario.ALIGNED, num_agents=7
    )
    alternatives = tuple(reversed(task.alternatives))
    prompt = authority_choice_prompt(
        task,
        [principal.principal_id for principal in task.principals],
        alternatives,
    )
    table_text = prompt.split("controlling decision table is ", maxsplit=1)[1]
    table = json.loads(table_text.split(". These are exact", maxsplit=1)[0])
    assert [row["policy_id"] for row in table] == [
        alternative.alternative_id for alternative in alternatives
    ]


def test_authority_parser_records_narrow_markdown_fence_normalization():
    assert parse_authority_choice('{"choice":"left"}', {"left"}) == (
        "left",
        "",
        False,
    )
    assert parse_authority_choice('```json\n{"choice":"left"}\n```', {"left"}) == (
        "left",
        "",
        True,
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_authority_choice('Answer: {"choice":"left"}', {"left"})


def test_authority_operation_runner_decomposes_structure_and_model_error():
    task = generate_objective_task(
        seed=2, scenario=PreferenceScenario.ALIGNED, num_agents=7
    )
    baseline = pd.DataFrame(
        [
            {
                "task_id": task.task_id,
                "scenario": PreferenceScenario.ALIGNED.value,
                "seed": 2,
                "agent_id": action.agent_id,
                "principal_id": action.principal_id,
                "model": "frozen-model",
                "model_choice": action.alternative_id,
                "response_valid": True,
                "exact_choice_match": True,
                "rationale": action.rationale,
            }
            for action in task.initial_actions
        ]
    )
    backend = FakeBackend('{"choice":"center"}')
    outcomes, decisions, errors = run_authority_operation_pilot(
        baseline, backend, tasks_per_scenario=1
    )
    summary = summarize_authority_operation(outcomes)

    assert len(outcomes) == 3
    assert len(decisions) == 4
    assert errors.empty
    assert outcomes["collective_choice_oracle_match"].all()
    assert outcomes["model_execution_loss"].eq(0).all()
    assert not summary.empty


def test_authority_operation_keeps_inexact_private_baselines():
    task = generate_objective_task(
        seed=2, scenario=PreferenceScenario.ALIGNED, num_agents=7
    )
    baseline = pd.DataFrame(
        [
            {
                "task_id": task.task_id,
                "scenario": PreferenceScenario.ALIGNED.value,
                "seed": 2,
                "agent_id": action.agent_id,
                "principal_id": action.principal_id,
                "model": "imperfect-model",
                "model_choice": "left",
                "response_valid": True,
                "exact_choice_match": False,
                "rationale": "",
            }
            for action in task.initial_actions
        ]
    )

    outcomes, decisions, errors = run_authority_operation_pilot(
        baseline,
        FakeBackend('{"choice":"center"}'),
        tasks_per_scenario=1,
    )

    assert errors.empty
    assert len(decisions) == 4
    private = outcomes[outcomes["institution"] == PRIVATE_BALLOT].iloc[0]
    delegated = outcomes[outcomes["institution"] == MODEL_DELEGATED_AUTHORITY].iloc[0]
    assert private["authority_node_accuracy"] == 0.0
    assert private["model_execution_loss"] > 0
    assert delegated["structural_loss_delta_vs_private"] == pytest.approx(0.0)
    assert delegated["model_execution_loss"] == pytest.approx(0.0)


def test_oracle_landscape_maps_exact_structural_effects():
    results = run_oracle_landscape(n_profiles_per_scenario=2, base_seed=50_000)
    summary = summarize_oracle_landscape(results)

    assert len(results) == 4 * 2 * 3
    assert len(summary) == 4 * 3
    assert set(results["institution"]) == {
        PRIVATE_BALLOT,
        ORACLE_DELEGATED_AUTHORITY,
        ORACLE_COALITION_AUTHORITY,
    }
    private = results[results["institution"] == PRIVATE_BALLOT]
    delegated = results[results["institution"] == ORACLE_DELEGATED_AUTHORITY]
    assert private["structural_loss_delta_vs_private"].eq(0).all()
    assert (delegated["structural_loss_delta_vs_private"] <= 1e-12).all()


def test_protected_mandate_creates_explicit_aggregate_conflict():
    task = generate_objective_task(
        seed=2, scenario=PreferenceScenario.POLARIZED, num_agents=7
    )
    principal_ids = tuple(range(7))
    mandate = construct_protected_mandate(
        task,
        principal_ids,
        conflict=True,
        seed=1,
    )

    assert mandate is not None
    unconstrained = oracle_authority_choice(task, principal_ids)
    protected = oracle_protected_choice(task, principal_ids, mandate)
    assert protected != unconstrained
    assert mandate.allowed_policy_ids == (protected,)
    prompt = protected_authority_prompt(
        task,
        principal_ids,
        mandate,
        tuple(reversed(task.alternatives)),
    )
    assert "strict priority order" in prompt
    assert "non-negotiable duty overrides a lower aggregate loss" in prompt
    table = json.loads(
        prompt.split("controlling decision table is ", maxsplit=1)[1].split(
            ". The policies", maxsplit=1
        )[0]
    )
    assert [row["policy_id"] for row in table] == ["right", "center", "left"]


def test_protected_mandate_pilot_records_compatible_and_conflict_cases():
    results = run_protected_mandate_pilot(
        FakeBackend('{"choice":"left"}'),
        n_profiles_per_scenario=1,
        base_seed=60_000,
    )
    summary = summarize_protected_mandates(results)

    assert not results.empty
    assert set(results["authority_type"]) == {"delegated", "coalition"}
    assert set(results["conflict"]) == {False, True}
    assert results["response_valid"].all()
    assert not summary.empty


def test_derived_protected_prompt_hides_answer_list():
    task = expand_policy_set(
        generate_objective_task(
            seed=70_008,
            scenario=PreferenceScenario.FRAGMENTED,
            num_agents=7,
        )
    )
    principal_ids = tuple(range(7))
    mandate = construct_protected_mandate(
        task,
        principal_ids,
        conflict=True,
        seed=1,
    )
    assert mandate is not None
    from agent_exploration.protected_mandates import (
        derived_protected_authority_prompt,
    )

    prompt = derived_protected_authority_prompt(
        task,
        principal_ids,
        mandate,
        tuple(reversed(task.alternatives)),
    )
    assert len(task.alternatives) == len(EXPANDED_ALTERNATIVES) == 7
    assert "protected_principal_weighted_loss" in prompt
    assert "max_weighted_loss" in prompt
    assert "allowed_policy_ids" not in prompt
    assert str(list(mandate.allowed_policy_ids)) not in prompt


def test_neutral_proposal_prompt_removes_only_anti_deference_instruction():
    task = expand_policy_set(
        generate_objective_task(
            seed=70_008,
            scenario=PreferenceScenario.FRAGMENTED,
            num_agents=7,
        )
    )
    principal_ids = tuple(range(7))
    mandate = construct_protected_mandate(task, principal_ids, conflict=True, seed=1)
    assert mandate is not None
    from agent_exploration.protected_mandates import derived_protected_authority_prompt

    neutral = derived_protected_authority_prompt(
        task,
        principal_ids,
        mandate,
        task.alternatives,
        proposed_choice="p_000",
        proposal_instruction="neutral",
    )
    anti = derived_protected_authority_prompt(
        task,
        principal_ids,
        mandate,
        task.alternatives,
        proposed_choice="p_000",
    )
    assert "A first authority proposed policy 'p_000'." in neutral
    assert "do not defer" not in neutral
    assert "do not defer" in anti


def test_panel_uses_status_quo_for_three_way_tie():
    task = expand_policy_set(
        generate_objective_task(seed=1, scenario=PreferenceScenario.ALIGNED)
    )
    assert (
        aggregate_panel_choices(
            task,
            ["p_neg_050", "p_000", "p_pos_050"],
        )
        == "p_000"
    )
    assert (
        aggregate_panel_choices(
            task,
            ["p_neg_050", "p_neg_050", "p_pos_050"],
        )
        == "p_neg_050"
    )


def test_authority_safeguard_pilot_records_three_matched_institutions():
    outcomes, decisions = run_authority_safeguard_pilot(
        FakeBackend('{"choice":"p_000"}'),
        n_profiles_per_scenario=1,
        base_seed=70_000,
    )
    summary = summarize_authority_safeguards(outcomes)

    assert set(outcomes["institution"]) == {
        "single_authority",
        "independent_panel",
        "override_review",
    }
    assert set(decisions["role"]) == {"single", "panel_member", "reviewer"}
    assert outcomes.groupby(["task_id", "conflict"]).size().eq(3).all()
    assert not summary.empty

    outcomes["model"] = "fake-local-model"
    paired = paired_safeguard_effects(
        outcomes,
        bootstrap_repetitions=20,
        bootstrap_seed=1,
    )
    assert set(paired["comparison"]) == {
        "independent_panel",
        "override_review",
    }
    assert set(paired["metric"]) == {
        "protected_oracle_match",
        "constraint_followed",
    }
    assert paired["n_profiles"].gt(0).all()


def test_authority_safeguard_parallel_runner_preserves_matched_rows():
    outcomes, decisions = run_authority_safeguard_pilot(
        FakeBackend('{"choice":"p_000"}'),
        n_profiles_per_scenario=1,
        base_seed=70_100,
        workers=2,
    )
    assert outcomes.groupby(["task_id", "conflict"]).size().eq(3).all()
    assert decisions.groupby(["task_id", "conflict"]).size().eq(5).all()


def test_blind_redecision_matches_reviewer_order_and_supports_paired_analysis():
    backend = FakeBackend('{"choice":"p_000"}')
    outcomes, decisions = run_authority_safeguard_pilot(
        backend,
        n_profiles_per_scenario=1,
        base_seed=70_200,
    )
    blind = run_blind_redecision(
        backend,
        n_profiles_per_scenario=1,
        base_seed=70_200,
    )
    comparison = compare_proposal_review(
        blind,
        decisions,
        bootstrap_repetitions=20,
        bootstrap_seed=1,
    )

    assert len(blind) == outcomes.groupby(["task_id", "conflict"]).ngroups
    assert len(comparison) == 6
    assert comparison["n_profiles"].gt(0).all()


def test_neutral_proposal_arm_matches_other_reviewer_arms():
    backend = FakeBackend('{"choice":"p_000"}')
    outcomes, decisions = run_authority_safeguard_pilot(
        backend,
        n_profiles_per_scenario=1,
        base_seed=70_300,
    )
    blind = run_blind_redecision(
        backend,
        n_profiles_per_scenario=1,
        base_seed=70_300,
    )
    neutral = run_neutral_proposal_decisions(
        backend,
        decisions,
        n_profiles_per_scenario=1,
        base_seed=70_300,
    )
    comparison = compare_reviewer_instructions(
        blind,
        neutral,
        decisions,
        bootstrap_repetitions=20,
        bootstrap_seed=1,
    )

    assert len(neutral) == outcomes.groupby(["task_id", "conflict"]).ngroups
    assert len(comparison) == 18
    assert set(comparison["contrast"]) == {
        "neutral_minus_blind",
        "anti_minus_neutral",
        "anti_minus_blind",
    }


def test_violation_only_authority_gate_blocks_unnecessary_override():
    decisions = pd.DataFrame(
        [
            {
                "task_id": "task-1",
                "scenario": "aligned",
                "conflict": False,
                "role": "single",
                "model_choice": "correct",
                "protected_oracle_choice": "correct",
                "response_valid": True,
                "constraint_followed": True,
            },
            {
                "task_id": "task-1",
                "scenario": "aligned",
                "conflict": False,
                "role": "reviewer",
                "model_choice": "wrong",
                "protected_oracle_choice": "correct",
                "response_valid": True,
                "constraint_followed": False,
            },
            {
                "task_id": "task-2",
                "scenario": "fragmented",
                "conflict": True,
                "role": "single",
                "model_choice": "wrong",
                "protected_oracle_choice": "correct",
                "response_valid": True,
                "constraint_followed": False,
            },
            {
                "task_id": "task-2",
                "scenario": "fragmented",
                "conflict": True,
                "role": "reviewer",
                "model_choice": "correct",
                "protected_oracle_choice": "correct",
                "response_valid": True,
                "constraint_followed": True,
            },
        ]
    )
    outcomes = apply_reviewer_authority_rules(decisions)
    summary = summarize_authority_rules(outcomes)
    effects = paired_gate_effects(
        outcomes,
        bootstrap_repetitions=20,
        bootstrap_seed=1,
    )

    gated = outcomes[outcomes["authority_rule"] == "violation_only_override"]
    assert gated["protected_oracle_match"].all()
    assert gated["constraint_followed"].all()
    assert len(summary) == 3
    assert len(effects) == 4


def test_certificate_review_parser_is_strict_but_normalizes_one_fence():
    raw = (
        '{"proposal_policy_id":"p_000","proposal_protected_loss":0.25,'
        '"max_weighted_loss":0.5,"proposal_violates_duty_1":false,'
        '"recommended_policy_id":"p_000","recommended_protected_loss":0.25}'
    )
    strict = parse_review_record(raw, {"p_000"})
    fenced = parse_review_record(f"```json\n{raw}\n```", {"p_000"})

    assert strict.proposal_violates_duty_1 is False
    assert strict.format_normalized is False
    assert fenced.format_normalized is True
    with pytest.raises(ValueError, match="missing or unexpected"):
        parse_review_record(raw[:-1] + ',"rationale":"extra"}', {"p_000"})


def test_dual_objective_audit_requires_aggregate_evidence_field():
    raw = (
        '{"proposal_policy_id":"p_000","proposal_protected_loss":0.25,'
        '"max_weighted_loss":0.5,"proposal_violates_duty_1":false,'
        '"recommended_policy_id":"p_000","recommended_protected_loss":0.25,'
        '"recommended_total_weighted_loss":2.75}'
    )
    record = parse_review_record(raw, {"p_000"}, audit_schema="dual_objective")

    assert record.recommended_total_weighted_loss == pytest.approx(2.75)
    with pytest.raises(ValueError, match="missing or unexpected"):
        parse_review_record(
            raw.replace(',"recommended_total_weighted_loss":2.75', ""),
            {"p_000"},
            audit_schema="dual_objective",
        )


def test_frozen_certificate_sample_collects_balanced_conflict_tasks():
    retained = collect_conflict_tasks(tasks_per_scenario=2, base_seed=90_000)

    assert len(retained) == 6
    assert Counter(item[0] for item in retained) == {
        scenario: 2 for scenario in CONFLICT_SCENARIOS
    }
    for _, _, task, principal_ids, mandate, aggregate_choice in retained:
        assert aggregate_choice == oracle_authority_choice(task, principal_ids)
        assert aggregate_choice not in mandate.allowed_policy_ids


def test_multi_eligible_sample_separates_compliance_and_optimality():
    retained = collect_multi_eligible_conflict_tasks(
        tasks_per_scenario=2,
        base_seed=95_000,
    )

    assert len(retained) == 6
    for _, _, task, principal_ids, mandate, aggregate_choice in retained:
        assert len(mandate.allowed_policy_ids) >= 2
        assert aggregate_choice not in mandate.allowed_policy_ids
        oracle = oracle_protected_choice(task, principal_ids, mandate)
        assert any(policy_id != oracle for policy_id in mandate.allowed_policy_ids)


def test_certificate_gate_effects_pair_the_same_reviewer_output():
    rows = []
    for task_id in ("task-1", "task-2"):
        for proposal_state in (ORACLE_CORRECT, AGGREGATE_PRESSURE_VIOLATION):
            for institution, exact, compliant in (
                (CERTIFICATE_BROAD_OVERRIDE, False, False),
                (CERTIFICATE_GATE, True, True),
            ):
                rows.append(
                    {
                        "task_id": task_id,
                        "proposal_state": proposal_state,
                        "institution": institution,
                        "protected_oracle_match": exact,
                        "constraint_followed": compliant,
                    }
                )
    effects = paired_certificate_effects(
        pd.DataFrame(rows),
        bootstrap_repetitions=20,
        bootstrap_seed=1,
    )

    assert len(effects) == 6
    assert effects["effect"].eq(1.0).all()


def test_prevalence_tradeoff_recovers_break_even_failure_rate():
    rows = []
    for task_index in range(4):
        for proposal_state in (ORACLE_CORRECT, AGGREGATE_PRESSURE_VIOLATION):
            broad = not (proposal_state == ORACLE_CORRECT and task_index == 0)
            gate = not (
                proposal_state == AGGREGATE_PRESSURE_VIOLATION and task_index == 0
            )
            for institution, compliant in (
                (CERTIFICATE_BROAD_OVERRIDE, broad),
                (CERTIFICATE_GATE, gate),
            ):
                rows.append(
                    {
                        "model": "fake-model",
                        "task_id": f"task-{task_index}",
                        "scenario": "fragmented",
                        "proposal_state": proposal_state,
                        "institution": institution,
                        "constraint_followed": compliant,
                    }
                )
    summary, curve = prevalence_tradeoffs(
        pd.DataFrame(rows),
        bootstrap_repetitions=20,
        bootstrap_seed=1,
    )

    model = summary[summary["scope"] == "fake-model"].iloc[0]
    assert model["correct_proposal_effect"] == pytest.approx(0.25)
    assert model["violation_proposal_effect"] == pytest.approx(-0.25)
    assert model["break_even_violation_prevalence"] == pytest.approx(0.5)
    assert len(curve) == 202


def test_multi_state_tradeoff_keeps_artificial_mixture_explicit():
    rows = []
    effects = {
        ORACLE_CORRECT: (False, True),
        AGGREGATE_PRESSURE_VIOLATION: (True, True),
        COMPLIANT_SUBOPTIMAL: (True, False),
    }
    for state, (broad, gate) in effects.items():
        for institution, exact in (
            (CERTIFICATE_BROAD_OVERRIDE, broad),
            (CERTIFICATE_GATE, gate),
        ):
            rows.append(
                {
                    "model": "fake-model",
                    "task_id": "task-1",
                    "scenario": "fragmented",
                    "proposal_state": state,
                    "institution": institution,
                    "protected_oracle_match": exact,
                }
            )
    summary, grid = multi_state_tradeoffs(pd.DataFrame(rows))

    model = summary[summary["scope"] == "fake-model"].iloc[0]
    assert model[f"{ORACLE_CORRECT}_effect"] == pytest.approx(1.0)
    assert model[f"{AGGREGATE_PRESSURE_VIOLATION}_effect"] == pytest.approx(0.0)
    assert model[f"{COMPLIANT_SUBOPTIMAL}_effect"] == pytest.approx(-1.0)
    assert len(grid[grid["scope"] == "fake-model"]) == 5151


def test_audit_schema_effects_pairs_identical_cases():
    protected = pd.DataFrame(
        [
            {
                "model": "fake-model",
                "task_id": "task-1",
                "scenario": "fragmented",
                "proposal_state": ORACLE_CORRECT,
                "institution": institution,
                "protected_oracle_match": False,
                "constraint_followed": True,
            }
            for institution in (CERTIFICATE_BROAD_OVERRIDE, CERTIFICATE_GATE)
        ]
    )
    dual = protected.copy()
    dual["protected_oracle_match"] = True
    effects = audit_schema_effects(protected, dual)

    exact = effects[
        (effects["proposal_state"] == "all")
        & (effects["metric"] == "protected_oracle_match")
    ]
    assert exact["dual_minus_protected"].eq(1.0).all()


def test_natural_proposal_classification_separates_error_types():
    assert classify_proposal("oracle", "oracle", {"oracle", "other"}) == ORACLE_CORRECT
    assert (
        classify_proposal("other", "oracle", {"oracle", "other"})
        == COMPLIANT_SUBOPTIMAL
    )
    assert (
        classify_proposal("forbidden", "oracle", {"oracle", "other"})
        == PROTECTED_VIOLATION
    )


def test_natural_proposer_prompt_does_not_supply_a_proposal():
    retained = collect_multi_eligible_conflict_tasks(
        tasks_per_scenario=1,
        base_seed=95_000,
    )
    _, _, task, principal_ids, mandate, _ = retained[0]
    prompt = natural_proposer_prompt(
        task, principal_ids, mandate, list(task.alternatives)
    )

    assert "upstream authority" in prompt
    assert "proposed policy" not in prompt
    assert '{"choice":"<policy id>"}' in prompt


@pytest.mark.parametrize("stratum", [BUDGET_ONLY, COVERAGE_ONLY, DUAL_VIOLATION])
def test_portfolio_transfer_tasks_have_required_matched_states(stratum):
    task = generate_portfolio_task(seed=120_000, stratum=stratum)
    oracle = task.plan(portfolio_oracle(task))
    unconstrained = task.plan(unconstrained_portfolio_oracle(task))
    suboptimal = task.plan(compliant_suboptimal_plan(task))

    assert task.eligible(oracle)
    assert not task.eligible(unconstrained)
    assert task.eligible(suboptimal)
    assert suboptimal.total_public_benefit < oracle.total_public_benefit
    assert unconstrained.total_public_benefit > oracle.total_public_benefit
    if stratum == BUDGET_ONLY:
        assert unconstrained.cost > task.budget
        assert unconstrained.protected_coverage >= task.minimum_protected_coverage
    elif stratum == COVERAGE_ONLY:
        assert unconstrained.cost <= task.budget
        assert unconstrained.protected_coverage < task.minimum_protected_coverage
    else:
        assert unconstrained.cost > task.budget
        assert unconstrained.protected_coverage < task.minimum_protected_coverage


def test_portfolio_review_parser_is_strict_but_normalizes_one_fence():
    raw = (
        '{"proposal_plan_id":"plan_A","proposal_cost":100,"budget":110,'
        '"proposal_protected_coverage":40,"minimum_protected_coverage":35,'
        '"proposal_violates_duty_1":false,"recommended_plan_id":"plan_B",'
        '"recommended_cost":105,"recommended_protected_coverage":45}'
    )
    strict = parse_portfolio_review(raw, {"plan_A", "plan_B"})
    fenced = parse_portfolio_review(f"```json\n{raw}\n```", {"plan_A", "plan_B"})

    assert strict.recommended_plan_id == "plan_B"
    assert strict.format_normalized is False
    assert fenced.format_normalized is True
    with pytest.raises(ValueError, match="missing or unexpected"):
        parse_portfolio_review(raw[:-1] + ',"extra":1}', {"plan_A", "plan_B"})


def test_validation_analysis_reports_frequencies_and_review_transitions():
    proposers = pd.DataFrame(
        [
            {
                "model": "fake-model",
                "task_id": f"task-{index}",
                "scenario": "fragmented",
                "proposal_state": state,
            }
            for index, state in enumerate((ORACLE_CORRECT, COMPLIANT_SUBOPTIMAL))
        ]
    )
    frequencies = natural_state_summary(proposers)
    exact = frequencies[
        (frequencies["scope"] == "fake-model")
        & (frequencies["scenario"] == "all")
        & (frequencies["proposal_state"] == ORACLE_CORRECT)
    ].iloc[0]
    assert exact["rate"] == pytest.approx(0.5)
    low, high = wilson_interval(1, 2)
    assert 0 < low < 0.5 < high < 1

    rows = []
    for task_id, proposal_exact in (("task-0", True), ("task-1", False)):
        for institution, reviewed_exact in (
            ("no_review", proposal_exact),
            (CERTIFICATE_BROAD_OVERRIDE, False),
            (CERTIFICATE_GATE, proposal_exact),
        ):
            rows.append(
                {
                    "model": "fake-model",
                    "task_id": task_id,
                    "scenario": "fragmented",
                    "proposal_state": ORACLE_CORRECT,
                    "institution": institution,
                    "protected_oracle_match": reviewed_exact,
                    "constraint_followed": True,
                }
            )
    transitions = natural_review_transitions(pd.DataFrame(rows))
    broad_exact = transitions[
        (transitions["scope"] == "fake-model")
        & (transitions["institution"] == CERTIFICATE_BROAD_OVERRIDE)
        & (transitions["metric"] == "protected_oracle_match")
    ].iloc[0]
    assert broad_exact["successes_spoiled"] == 1


def test_local_baseline_runner_measures_representative_choice_accuracy():
    # All generated aligned principals choose center, so the fake local model
    # is a perfect representative in that controlled scenario.
    backend = FakeBackend('{"choice":"center","rationale":"nearest"}')
    results = run_local_baseline_fidelity(backend, n_tasks_per_scenario=1, num_agents=4)
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
        "format_normalization_rate",
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
