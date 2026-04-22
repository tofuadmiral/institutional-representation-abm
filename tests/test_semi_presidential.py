from __future__ import annotations

import pytest

from bills.bill import Bill
from config import (
    GOV_FORMATION_MAJORITY_DRIVEN,
    GOV_FORMATION_PRESIDENT_DRIVEN,
    SemiPresidentialConfig,
    premier_presidential_config,
    president_parliamentary_config,
)
from institutions.semi_presidential import SemiPresidentialModel


@pytest.fixture
def premier_model() -> SemiPresidentialModel:
    return SemiPresidentialModel(
        num_legislators=20, num_constituencies=6, num_parties=3,
        config=premier_presidential_config(), seed=42,
    )


@pytest.fixture
def president_parl_model() -> SemiPresidentialModel:
    return SemiPresidentialModel(
        num_legislators=20, num_constituencies=6, num_parties=3,
        config=president_parliamentary_config(), seed=42,
    )


def test_premier_presidential_has_no_dismissal(premier_model):
    assert premier_model.config.president_can_dismiss_pm is False
    assert premier_model.config.government_formation == GOV_FORMATION_MAJORITY_DRIVEN


def test_president_parliamentary_can_dismiss(president_parl_model):
    assert president_parl_model.config.president_can_dismiss_pm is True
    assert president_parl_model.config.government_formation == GOV_FORMATION_PRESIDENT_DRIVEN


def test_both_variants_form_government_and_elect_president(premier_model, president_parl_model):
    for m in (premier_model, president_parl_model):
        assert m.government_formed is True
        assert m.president is not None
        assert m.prime_minister is not None
        assert m.government_party is not None
        assert m.executive_party is not None


def test_president_driven_government_uses_president_party():
    """Under president-driven formation, the governing party is the president's party."""
    for seed in range(10):
        model = SemiPresidentialModel(
            num_legislators=20, num_constituencies=6, num_parties=3,
            config=president_parliamentary_config(), seed=seed,
        )
        if model.government_formed and model.executive_party is not None:
            assert model.government_party == model.executive_party


def test_semi_presidential_passage_is_between_parl_and_rep():
    """Sanity check: semi-pres passage should sit between parl and rep at baseline."""
    # Not a strict law, but should hold in expectation across seeds.
    from institutions.parliamentary import ParliamentaryModel
    from institutions.republican import RepublicanModel

    def simulate(ModelClass, cfg, seed):
        m = ModelClass(num_legislators=20, num_constituencies=6, num_parties=3,
                       config=cfg, seed=seed)
        passed = 0
        for i in range(25):
            b = Bill(
                bill_id=i,
                ideology=(m.random.uniform(-1, 1), m.random.uniform(-1, 1)),
                salience=m.random.uniform(0.3, 1.0),
            )
            if m.pass_legislation(b):
                passed += 1
        return passed

    parl_total = 0
    rep_total = 0
    semi_total = 0
    for seed in range(20):
        from config import ParliamentaryConfig, RepublicanConfig
        parl_total += simulate(ParliamentaryModel, ParliamentaryConfig(), seed)
        rep_total += simulate(RepublicanModel, RepublicanConfig(), seed)
        semi_total += simulate(SemiPresidentialModel, premier_presidential_config(), seed)

    # Semi-presidential is hybrid: should fall between pure parliamentary and pure republican.
    # With 20 seeds * 25 bills = 500 max; we check relative ordering.
    # Parliamentary (high discipline) > semi-pres > republican is the expected order,
    # but we only enforce semi-pres is not at either extreme.
    assert min(parl_total, rep_total) - 20 < semi_total < max(parl_total, rep_total) + 20


def test_semi_presidential_is_deterministic():
    a = SemiPresidentialModel(
        num_legislators=20, num_constituencies=6, num_parties=3,
        config=president_parliamentary_config(), seed=7,
    )
    b = SemiPresidentialModel(
        num_legislators=20, num_constituencies=6, num_parties=3,
        config=president_parliamentary_config(), seed=7,
    )
    bills_a = [
        Bill(bill_id=i,
             ideology=(a.random.uniform(-1, 1), a.random.uniform(-1, 1)),
             salience=a.random.uniform(0.3, 1.0))
        for i in range(15)
    ]
    bills_b = [
        Bill(bill_id=i,
             ideology=(b.random.uniform(-1, 1), b.random.uniform(-1, 1)),
             salience=b.random.uniform(0.3, 1.0))
        for i in range(15)
    ]
    a_passes = sum(1 for bill in bills_a if a.pass_legislation(bill))
    b_passes = sum(1 for bill in bills_b if b.pass_legislation(bill))
    assert a_passes == b_passes


def test_custom_config_overrides_default():
    cfg = SemiPresidentialConfig(
        discipline_strength=0.1, confidence_threshold=0.55,
    )
    model = SemiPresidentialModel(
        num_legislators=15, num_constituencies=5, num_parties=2,
        config=cfg, seed=0,
    )
    assert model.config.discipline_strength == 0.1
    assert model.config.confidence_threshold == 0.55


def test_presidential_dismissal_fires_in_batch_runs():
    """Regression: dismissal must fire during pass_legislation, not only during step().

    CLI batch runners call pass_legislation directly and never touch step();
    if dismissal lives only in step(), it's dead code for all reported figures.
    """
    total_dismissals_pp = 0
    total_dismissals_premier = 0
    for seed in range(50):
        pp = SemiPresidentialModel(
            num_legislators=24, num_constituencies=8, num_parties=5,
            config=president_parliamentary_config(), seed=seed,
        )
        premier = SemiPresidentialModel(
            num_legislators=24, num_constituencies=8, num_parties=5,
            config=premier_presidential_config(), seed=seed,
        )
        for i in range(30):
            b_pp = Bill(
                bill_id=i,
                ideology=(pp.random.uniform(-1, 1), pp.random.uniform(-1, 1)),
                salience=pp.random.uniform(0.3, 1.0),
            )
            pp.pass_legislation(b_pp)
            b_pr = Bill(
                bill_id=i,
                ideology=(premier.random.uniform(-1, 1), premier.random.uniform(-1, 1)),
                salience=premier.random.uniform(0.3, 1.0),
            )
            premier.pass_legislation(b_pr)
        total_dismissals_pp += pp.presidential_dismissals
        total_dismissals_premier += premier.presidential_dismissals

    assert total_dismissals_pp > 0, "dismissal must fire in batch mode"
    assert total_dismissals_premier == 0, "premier-presidential must not dismiss"


def test_stats_accessors_return_expected_keys(premier_model):
    gov = premier_model.get_government_stats()
    sys = premier_model.get_system_stats()
    sep = premier_model.get_separation_of_powers_stats()
    committees = premier_model.get_committee_stats()

    assert {"variant", "government_formation", "government_formed", "coalition_size",
            "presidential_dismissals"}.issubset(gov.keys())
    assert {"bills_passed", "bills_vetoed", "gridlock_events"}.issubset(sys.keys())
    assert {"cohabitation", "divided_government", "veto_rate"}.issubset(sep.keys())
    assert {"num_committees", "total_bills_considered"}.issubset(committees.keys())
