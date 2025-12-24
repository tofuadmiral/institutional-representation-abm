from __future__ import annotations

from institutions.parliamentary import ParliamentaryModel
from institutions.republican import RepublicanModel
from mesa.datacollection import DataCollector


def run_baseline_parliamentary(steps: int = 5) -> None:
    """
    Instantiate and run a minimal parliamentary baseline model.

    The output is limited to simple diagnostics that verify the model runs
    end-to-end and that data collection is functioning.
    """
    model = ParliamentaryModel(
        num_legislators=10,
        num_constituencies=5,
        num_parties=2,
        seed=42,
    )

    for _ in range(steps):
        model.step()

    model_df = model.datacollector.get_model_vars_dataframe()
    agent_df = model.datacollector.get_agent_vars_dataframe()

    print("Parliamentary model-level metrics:")
    print(model_df)
    print("\nParliamentary agent-level metrics (tail):")
    print(agent_df.tail())


def run_baseline_republican(steps: int = 5) -> None:
    """
    Instantiate and run a minimal republican baseline model.

    This uses the same population and reporters as the parliamentary variant,
    differing only by the institutional subclass.
    """
    model = RepublicanModel(
        num_legislators=10,
        num_constituencies=5,
        num_parties=2,
        seed=42,
    )

    for _ in range(steps):
        model.step()

    model_df = model.datacollector.get_model_vars_dataframe()
    agent_df = model.datacollector.get_agent_vars_dataframe()

    print("Republican model-level metrics:")
    print(model_df)
    print("\nRepublican agent-level metrics (tail):")
    print(agent_df.tail())


if __name__ == "__main__":
    run_baseline_parliamentary()
    print("\n" + "=" * 80 + "\n")
    run_baseline_republican()


