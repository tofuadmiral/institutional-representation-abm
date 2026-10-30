"""Reasoning-only timeout recovery; never repair or replace a received action.

New prospective eligibility ONLY. Raw partial response, unsafe verdict and its
certified charge/full uncertain reservation remain immutable. This does not
make the failed response a scientific action; it permits one bounded next POST.
"""
from decimal import Decimal
import math

from paper3 import retrospective_graceful_recovery as original
from paper3 import retrospective_receipt_recovery_v1 as billing
from paper3 import retrospective_deepinfra_classifier_v1 as classifier
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_serialization_contract as grammar

VERSION = "reasoning-only-no-action-timeout-recovery-v1"


def frames(trace):
    """Strictly parse the existing partial SSE, without adding a DONE marker."""
    pending = []
    for line in [*trace['lines'], '']:
        original.require(type(line) is str, 'string SSE line')
        if line == '':
            if pending:
                raw = '\n'.join(pending)
                pending = []
                original.require(raw != '[DONE]', 'completed stream is not retryable')
                yield grammar._object(raw)
        elif line.startswith('data:'):
            pending.append(line[5:].lstrip(' '))
        else:
            original.require(line.startswith(':'), 'unknown SSE field')


def eligibility(row):
    prior = original.overload(row)
    if prior['eligible']:
        return prior  # Preserve exactly the existing zero-output policy.
    rejected = dict(prior, reason='not_verified_reasoning_only_timeout')
    try:
        s, a = row['stream'], row['assessment']
        expected = route.request(dict(tool_choice='auto', tools=[{}]), 0)
        request = row['request']
        original.require(row['status'] == 'recorded' and not row.get('instrument_error')
            and s['http_status'] == 200 and s['error_type'] == 'TimeoutError'
            and s.get('secret_redacted') is False
            and not s.get('error_body_redacted', False)
            and not s.get('http_error_body') and s['http_error_body_truncated'] is False,
            'only known unredacted HTTP200 read timeout')
        original.require(request['model'] == route.MODEL
            and request['provider'] == expected['provider']
            and request['reasoning'] == expected['reasoning'] and request['stream'] is True,
            'same exact model provider reasoning route')
        reassessed = billing.assess(row, classifier.CONFIG)
        original.require(a == reassessed, 'unaltered native/billing assessment')
        summary = a['stream']
        original.require(not summary['complete'] and summary['done_markers'] == 0
            and summary['finish_reasons'] == [] and summary['usage'] is None
            and summary['error_frames'] == summary['malformed_frames']
                == summary['frames_after_done'] == 0
            and summary['frame_count'] > 0
            and summary['reasoning_channel_characters'] > 0
            and len(summary['ids']) == 1 and summary['generation_id'] == summary['ids'][0]
            and len(summary['models']) == 1 and summary['models'][0] in classifier.CONFIG['models']
            and summary['providers'] == [route.PROVIDER], 'known partial native identity')
        allowed = {'stream:stream incomplete or invalid'}
        if not a['receipt_certified']:
            allowed.add('receipt:unavailable, invalid or conflicting')
            original.require(len(row['receipts']) == 4
                and [o['scheduled_offset_seconds'] for o in row['receipts']] == billing.OFFSETS
                and all(billing.benign(o) for o in row['receipts'])
                and Decimal(a['accounted_usd']) >= Decimal(row['reserved_usd']),
                'known absent/transient receipts retain full reservation')
        original.require(set(a['reasons']) == allowed, 'no other instrument/billing failure')
        original.require(Decimal(a['accounted_usd']) >= 0
            and Decimal(a['accounted_usd']) <= Decimal(row['reserved_usd']), 'finite bounded cost')
        original.require(row.get('final_content') is None
            and row['result']['status'] == 'unsafe_failed'
            and row['result']['action'] is None and row['result']['execution'] is None,
            'no accepted/complete action may be regenerated')
        count = 0
        for frame in frames(s):
            original.require(not frame.get('error') and frame.get('usage') is None
                and not any(k in frame for k in ('output', 'message', 'tool_calls', 'function_call')),
                'no hidden action or usage frame')
            choices = frame.get('choices', [])
            original.require(type(choices) is list and len(choices) <= 1, 'single choice')
            for choice in choices:
                original.require(type(choice) is dict and choice.get('index') == 0
                    and type(choice.get('index')) is int
                    and choice.get('finish_reason') is None and 'message' not in choice,
                    'unfinished single delta choice')
                delta = choice.get('delta')
                original.require(type(delta) is dict
                    and set(delta) <= {'role', 'content', 'reasoning', 'reasoning_details'}
                    and delta.get('role') in (None, 'assistant')
                    and delta.get('content') in (None, ''),
                    'no text/tool/refusal/unknown action channel, even fragments')
            count += 1
        original.require(count == summary['frame_count'], 'all SSE frames inspected')
        for value in (row['ended_unix'], row['admitted_unix']):
            original.require(type(value) in (int, float) and math.isfinite(value), 'finite retry timing')
    except (ValueError, KeyError, TypeError, ArithmeticError):
        return rejected
    return dict(prior, eligible=True, reason=VERSION,
        delay=original.prior.retry_after_seconds(s),
        full_failed_reservation_retained=not a['receipt_certified'],
        certified_actual_charge_preserved=a['receipt_certified'],
        failed_record_and_charge_unchanged=True, received_action=False)


class DurableResponses(original.DurableResponses):
    # All persistence, no-double-send, attempt/cooldown/cap checks are EXACT
    # original code objects. Only the prospective failed-attempt predicate differs.
    _respond = billing.bind(original.DurableResponses._respond, overload=eligibility)
