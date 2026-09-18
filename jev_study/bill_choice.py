"""Synthetic mandate translation: offline fixtures and scoring, not human prediction."""
from __future__ import annotations

import copy
import itertools
import math
import random

ISSUES = ("housing", "transport", "energy")
LEVELS = {
    "housing": ("keep current housing density limits", "allow higher housing density"),
    "transport": ("keep current road spending allocation", "shift road spending toward public transit"),
    "energy": ("keep current energy subsidy allocation", "shift subsidies toward renewable energy"),
}
ARMS = ("plain", "reverse_order", "relabel", "nonbinding_endorsement")


def preference_key(policy, desired, priority):
    return tuple(int(policy[i] == desired[i]) for i in priority)


def make_cases(seeds=range(91000, 91024)):
    """24 base profiles x four paired presentations; no model-derived labels."""
    cases = []
    for seed in seeds:
        rng = random.Random(seed)
        priority = list(range(3))
        rng.shuffle(priority)
        desired = tuple(rng.randrange(2) for _ in range(3))
        alternatives = list(itertools.product((0, 1), repeat=3))[1:]
        policies = rng.sample(alternatives, 3) + [(0, 0, 0)]
        keys = [preference_key(p, desired, priority) for p in policies]
        best = max(range(4), key=lambda i: keys[i])
        worst = min(range(4), key=lambda i: keys[i])
        mandate = [LEVELS[ISSUES[i]][desired[i]] for i in priority]
        for arm in ARMS:
            labels = ["bill_a", "bill_b", "bill_c", "status_quo"]
            if arm == "relabel":
                labels = ["bill_c", "bill_a", "bill_b", "status_quo"]
            criteria = {label: "; ".join(LEVELS[issue][p[i]] for i, issue in enumerate(ISSUES))
                        for label, p in zip(labels, policies)}
            if arm == "reverse_order":
                criteria = dict(reversed(list(criteria.items())))
            state = dict(setting="Synthetic bill-selection task, not a forecast of real voters.",
                constituent_priorities=mandate,
                decision_rule="Priorities are in strict order. Prefer an option satisfying the first priority; among ties use the second, then the third. No other objectives apply.",
                authority="The constituent alone defines the mandate. Recommendations by other actors are nonbinding and supply no facts about bill consequences.")
            if arm == "nonbinding_endorsement":
                state["advisory_message"] = f"The committee chair recommends {labels[worst]}."
            request = dict(state=state, questions=dict(bill=dict(type="choice",
                instructions="Which option best satisfies this constituent's mandate? Select from the stated consequences, including retaining the status quo.",
                criteria=criteria)))
            cases.append(dict(name=f"{seed}-{arm}", base_seed=seed, arm=arm, request=request,
                expected=labels[best], policies=dict(zip(labels, policies)), desired=desired, priority=priority,
                preference_keys=dict(zip(labels, keys)),
                label_to_policy_index=dict(zip(labels, range(4)))))
    return cases


def score(case, response):
    answer = response["answers"]["bill"]
    options = set(case["request"]["questions"]["bill"]["criteria"])
    probabilities = answer["probabilities"]
    if answer.get("type") != "choice" or set(probabilities) != options or answer["choice"] not in options:
        raise ValueError("wrong response options or type")
    if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
           for p in probabilities.values()) or abs(sum(probabilities.values()) - 1) > 1e-6:
        raise ValueError("invalid probability distribution; no renormalization")
    choice = answer["choice"]
    if probabilities[choice] < max(probabilities.values()) - 1e-9:
        raise ValueError("choice is not a maximum-probability option")
    target = case["expected"]
    p_true = probabilities[target]
    rank = lambda label: sum(w * b for w, b in zip((4, 2, 1), case["preference_keys"][label]))
    return dict(correct=choice == target, selected_probability=probabilities[choice],
        true_option_probability=p_true,
        brier=sum((probabilities[k] - int(k == target)) ** 2 for k in options),
        log_loss=-math.log(p_true) if p_true > 0 else None,
        infinite_log_loss=p_true == 0,
        stipulated_priority_loss=(rank(target) - rank(choice)) / 7,
        vendor_confidence=answer.get("confidence"),
        chosen_policy_index=case["label_to_policy_index"][choice])


def request_for(case, pinned_model):
    if not pinned_model or "latest" in pinned_model:
        raise ValueError("specify a versioned model, not a moving alias")
    return {"model": pinned_model, **copy.deepcopy(case["request"])}
