from collections import defaultdict
from jev_study.bill_choice import make_cases
from jev_study.replication import make_replication, signature
from jev_study.run_replication import wire_request


def test_heldout_design():
    cases = make_replication()
    assert len(cases) == 840
    assert cases == make_replication()
    assert len({c['name'] for c in cases}) == 840
    grouped = defaultdict(dict)
    for c in cases:
        grouped[c['base_seed']][c['arm']] = c
        # Independent elimination oracle: successively discard options that
        # fail the highest remaining priority if any option satisfies it.
        survivors = list(c['policies'])
        for issue in c['priority']:
            satisfying = [k for k in survivors if c['policies'][k][issue] == c['desired'][issue]]
            survivors = satisfying or survivors
        assert survivors == [c['expected']]
    assert len(grouped) == 120
    signatures = {signature(g['plain']) for g in grouped.values()}
    assert len(signatures) == 120
    assert not signatures & {signature(c) for c in make_cases()}
    for group in grouped.values():
        assert len(group) == 7
        assert wire_request(group['plain']) == wire_request(group['plain_repeat'])
        assert wire_request(group['neutral']) == wire_request(group['neutral_repeat'])
        assert len({g['label_to_policy_index'][g['expected']] for g in group.values()}) == 1
