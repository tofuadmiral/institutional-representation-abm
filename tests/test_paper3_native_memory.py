import json

from experiments.paper3_native_memory_pilot import CollectiveBackend, event_index
from paper3.grounded_interface import GroundedInterface
from paper3.commitment_memory import RULES, profile, ask


def test_event_index_copies_facts_not_derived_status_or_prose():
    events = [dict(type='draft_offer', offer_id='draft-1', package=2, first='B', message='a claim'),
              dict(type='ratification', offer_id='final-2', signatures=[True, False])]
    index = event_index(events)
    assert 'message' not in index[0]
    assert all('status' not in e for e in index)
    assert index[1]['signatures'] == [True, False]
    index[1]['signatures'][0] = False
    assert events[1]['signatures'][0] is True


class RecordedTestDouble:
    """Unit-test fixture only; never written to experimental artifacts."""
    def call(self, messages, seed):
        self.messages, self.seed = messages, seed
        return 'test-key', dict(response=dict(choices=[dict(finish_reason='stop',
            message=dict(content='[THINK]unit fixture[/THINK]{"vote":false}'))]))


def test_collective_wrapper_preserves_action_and_uses_reasoning():
    native = RecordedTestDouble()
    direct = CollectiveBackend(native)
    direct.begin(62500, 'event_index')
    grounded = GroundedInterface(direct)
    assert ask(grounded, profile(503), 3, [], 'Cast your vote. Return {"vote":true}.', {'vote': bool}) == {'vote': False}
    assert native.seed == 62500
    assert direct.call_keys == ['test-key']
    assert 'acting exclusively for principal 3' in native.messages[0]['content']
    assert 'You may reason internally; output JSON only.' not in native.messages[0]['content']
    assert '# HOW YOU SHOULD THINK AND ANSWER' in native.messages[0]['content']
    record, task = native.messages[1]['content'].split('\n', 1)
    assert json.loads(record)['event_index'] == []
    assert '{"vote":true}' not in task
    assert 'vote (boolean: true is yes, false is no)' in task
