from paper3.institution import AuthorityRule, CoalitionContract, Mandate, Policy, reauthorization_ledger, resolve_contract


POLICIES = (Policy("status_quo", (0.0, 0.0)), Policy("deal", (1.0, 0.0)))
MANDATES = (
    Mandate(0, (1.0, 0.0), hard_loss_limit=0.3),
    Mandate(1, (1.0, 0.0), hard_loss_limit=0.3),
    Mandate(2, (0.0, 0.0), hard_loss_limit=0.3),
    Mandate(3, (0.0, 0.0), hard_loss_limit=0.3),
    Mandate(4, (0.0, 0.0), hard_loss_limit=0.3),
    Mandate(5, (0.0, 0.0), hard_loss_limit=0.3),
    Mandate(6, (0.0, 0.0), hard_loss_limit=0.3),
)
CONTRACT = CoalitionContract(0, (0, 1, 2, 3), "deal")
REQUESTED = {0: "deal", 1: "deal", 2: "status_quo", 3: "status_quo", 4: "status_quo", 5: "status_quo", 6: "status_quo"}


def test_discipline_can_change_effective_vote_but_free_ratification_cannot():
    free = resolve_contract(mandates=MANDATES, policies=POLICIES, status_quo_id="status_quo", contract=CONTRACT, requested_votes=REQUESTED, authority=AuthorityRule.FREE_RATIFICATION)
    disciplined = resolve_contract(mandates=MANDATES, policies=POLICIES, status_quo_id="status_quo", contract=CONTRACT, requested_votes=REQUESTED, authority=AuthorityRule.COALITION_DISCIPLINE)
    assert not free.accepted
    assert disciplined.accepted
    assert disciplined.overridden_members == (2, 3)


def test_mandate_veto_rejects_a_majority_deal_that_violates_named_member_mandates():
    record = resolve_contract(mandates=MANDATES, policies=POLICIES, status_quo_id="status_quo", contract=CONTRACT, requested_votes=REQUESTED, authority=AuthorityRule.MANDATE_VETO)
    assert not record.accepted
    assert record.reason == "mandate veto"
    assert record.final_policy_id == "status_quo"


def test_reauthorization_is_procedural_and_records_who_lost_future_eligibility():
    record = resolve_contract(mandates=MANDATES, policies=POLICIES, status_quo_id="status_quo", contract=CONTRACT, requested_votes=REQUESTED, authority=AuthorityRule.COALITION_DISCIPLINE)
    ledger = reauthorization_ledger(term=1, record=record, mandates=MANDATES, policies=POLICIES)
    assert ledger.principal_reauthorized[0]
    assert not ledger.principal_reauthorized[2]
    assert ledger.context_for(2)["prior_policy_id"] == "deal"
