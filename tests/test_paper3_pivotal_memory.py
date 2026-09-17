import json

from experiments.paper3_pivotal_memory_diagnostic import diagnostic_cases
from paper3.commitment_memory import contract_state


def test_cases_are_paired_and_every_vote_is_consequential():
    cases = diagnostic_cases()
    assert cases == diagnostic_cases()
    assert len(cases) == len({c['name'] for c in cases}) == 72
    groups = {}
    for c in cases:
        r = json.loads(c['messages'][1]['content'].split('\n')[0])
        others = r['binding_second_votes_by_other_representatives']
        assert str(r['principal']) not in others
        assert len(others) == 6 and sum(others.values()) == 3
        assert sum(others.values()) < 4 <= sum(others.values()) + 1
        state = contract_state(r['events'])
        due = r['principal'] in state['signers'] and state['status'] == 'second_vote_due'
        own = r['utilities_for_all_principals'][str(r['principal'])]['B0']
        assert c['expected']['vote'] == (due or own > 0)
        assert c['expected']['obligation_due'] == due
        assert c['expected']['current_project_utility'] == own
        assert 'Votes are simultaneous' not in c['messages'][0]['content']
        groups.setdefault(c['base_case'], []).append(c)
    for rows in groups.values():
        assert len(rows) == 3
        assert len({r['random_seed'] for r in rows}) == 1
        assert all(r['expected'] == rows[0]['expected'] for r in rows)
        clean = []
        for c in rows:
            payload = json.loads(c['messages'][1]['content'].split('\n')[0])
            payload.pop('event_index', None)
            payload.pop('derived_registry', None)
            clean.append(payload)
        assert clean[0] == clean[1] == clean[2]
