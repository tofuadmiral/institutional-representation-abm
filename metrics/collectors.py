from __future__ import annotations

from typing import Callable, Dict, Any

from mesa.datacollection import DataCollector


def default_model_reporters() -> Dict[str, Callable[[Any], Any]]:
    """
    Model-level metrics tracked across institutional variants.

    These are deliberately simple aggregate indicators that help verify that
    runs are reproducible and that institutional subclasses behave comparably.
    """

    return {
        "schedule_time": lambda m: m.schedule.time,
        "num_legislators": lambda m: m.num_legislators,
        "num_constituencies": lambda m: m.num_constituencies,
        "num_parties": lambda m: m.num_parties,
    }


def default_agent_reporters() -> Dict[str, Callable[[Any], Any]]:
    """
    Agent-level metrics tracked for basic inspection of the population.

    The baseline focuses on static properties rather than dynamic behavior.
    """

    return {
        "agent_type": lambda a: type(a).__name__,
    }


def build_default_datacollector() -> DataCollector:
    """
    Construct a DataCollector with baseline model and agent reporters.

    Institutional subclasses can reuse or extend this configuration without
    needing to re-specify common metrics.
    """

    return DataCollector(
        model_reporters=default_model_reporters(),
        agent_reporters=default_agent_reporters(),
    )


