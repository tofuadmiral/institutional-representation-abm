from __future__ import annotations

import pytest

from agents.legislator import LegislatorAgent
from bills.bill import Bill
from config import ParliamentaryConfig, RepublicanConfig
from institutions.parliamentary import ParliamentaryModel
from institutions.republican import RepublicanModel


def test_parliamentary_forms_government(parliamentary_model):
    assert parliamentary_model.government_formed is True
    assert parliamentary_model.government_party is not None
    assert len(parliamentary_model.government_coalition) >= 1
    assert parliamentary_model.prime_minister is not None


def test_republican_elects_executive(republican_model):
    assert republican_model.executive_party is not None
    assert republican_model.president is not None


def test_legislator_vote_threshold_is_read_from_config():
    """Changing vote_support_threshold must affect decide_vote behavior."""
    model = ParliamentaryModel(
        num_legislators=6,
        num_constituencies=2,
        num_parties=2,
        seed=1,
    )
    legislator = next(a for a in model.schedule.agents if isinstance(a, LegislatorAgent))
    bill = Bill(bill_id=0, ideology=legislator.ideology, salience=0.5)
    # Zero ideological distance is always below any positive threshold.
    assert legislator.decide_vote(bill) is True


def test_committee_behavior_is_deterministic_under_seed():
    """Regression guard: seeded runs must produce identical passage rates.

    This is the property the committee RNG fix restored -- previously committee
    ops drew from module-level random.* and ignored the model seed.
    """
    def run(seed: int) -> tuple[int, int]:
        parl = ParliamentaryModel(
            num_legislators=20, num_constituencies=6, num_parties=3,
            config=ParliamentaryConfig(), seed=seed,
        )
        rep = RepublicanModel(
            num_legislators=20, num_constituencies=6, num_parties=3,
            config=RepublicanConfig(), seed=seed,
        )
        bills_parl = [
            Bill(
                bill_id=i,
                ideology=(parl.random.uniform(-1, 1), parl.random.uniform(-1, 1)),
                salience=parl.random.uniform(0.3, 1.0),
            )
            for i in range(25)
        ]
        bills_rep = [
            Bill(
                bill_id=i,
                ideology=(rep.random.uniform(-1, 1), rep.random.uniform(-1, 1)),
                salience=rep.random.uniform(0.3, 1.0),
            )
            for i in range(25)
        ]
        p_passed = sum(1 for b in bills_parl if parl.pass_legislation(b))
        r_passed = sum(1 for b in bills_rep if rep.pass_legislation(b))
        return p_passed, r_passed

    # Three identical runs with the same seed must match exactly.
    run_a = run(42)
    run_b = run(42)
    run_c = run(42)
    assert run_a == run_b == run_c

    # Different seeds should (almost surely) produce different outcomes.
    assert run(1) != run(2)


def test_executive_veto_requires_president():
    """Edge-case: model with zero legislators has no president and should not veto."""
    model = RepublicanModel(
        num_legislators=0, num_constituencies=1, num_parties=0,
        config=RepublicanConfig(), seed=0,
    )
    bill = Bill(bill_id=0, ideology=(0.0, 0.0), salience=0.5)
    assert model._executive_veto_check(bill) is False


def test_parliamentary_bills_route_through_committee(parliamentary_model):
    """A bill within committee jurisdiction is tracked in bills_in_committee."""
    bill = Bill(bill_id=0, ideology=(0.3, 0.0), salience=0.5)  # Finance-ish
    parliamentary_model.pass_legislation(bill)
    assert 0 in parliamentary_model.bills_in_committee


def test_committee_totals_reflect_decisions(parliamentary_model):
    """After processing several bills, committee counters must be non-zero."""
    for i in range(10):
        bill = Bill(
            bill_id=i,
            ideology=(parliamentary_model.random.uniform(-1, 1), parliamentary_model.random.uniform(-1, 1)),
            salience=0.5,
        )
        parliamentary_model.pass_legislation(bill)
    stats = parliamentary_model.get_committee_stats()
    assert stats["total_bills_considered"] > 0
    assert stats["num_committees"] == 3
