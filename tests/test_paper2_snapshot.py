"""Integrity checks for the frozen Paper 2 evidence snapshot."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1] / "paper2" / "data"
PROCESSED = ROOT / "processed"


def _effects(directory: str, filename: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / directory / filename).set_index(
        ["scope", "metric"]
    )


def test_raw_completion_archive_is_the_frozen_snapshot():
    digest = hashlib.sha256((ROOT / "raw_completion_caches.tar.gz").read_bytes()).hexdigest()
    assert digest == "7041c25347664cf86d8dc8540fe9c2d57493a1d062a255265a8a00b5397feea2"


@pytest.mark.parametrize(
    ("directory", "correct", "violation", "suboptimal"),
    [
        ("multi_eligible_certificate_gate_qwen3_8b_n96", 0.8854166667, 0.0, -0.0208333333),
        ("multi_eligible_certificate_gate_mistral_24b_n96", 0.8854166667, 0.0, -0.0625),
    ],
)
def test_spatial_exact_effects(directory, correct, violation, suboptimal):
    effects = _effects(directory, "certificate_gate_effects.csv")
    assert effects.loc[("oracle_correct", "protected_oracle_match"), "effect"] == pytest.approx(correct)
    assert effects.loc[("aggregate_pressure_violation", "protected_oracle_match"), "effect"] == pytest.approx(violation)
    assert effects.loc[("compliant_suboptimal", "protected_oracle_match"), "effect"] == pytest.approx(suboptimal)


@pytest.mark.parametrize(
    ("directory", "correct", "violation", "suboptimal"),
    [
        ("portfolio_certificate_gate_qwen3_8b_n96", 0.59375, -0.0208333333, -0.5104166667),
        ("portfolio_certificate_gate_mistral_24b_n96", 0.40625, 0.0, -0.875),
    ],
)
def test_portfolio_exact_effects(directory, correct, violation, suboptimal):
    effects = _effects(directory, "portfolio_gate_effects.csv")
    assert effects.loc[("oracle_correct", "protected_oracle_match"), "effect"] == pytest.approx(correct)
    assert effects.loc[("aggregate_pressure_violation", "protected_oracle_match"), "effect"] == pytest.approx(violation)
    assert effects.loc[("compliant_suboptimal", "protected_oracle_match"), "effect"] == pytest.approx(suboptimal)


@pytest.mark.parametrize(
    ("directory", "counts"),
    [
        ("natural_proposer_qwen3_8b_n96", {"oracle_correct": 8, "protected_violation": 14, "compliant_suboptimal": 74}),
        ("natural_proposer_mistral_24b_n96", {"oracle_correct": 4, "protected_violation": 3, "compliant_suboptimal": 89}),
    ],
)
def test_natural_proposal_state_counts(directory, counts):
    proposals = pd.read_csv(PROCESSED / directory / "natural_proposers.csv")
    assert len(proposals) == 96
    assert proposals["response_valid"].all()
    assert proposals["proposal_state"].value_counts().to_dict() == counts


@pytest.mark.parametrize(
    ("directory", "filename", "expected_rows"),
    [
        ("multi_eligible_certificate_gate_qwen3_8b_n96", "certificate_reviews.csv", 288),
        ("multi_eligible_certificate_gate_mistral_24b_n96", "certificate_reviews.csv", 288),
        ("portfolio_certificate_gate_qwen3_8b_n96", "portfolio_reviews.csv", 288),
        ("portfolio_certificate_gate_mistral_24b_n96", "portfolio_reviews.csv", 288),
    ],
)
def test_primary_controlled_reviews_all_parsed(directory, filename, expected_rows):
    reviews = pd.read_csv(PROCESSED / directory / filename)
    assert len(reviews) == expected_rows
    assert reviews["response_valid"].all()
