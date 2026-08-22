"""Tests for the clustered-initialisation robustness experiment."""
from __future__ import annotations

import math

from config import ParliamentaryConfig
from experiments.clustered_robustness import apply_clustered_ideologies
from experiments.scenarios import FRAGMENTED
from institutions.parliamentary import ParliamentaryModel


def _fragmented_model(seed: int = 42) -> ParliamentaryModel:
    return ParliamentaryModel(
        num_legislators=FRAGMENTED.num_legislators,
        num_constituencies=FRAGMENTED.num_constituencies,
        num_parties=FRAGMENTED.num_parties,
        config=ParliamentaryConfig(),
        seed=seed,
    )


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_default_init_is_unchanged_diagonal_spread():
    model = _fragmented_model()
    for legislator in model.legislators:
        x, y = legislator.ideology
        assert x == y  # on the main diagonal
    positions = sorted(l.ideology[0] for l in model.legislators)
    assert positions[0] == -1.0 and positions[-1] == 1.0


def test_clustered_legislators_sit_nearest_their_own_party():
    model = _fragmented_model()
    apply_clustered_ideologies(model, seed=42, spread=0.15)
    party_positions = {
        p: model._default_ideology(p, model.num_parties)
        for p in range(model.num_parties)
    }
    own_closer = 0
    for legislator in model.legislators:
        d_own = _dist(legislator.ideology, party_positions[legislator.party_id])
        d_others = min(
            _dist(legislator.ideology, pos)
            for p, pos in party_positions.items()
            if p != legislator.party_id
        )
        if d_own < d_others:
            own_closer += 1
    # With spread=0.15 and parties 0.5 apart, essentially all legislators
    # should sit nearest their own party.
    assert own_closer >= 0.9 * len(model.legislators)


def test_clustered_init_is_deterministic_under_seed():
    model_a = _fragmented_model(seed=7)
    model_b = _fragmented_model(seed=7)
    apply_clustered_ideologies(model_a, seed=7)
    apply_clustered_ideologies(model_b, seed=7)
    ideologies_a = [l.ideology for l in sorted(model_a.legislators, key=lambda a: a.unique_id)]
    ideologies_b = [l.ideology for l in sorted(model_b.legislators, key=lambda a: a.unique_id)]
    assert ideologies_a == ideologies_b


def test_clustering_does_not_touch_model_rng_stream():
    model_a = _fragmented_model(seed=11)
    model_b = _fragmented_model(seed=11)
    apply_clustered_ideologies(model_a, seed=11)
    # The model RNG must be in the same state whether or not clustering ran.
    assert model_a.random.random() == model_b.random.random()
