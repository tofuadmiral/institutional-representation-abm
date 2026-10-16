"""Fabricated institution/science integration, NOT new empirical assignments.

Independent synthetic fixtures, no historical response rows, no ledger/network.
Ensure resource isolation cannot silently filter cases or redefine the horizon.
"""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import json

import pytest

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_electorates as electorates
from paper3 import retrospective_independent_execution as previous
from paper3 import retrospective_resource_execution_v1 as execution
from paper3 import retrospective_billing_calls as service
from tests.test_paper3_retrospective_independent_execution import row


def fixture_assignments():
    rows = []
    for i, seed in enumerate((7101, 7102)):
        pair = electorates.generate(seed)
        for stratum in science.STRATA:
            game = replace(getattr(pair, stratum), game_id=f"fabricated-science-{i}-{stratum}")
            for arm in institution.ARMS:
                rows.append(dict(id=f"fabricated-science-{i}-{stratum}-{arm}",
                    seed=seed, seed_base=7900000 + 64 * i, stratum=stratum, arm=arm, game=game))
    return tuple(rows)


def fabricated_run(bad_index):
    assigned = fixture_assignments()
    def respond(request, identifier):
        saved = row(request, identifier, absent=True)
        if identifier == assigned[0]["id"] + f"-{bad_index:02d}":
            frames = [json.loads(line[6:]) for line in saved["stream"]["lines"]
                      if line.startswith("data: ") and line != "data: [DONE]"]
            frames[1]["choices"][0].update(delta=dict(content=""), finish_reason="length")
            frames[2]["usage"].update(completion_tokens=14000,
                completion_tokens_details=dict(reasoning_tokens=14002))
            saved["stream"]["lines"] = [line for frame in frames
                for line in ("data: " + json.dumps(frame), "")] + ["data: [DONE]", ""]
            saved["assessment"] = service.assess(saved, previous.CONFIG)
        return saved
    report = execution.execute(assigned, respond=respond, verify=lambda: None,
                               persist=lambda event: None)
    observations = {r["id"]: tuple(r["terms"]) for r in report["assignments"]}
    readout = science.analyze(assigned, observations,
        minimum_effect=Fraction(1, 25), aligned_fraction=Fraction(1, 2))
    return assigned, observations, report, readout


@pytest.mark.parametrize("bad_index", (0, 14, 15, 29))
def test_first_term_screen_and_full_horizon_missingness_are_not_conflated(bad_index):
    assigned, observations, execution_report, readout = fabricated_run(bad_index)
    assert execution_report["assigned"] == readout["assigned"] == 16
    assert execution_report["resource_failed"] == 1 and execution_report["completed"] == 15
    assert not execution_report["global_safety_stop"]
    assert readout["first_terms_complete"] == (15 if bad_index < 15 else 16)
    assert readout["episodes_complete"] == 15
    screen = readout["candidate_screen"]
    assert screen["status"] == ("incomplete_first_term" if bad_index < 15 else "no_selected_case_lead")
    assert not screen["selected_case_lead"] and not readout["publication_evidence"]
    first = next(r for r in readout["assignments"] if r["id"] == assigned[0]["id"])
    assert not first["two_term"]["complete"]
    assert len(first["two_term"]["citizen_utility_bounds"]) == 7
    assert all(len(d) == 9 for d in first["two_term"]["citizen_utility_bounds"])
    for horizon in ("first_term", "two_term"):
        for metric in readout["readouts"][horizon].values():
            assert metric["interaction"]["assigned"] == 16
            assert len(metric["interaction"]["assignments"]) == 16
            assert any(r["id"] == assigned[0]["id"] for r in metric["interaction"]["assignments"])
    before = deepcopy(observations)
    filtered = {k: v for k, v in observations.items() if k != assigned[0]["id"]}
    with pytest.raises(ValueError, match="no filtering"):
        science.analyze(assigned, filtered, minimum_effect=Fraction(1, 25), aligned_fraction=Fraction(1, 2))
    assert observations == before
