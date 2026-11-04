"""Private arithmetic fixtures, never experimental observations."""
from dataclasses import replace

from analysis import paper3_mechanism_audit_v1 as audit
from paper3 import retrospective_accountability as core


def fixture():
    # p1 yields SUM +10 but four approvals; p2 SUM +8 and five approvals.
    first = tuple(zip((0,) * 9, (4, 4, 4, 4, -1, -1, -1, -1, -2),
                      (2, 2, 2, 2, 4, -1, -1, -1, -1), strict=True))
    second = tuple((0, 1, 2) for _ in range(9))
    return core.Game("private", ((first,) * 7, (second,) * 7), (0, 1), 24)


def test_strict_reversal_and_ties():
    p = audit.menu(fixture(), "binding_majority")[0]
    assert [x["utility"] for x in p] == [0, 10, 8]
    assert [x["score"] for x in p] == [24, 10, 32]
    r = audit.preferences(p)
    assert r["mandate_optima"] == [1] and r["office_optima"] == [2]
    assert r["disjoint_optima"] and len(r["strict_reversals"]) == 2
    assert audit.choice(p, 2)["optimum_membership"] == "office_only"
    assert audit.maxima([0, 3, 3]) == [1, 2]


def test_zero_bonus_and_control_arms_remove_reversals():
    game = fixture()
    for arm in ("advisory_majority", "advisory_sum", "binding_sum"):
        assert not audit.preferences(audit.menu(game, arm)[0])["strict_reversals"]
    for arm in core.ARMS:
        assert not audit.preferences(audit.menu(replace(game, office_value=0), arm)[0])["strict_reversals"]
        assert not audit.preferences(audit.menu(game, arm, 1)[0])["strict_reversals"]


def test_nonpivotal_vote_does_not_create_local_tradeoff():
    game = fixture()
    nonpivotal = core.conditional_ballot_scores(game, "binding_majority", 0, 1, (True,) * 6)
    pivotal = core.conditional_ballot_scores(game, "binding_majority", 0, 1, (True,) * 3 + (False,) * 3)
    assert nonpivotal[True] == nonpivotal[False]
    assert pivotal[True] - pivotal[False] == -14
    assert sum(row[1] for row in game.utilities[0][0]) == 10


def test_reference_policies_have_distinguishable_choices():
    game = fixture()
    for coalition in (False, True):
        mandate, _ = audit.reference(game, "binding_majority", "utility", coalition)
        office, _ = audit.reference(game, "binding_majority", "score", coalition)
        assert mandate.terms[0].enacted == 1
        assert office.terms[0].enacted == 2
        assert mandate.terms[1].enacted == office.terms[1].enacted == 2


def test_passage_filter_and_mixed_tied_maxima():
    m = audit.menu(fixture(), "binding_majority")
    assert audit.passable(m, "utility") == [0, 1, 2]
    assert audit.passable(m, "score") == [0, 2]
    prefs = audit.preferences([dict(utility=0, score=0), dict(utility=3, score=4),
                              dict(utility=3, score=5)])
    assert prefs["mandate_optima"] == [1, 2] and prefs["office_optima"] == [2]
    assert not prefs["disjoint_optima"]
    assert prefs["strict_reversals"] == []


def test_guard_blocks_network_process_and_protected_write(tmp_path):
    # Install in a separate interpreter: the audit hook is intentionally permanent.
    import subprocess
    import sys
    code = """
from pathlib import Path
from analysis.paper3_mechanism_audit_v1 import install_guard
output=Path(__import__('sys').argv[1]).resolve()
state=install_guard(output)
try:
    (output.parent/'forbidden').write_text('no')
except RuntimeError:
    pass
else:
    raise AssertionError('write guard')
with output.open('x') as f: f.write('private test')
assert state == {'network_denials': 1, 'process_denials': 1}
"""
    result = subprocess.run([sys.executable, "-B", "-c", code, str(tmp_path / "allowed")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "forbidden").exists()
