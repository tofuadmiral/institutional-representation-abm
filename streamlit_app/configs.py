"""Streamlit sidebar config builders.

For each institution we surface every tunable config field as a slider,
seeded with the default value. The builders read `st.session_state` and
return live config dataclasses; nothing else in the repo depends on this
module.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, Tuple

import streamlit as st

from config import (
    ParliamentaryConfig,
    RepublicanConfig,
    SemiPresidentialConfig,
    premier_presidential_config,
    president_parliamentary_config,
)

INSTITUTIONS = (
    "parliamentary", "republican", "premier_presidential", "president_parliamentary",
)

SLIDER_SPECS: Dict[str, Dict[str, Tuple[float, float, float, float]]] = {
    "parliamentary": {
        "discipline_strength": (0.0, 1.0, 0.01, 0.8),
        "confidence_threshold": (0.4, 0.7, 0.01, 0.5),
        "opposition_discipline_multiplier": (0.0, 1.0, 0.01, 0.7),
        "confidence_matter_rate": (0.0, 1.0, 0.01, 0.3),
        "legislative_activity_rate": (0.0, 1.0, 0.01, 0.2),
        "committee_gatekeeping_power": (0.0, 1.0, 0.01, 0.3),
    },
    "republican": {
        "discipline_strength": (0.0, 1.0, 0.01, 0.4),
        "executive_opposition_rate": (0.0, 1.0, 0.01, 0.3),
        "largest_party_presidency_prob": (0.0, 1.0, 0.01, 0.7),
        "max_veto_probability": (0.0, 1.0, 0.01, 0.8),
        "veto_distance_scale": (0.5, 5.0, 0.1, 2.0),
        "override_threshold_fraction": (0.5, 0.9, 0.01, 0.67),
        "legislative_activity_rate": (0.0, 1.0, 0.01, 0.3),
        "committee_gatekeeping_power": (0.0, 1.0, 0.01, 0.4),
    },
    "premier_presidential": {
        "discipline_strength": (0.0, 1.0, 0.01, 0.6),
        "confidence_threshold": (0.4, 0.7, 0.01, 0.5),
        "opposition_discipline_multiplier": (0.0, 1.0, 0.01, 0.7),
        "confidence_matter_rate": (0.0, 1.0, 0.01, 0.3),
        "legislative_activity_rate": (0.0, 1.0, 0.01, 0.25),
        "largest_party_presidency_prob": (0.0, 1.0, 0.01, 0.6),
        "max_veto_probability": (0.0, 1.0, 0.01, 0.6),
        "veto_distance_scale": (0.5, 5.0, 0.1, 2.0),
        "override_threshold_fraction": (0.5, 0.9, 0.01, 0.67),
        "executive_opposition_rate": (0.0, 1.0, 0.01, 0.2),
        "committee_gatekeeping_power": (0.0, 1.0, 0.01, 0.35),
    },
    "president_parliamentary": {
        "discipline_strength": (0.0, 1.0, 0.01, 0.6),
        "confidence_threshold": (0.4, 0.7, 0.01, 0.5),
        "opposition_discipline_multiplier": (0.0, 1.0, 0.01, 0.7),
        "confidence_matter_rate": (0.0, 1.0, 0.01, 0.3),
        "legislative_activity_rate": (0.0, 1.0, 0.01, 0.25),
        "largest_party_presidency_prob": (0.0, 1.0, 0.01, 0.6),
        "max_veto_probability": (0.0, 1.0, 0.01, 0.6),
        "veto_distance_scale": (0.5, 5.0, 0.1, 2.0),
        "override_threshold_fraction": (0.5, 0.9, 0.01, 0.67),
        "executive_opposition_rate": (0.0, 1.0, 0.01, 0.2),
        "committee_gatekeeping_power": (0.0, 1.0, 0.01, 0.35),
        "presidential_dismissal_rate": (0.0, 0.3, 0.01, 0.05),
    },
}


def _render_sliders(institution: str) -> Dict[str, Any]:
    """Draw a collapsible expander with a slider per tunable field."""
    overrides: Dict[str, Any] = {}
    with st.expander(institution.replace("_", " ").title(), expanded=False):
        for field, (lo, hi, step, default) in SLIDER_SPECS[institution].items():
            key = f"{institution}__{field}"
            # Honour a previously-set session state value, otherwise fall back to default.
            value = st.session_state.get(key, default)
            overrides[field] = st.slider(
                field, min_value=float(lo), max_value=float(hi),
                value=float(value), step=float(step), key=key,
            )
    return overrides


def build_configs_from_sidebar():
    """Read sidebar state, return a dict of institution→config dataclass."""
    overrides = {inst: _render_sliders(inst) for inst in INSTITUTIONS}
    return {
        "parliamentary": dataclasses.replace(ParliamentaryConfig(), **overrides["parliamentary"]),
        "republican": dataclasses.replace(RepublicanConfig(), **overrides["republican"]),
        "premier_presidential": dataclasses.replace(
            premier_presidential_config(), **overrides["premier_presidential"],
        ),
        "president_parliamentary": dataclasses.replace(
            president_parliamentary_config(), **overrides["president_parliamentary"],
        ),
    }
