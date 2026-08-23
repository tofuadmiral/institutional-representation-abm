from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from config import (
    HUNG_COHESIVE_OBSTRUCTION,
    HUNG_PERSONAL_VOTE,
    ParliamentaryConfig,
    RepublicanConfig,
    SemiPresidentialConfig,
    premier_presidential_config,
)
from experiments.hung_parliament import (
    MAJORITY_DRIVEN_INSTITUTIONS,
    _config_with_variant,
    run_hung_parliament_comparison,
    summarize_variants,
)
from experiments.scenarios import FRAGMENTED, BASELINE


def test_default_behaviour_is_cohesive_obstruction():
    """Backward compatibility: shipped defaults reproduce pre-Phase-H results."""
    assert ParliamentaryConfig().hung_parliament_behavior == HUNG_COHESIVE_OBSTRUCTION
    assert SemiPresidentialConfig().hung_parliament_behavior == HUNG_COHESIVE_OBSTRUCTION


def test_config_with_variant_only_touches_the_flag():
    cfg = _config_with_variant("parliamentary", HUNG_PERSONAL_VOTE)
    base = ParliamentaryConfig()
    changed = {f.name for f in dataclasses.fields(base)
               if getattr(cfg, f.name) != getattr(base, f.name)}
    assert changed == {"hung_parliament_behavior"}


def test_flag_is_inert_for_republican_and_president_parliamentary():
    """No formation gate / always a minority cabinet, so the flag cannot bind."""
    assert isinstance(_config_with_variant("republican", HUNG_PERSONAL_VOTE), RepublicanConfig)
    pp = _config_with_variant("president_parliamentary", HUNG_PERSONAL_VOTE)
    assert pp.government_formation == "president_driven"
    # republican has no hung-parliament field at all
    assert not hasattr(RepublicanConfig(), "hung_parliament_behavior")


def test_personal_vote_restores_fragmented_passage():
    """The Phase H decomposition: formation failure alone must NOT collapse passage."""
    df = run_hung_parliament_comparison(
        scenarios=[FRAGMENTED],
        institutions=["parliamentary", "premier_presidential"],
        n_seeds=40,
        n_jobs=1,
    )
    means = df.groupby(["institution", "hung_parliament_behavior"])["passage_rate"].mean()

    for inst in ("parliamentary", "premier_presidential"):
        obstructed = means[(inst, HUNG_COHESIVE_OBSTRUCTION)]
        personal = means[(inst, HUNG_PERSONAL_VOTE)]
        # cohesive obstruction reproduces the collapse
        assert obstructed < 0.05, f"{inst}: expected collapse under obstruction, got {obstructed}"
        # personal vote restores substantial throughput
        assert personal > 0.25, f"{inst}: expected restoration under personal vote, got {personal}"
        assert personal - obstructed > 0.2


def test_flag_inert_when_a_coalition_forms():
    """Baseline forms a government, so both variants must agree closely."""
    df = run_hung_parliament_comparison(
        scenarios=[BASELINE],
        institutions=["parliamentary"],
        n_seeds=20,
        n_jobs=1,
    )
    piv = df.pivot_table(index="seed", columns="hung_parliament_behavior",
                         values="passage_rate")
    # Identical coalition state => identical draws => identical passage per seed.
    assert (piv[HUNG_COHESIVE_OBSTRUCTION] == piv[HUNG_PERSONAL_VOTE]).mean() > 0.9


def test_summarize_variants_reports_delta():
    df = run_hung_parliament_comparison(
        scenarios=[FRAGMENTED], institutions=["parliamentary"], n_seeds=10, n_jobs=1,
    )
    summary = summarize_variants(df)
    row = summary[summary["institution"] == "parliamentary"].iloc[0]
    means = df.groupby("hung_parliament_behavior")["passage_rate"].mean()
    expected_delta = float(means[HUNG_PERSONAL_VOTE] - means[HUNG_COHESIVE_OBSTRUCTION])
    assert abs(float(row["delta_personal_minus_obstruction"]) - expected_delta) < 1e-12


def test_majority_driven_membership():
    assert set(MAJORITY_DRIVEN_INSTITUTIONS) == {"parliamentary", "premier_presidential"}
