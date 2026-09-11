"""Integrity checks for the frozen Paper 2 evidence snapshot."""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

import pandas as pd
import pytest


PAPER2_ROOT = Path(__file__).resolve().parents[1] / "paper2"
ROOT = PAPER2_ROOT / "data"
PROCESSED = ROOT / "processed"


def test_arxiv_source_bundle_is_minimal_and_self_contained():
    expected = {
        "main.tex",
        "main.bbl",
        "references.bib",
        "plainurl.bst",
        "figures",
        "figures/natural_proposal_outcomes.pdf",
        "figures/prevalence_frontiers.pdf",
        "figures/state_conditional_effects.pdf",
        "tables",
        "tables/action_aware_validation.tex",
        "tables/natural_results.tex",
        "tables/state_effects.tex",
    }
    with tarfile.open(PAPER2_ROOT / "arxiv-submission.tar.gz", "r:gz") as archive:
        members = archive.getmembers()

    assert {member.name for member in members} == expected
    assert all(not member.name.startswith("/") for member in members)
    assert all(".." not in Path(member.name).parts for member in members)


def _effects(directory: str, filename: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / directory / filename).set_index(
        ["scope", "metric"]
    )


def test_raw_completion_archive_is_the_frozen_snapshot():
    archive_path = ROOT / "raw_completion_caches.tar.gz"
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert digest == "4fe83a4df6ace60efcbbaa6c321d0802c323212b5378670a0b90da2d6736dcea"
    with tarfile.open(archive_path, "r:gz") as archive:
        action_members = [
            member.name
            for member in archive.getmembers()
            if member.name.startswith("results/paper2/") and member.name.endswith(".json")
        ]
    assert len(action_members) == 288
    assert all("failed" not in name for name in action_members)


@pytest.mark.parametrize(
    ("directory", "dispositions"),
    [
        (
            "action_aware_qwen_n48",
            {
                "oracle_correct": {"retain": 48},
                "aggregate_pressure_violation": {"retain": 19, "replace": 29},
                "compliant_suboptimal": {"retain": 48},
            },
        ),
        (
            "action_aware_mistral_n48",
            {
                "oracle_correct": {"replace": 48},
                "aggregate_pressure_violation": {"replace": 48},
                "compliant_suboptimal": {"retain": 2, "replace": 46},
            },
        ),
    ],
)
def test_action_aware_validation_snapshot(directory, dispositions):
    reviews = pd.read_csv(PROCESSED / directory / "action_aware_reviews.csv")
    assert len(reviews) == 144
    assert reviews["response_valid"].all()
    assert reviews["certificate_fields_valid"].all()
    for state, expected in dispositions.items():
        scoped = reviews[reviews["proposal_state"] == state]
        assert scoped["disposition"].value_counts().to_dict() == expected


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
