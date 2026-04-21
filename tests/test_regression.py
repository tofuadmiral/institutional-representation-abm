from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from experiments.multiseed_comparison import _simulate_one
from experiments.scenarios import DEFAULT_SCENARIOS, SCENARIOS_BY_NAME

REPO_ROOT = Path(__file__).parent.parent
FIXTURE_PATH = REPO_ROOT / "institutional_comparison_results.csv"


@pytest.fixture(scope="module")
def fixture_df() -> pd.DataFrame:
    return pd.read_csv(FIXTURE_PATH)


@pytest.mark.parametrize(
    "scenario_name,institution",
    [
        (scenario.name, institution)
        for scenario in DEFAULT_SCENARIOS
        for institution in ("parliamentary", "republican")
    ],
)
def test_passage_rate_matches_fixture(
    scenario_name: str,
    institution: str,
    fixture_df: pd.DataFrame,
) -> None:
    """Seed=42 single-run outputs must match the committed fixture exactly.

    If this test fails after an intentional mechanism change, regenerate
    institutional_comparison_results.csv in the same commit and document the
    delta in docs/PHASE_A_NOTES.md.
    """
    scenario = SCENARIOS_BY_NAME[scenario_name]
    result = _simulate_one(scenario, institution, seed=42)

    expected = fixture_df[
        (fixture_df["scenario"] == scenario_name)
        & (fixture_df["institution"] == institution)
    ]
    assert len(expected) == 1, f"Fixture missing row for ({scenario_name}, {institution})"
    expected_row = expected.iloc[0]

    assert result["bills_passed"] == int(expected_row["bills_passed"]), (
        f"bills_passed mismatch for ({scenario_name}, {institution}): "
        f"got {result['bills_passed']}, expected {expected_row['bills_passed']}"
    )
    assert result["passage_rate"] == pytest.approx(
        float(expected_row["passage_rate"]), abs=1e-6
    )
