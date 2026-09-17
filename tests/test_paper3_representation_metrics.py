import pytest

from paper3.commitment_memory import profile
from paper3.representation_metrics import feasible_portfolios, representation_metrics


def test_menu_includes_abstention_and_single_projects():
    assert len(feasible_portfolios()) == 9
    assert () in feasible_portfolios()
    assert ("A0",) in feasible_portfolios()
    assert ("A0", "A1") not in feasible_portfolios()


def test_baseline_is_agenda_conditional_not_an_equilibrium_claim():
    p = profile(7)
    r = representation_metrics(p.utilities, ("A0", "B0"), ("A0", "B0"), list(range(7)))
    assert r["myopic_selected_agenda_projects"] == ()
    assert r["negative_package_signers"] == ["6"]
    assert r["loss_principals"] == ["6"]
    assert all(0 <= x <= 1 for x in r["normalized_individual_regret"].values())
    other = representation_metrics(p.utilities, ("A1", "B1"), ("A1", "B1"), list(range(7)))
    assert other["myopic_selected_agenda_projects"] == ("A1", "B1")


def test_symmetry_preserves_utility_metrics():
    a = representation_metrics(profile(7).utilities, ("A0", "B1"), ("A0",), [0, 3])
    b = representation_metrics(profile(7, True).utilities, ("B0", "A1"), ("B0",), [0, 3])
    assert a["realized"] == b["realized"]
    assert a["normalized_individual_regret"] == b["normalized_individual_regret"]
    assert a["utilitarian_menu_ceiling"] == b["utilitarian_menu_ceiling"]


def test_reject_inconsistent_or_illegal_agenda():
    with pytest.raises(ValueError):
        representation_metrics(profile(7).utilities, ("A0", "B0"), ("A1",), [])
    with pytest.raises(ValueError):
        representation_metrics(profile(7).utilities, ("A0", "A1"), (), [])
