"""Post-freeze reporting correction; never edits the frozen experiment/auditor.

The frozen audit entry point crashes on response.usage=None when summarizing a
transport failure. This module retains its integrity/session/coordinator checks
and all scientific readouts verbatim, replacing only resource-use aggregation.
Unknown usage is counted explicitly rather than silently interpreted as zero.
"""
from __future__ import annotations
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path

from analysis import paper3_disclosure_identification_audit as frozen

run = frozen.run
require = frozen.require
sources = frozen.sources
verify_shard = frozen.verify_shard
profile_readout = frozen.profile_readout
digest = frozen.digest


def usage_summary(rows):
    fields = ('prompt_tokens', 'completion_tokens', 'reasoning_tokens')
    known = {k: 0 for k in fields}
    missing = {k: 0 for k in fields}
    for row in rows:
        response = row.get('response')
        usage = response.get('usage') if isinstance(response, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        details = usage.get('completion_tokens_details')
        details = details if isinstance(details, dict) else {}
        values = dict(prompt_tokens=usage.get('prompt_tokens'),
                      completion_tokens=usage.get('completion_tokens'),
                      reasoning_tokens=details.get('reasoning_tokens'))
        for field, value in values.items():
            if type(value) is int and value >= 0:
                known[field] += value
            else:
                missing[field] += 1
    return dict(known_token_totals=known, attempts_with_unknown_tokens=missing,
                outcomes=dict(Counter(r.get('outcome','uncertified') for r in rows)),
                scope='Observed integer usage only; missing/invalid fields are unknown, not zero. Costs include charges or conservative reservations independently.')


def audit(root):
    root=Path(root);errors=[];shards={}
    try: sources(root,'coordinator')
    except (ValueError,KeyError,TypeError,OSError) as exc:errors.append('coordinator: '+str(exc))
    for index in [None]+list(range(run.SHARDS)):
        name='gate' if index is None else f'profile-{index}'
        try: shards[name]=verify_shard(root/name,index)
        except (ValueError,KeyError,TypeError,IndexError,OSError,ArithmeticError) as exc:
            errors.append(name+': '+str(exc))
    rows=run.all_rows(root)
    cost=sum((run.row_cost(r) for r in rows),Decimal(0))
    if cost>run.CAP or run.PRIOR+cost>run.AUTHORIZED or len(rows)>run.MAX_CALLS:
        errors.append('aggregate budget exceeded')
    profiles=[profile_readout(root,i) for i in range(run.SHARDS)]
    try:
        terminal=run.load(root/'sessions/terminal.json')
        start=run.load(root/'sessions/execution_started.json')
        ph=digest(run.load(root/'manifest.json'))
        require(start['protocol_hash']==terminal['protocol_hash']==ph,'coordinator protocol mismatch')
        require(start['preflight_hash']==digest(run.load(root/'network_preflight.json')),'preflight changed')
        require(Decimal(terminal['accounted_usd'])==cost,'coordinator cost mismatch')
        launched=terminal['launched_indices']
        require(launched==list(range(len(launched))) and len(launched)<=run.SHARDS,'launch order mismatch')
        require(terminal['not_started_indices']==list(range(len(launched),run.SHARDS)),'unstarted inventory mismatch')
        require(set(terminal['workers'])=={str(i) for i in launched},'worker inventory mismatch')
        known={'terminal','execution_started'}
        gate=run.load(root/'gate/sessions/terminal.json')
        require(gate['passed']==terminal['gate_passed'],'coordinator gate mismatch')
        require(gate['passed'] or not launched,'episodes ran after gate failed')
        for i in launched:
            require(run.load(root/f'sessions/launch-{i}.json')['index']==i,'launch index mismatch')
            require(run.load(root/f'sessions/worker-{i}.json')==terminal['workers'][str(i)],'worker record mismatch')
            known.update({f'launch-{i}',f'worker-{i}'})
        require({p.stem for p in (root/'sessions').glob('*.json')}==known,'coordinator session inventory mismatch')
        require({p.name for p in root.glob('profile-*') if p.is_dir()}=={f'profile-{i}' for i in range(run.SHARDS)},
                'profile directory inventory mismatch')
    except (ValueError,KeyError,TypeError,OSError) as exc:errors.append('coordinator terminal: '+str(exc))
    return dict(integrity_errors=errors,shards=shards,calls=len(rows),accounted_usd=str(cost),
        cumulative_additional_usd=str(run.PRIOR+cost),complete_profiles=sum(p['complete'] for p in profiles),
        complete_blocks=sum(p['complete'] for p in profiles),base_profiles=2,
        usage=usage_summary(rows),
        reporting_correction='Post-freeze null-usage reporting fix. Frozen sources, record/session replay, outcomes, assignments and accounting unchanged. Missing usage is not zero.',
        profiles=profiles,scope=run.design.frame()['inference_scope'],
        limitations='Matching local source replay, not portable reproduction or provider-internal verification. '
        'Admission-failure reasons replay from saved unsubmitted requests; aggregate final costs checked. '
        'Shared budget safety is enforced atomically by the runner, not inferred from final completion timestamps.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    report=audit(parser.parse_args().root)
    print(json.dumps(report,indent=2))
    raise SystemExit(bool(report['integrity_errors']))
