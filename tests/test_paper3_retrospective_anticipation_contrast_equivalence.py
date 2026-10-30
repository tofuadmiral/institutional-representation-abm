"""Exact optimization equivalence, including every scalar/horizon/missing case."""
from fractions import Fraction

import pytest

from paper3 import retrospective_anticipation_analysis as analysis
from paper3 import retrospective_anticipation_baselines as baseline
from paper3 import retrospective_anticipation_design as design
from paper3 import retrospective_joint_outcome_bounds as reference


@pytest.mark.parametrize("coverage", ("all_missing", "complete_and_partial"))
def test_every_reused_contrast_matches_original_joint_menu_computation(coverage):
    items = design.assignments()
    observations = {}
    for index, item in enumerate(items):
        if coverage == "all_missing" or index % 3 == 0:
            observations[item["id"]] = (None, None)
        else:
            episode = baseline.mandate_only(item["game"], item["arm"])["episode"]
            observations[item["id"]] = (episode.terms[0], None) if index % 3 == 1 else episode.terms
    result = analysis.analyze(items, observations, minimum_effect=Fraction(1, 25), aligned_fraction=Fraction(1, 2))
    for horizon in ("first_term", "two_term"):
        for metric in reference.SCALARS:
            for kind in ("interaction", "aligned", "conflict"):
                selected = [a for a in items if kind == "interaction" or a["stratum"] == kind]
                weighted = tuple((a["id"], a["game"], a["arm"], observations[a["id"]],
                    Fraction(analysis.WEIGHTS[a["arm"]] *
                    (-1 if kind == "interaction" and a["stratum"] == "aligned" else 1), 2))
                    for a in selected)
                assert result["readouts"][horizon][metric][kind] == reference.contrast(weighted, metric, horizon)
    assert result["assigned"] == len(result["assignments"]) == 16
