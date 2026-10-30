"""Four approved transport-only requests; $0.15, no inference retries or restart.

Standalone standard-library instrument and replay. Existing scientific freezes
are never edited. Action content is not scored, repaired or substituted into any
old episode. Receipt observations at 0/20/40/60 seconds are GETs, not inference.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://openrouter.ai/api/v1/chat/completions'
RECEIPT_URL = 'https://openrouter.ai/api/v1/generation'
METADATA_URL = 'https://openrouter.ai/api/v1/models/deepseek/deepseek-v3.2/endpoints'
MODEL = 'deepseek/deepseek-v3.2'
MODELS = (MODEL, MODEL+'-20251201')
PROVIDER = 'AtlasCloud'
PRIOR, CAP = Decimal('5.311062316'), Decimal('0.15')
PRICE_IN, PRICE_OUT = Decimal('0.269'), Decimal('0.4')
OUTPUT_BOUND = 65552
OFFSETS = (0, 20, 40, 60)
OLD_ROOT = 'results/paper3/deepseek_presentation_v1/'
SOURCE_CASES = (
    ('profile-1/calls/d091c6f9f18e3a623af188f87ec4be348614bb2d81f342390d1669293a203fb4.json',
     'b098064a77cca14d55d37f487e828e9035c6fd38f7b20b26392ecd699cb9cf11'),
    ('profile-3/calls/7208851b26cb6ef54a1092d6080cf5d8cfd18116b5ce8aa9e062a603a0d5b839.json',
     'b512905e025a86543489db31eeac203e9dae87c7195efc5b71279c204efc8f32'),
    ('profile-0/calls/978c030fcedd9ca65acf35b6911e42d937cb068903ecc7e89c664e7bb1df5a97.json',
     'cc4ccef96aa638fb08fe4dacb7fb19a08139d97fba366e85b7655a69adc7611d'),
    ('profile-0/calls/194f4e8365257aec357f8a2fd2c2d0fc2e03c60e14e797b7d0a3e030c4e52dcd.json',
     '5aa92880d6be6cb2e945c9c8b05fad1ab227359915dd4ccd8a9849dcf0d90525'),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    staging = path.with_suffix('.partial')
    with staging.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    staging.replace(path)


def encoded(request):
    return json.dumps(request, ensure_ascii=False, separators=(',', ':'))


def cases(code_root=ROOT):
    result = []
    for i, (relative, expected) in enumerate(SOURCE_CASES):
        source = Path(code_root)/OLD_ROOT/relative
        require(sha(source.read_bytes()) == expected, 'source call changed')
        row = load(source)
        request = json.loads(row['request_text'])  # Preserve original wire key order.
        require(request == row['request'] and encoded(request) == row['request_text'], 'source wire mismatch')
        request['seed'] = 315000+i
        wire = encoded(request)
        bound = len(wire.encode())+1024
        reserve = (bound*PRICE_IN+OUTPUT_BOUND*PRICE_OUT)/Decimal(1000000)
        require(bound <= 65536, 'input too large')
        require(request['model'] == MODEL and request['max_tokens'] == 65536, 'native model/output changed')
        require(request['reasoning'] == {'enabled': True, 'exclude': False}, 'reasoning changed')
        require(request['stream'] is True, 'streaming required')
        p = request['provider']
        require(p['only'] == p['order'] == ['atlas-cloud/fp8'] and p['allow_fallbacks'] is False,
                'provider/fallback changed')
        require(p['require_parameters'] is True and p['quantizations'] == ['fp8'], 'routing changed')
        require(p['max_price'] == {'prompt': .269, 'completion': .4, 'request': 0}, 'price ceilings changed')
        result.append(dict(index=i, source_call=OLD_ROOT+relative, source_sha256=expected,
            old_decision_id=row['decision_id'], seed=315000+i, request_text=wire,
            request_sha256=sha(wire.encode()), input_token_bound=bound, reserved_usd=str(reserve)))
    require(sum(Decimal(c['reserved_usd']) for c in result) <= CAP, 'allocation exceeds cap')
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def opener():
    return urllib.request.build_opener(NoRedirect())


def seed_check(root=ROOT):
    planned = set(range(315000, 315004))
    observed, manifests, calls_seen, declared_strings = set(), [], [], set()
    def walk(value, key=''):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, k)
        elif isinstance(value, list):
            for item in value:
                walk(item, key)
        elif type(value) is int and 'seed' in key.lower():
            observed.add(value)
        elif isinstance(value, str) and 'seed' in key.lower():
            declared_strings.add(value)
    for directory in sorted((Path(root)/'results/paper3').iterdir()):
        if not directory.is_dir() or any(x in directory.name for x in ('portable', 'bundle', 'export')):
            continue
        for base, folders, files in os.walk(directory):
            folders[:] = [n for n in folders if n not in ('code', '__pycache__')]
            for name in files:
                p = Path(base)/name
                if name == 'manifest.json':
                    walk(load(p)); manifests.append((str(p.relative_to(root)), sha(p.read_bytes())))
                elif p.parent.name == 'calls' and p.suffix == '.json':
                    row = load(p)
                    walk(row.get('request', {})); calls_seen.append((str(p.relative_to(root)), sha(p.read_bytes())))
    # Include reserved but never executed institutional positions in every recent
    # prescribed schedule, not merely seed literals appearing in existing calls.
    expanded = {281000+1000*i+j for i in range(12) for j in range(25)}
    expanded |= {301000+1000*i+100*p+j for i in range(2) for p in range(2) for j in range(25)}
    expanded |= {311000+1000*i+j for i in range(4) for j in range(25)}
    expanded |= set(range(310000, 310008))
    overlap = sorted(planned & (observed | expanded))
    require(not overlap, 'seed overlap; do not silently choose replacements')
    return dict(planned=sorted(planned), overlaps=overlap, manifests=manifests,
        call_count=len(calls_seen), call_inventory_sha256=sha(canonical(calls_seen).encode()),
        expanded_recent_schedules=sorted(expanded), declared_seed_strings=sorted(declared_strings))


def check_metadata(metadata):
    data = metadata['data']
    require(data['id'] == MODEL, 'metadata alias mismatch')
    selected = [e for e in data['endpoints'] if e.get('tag') == 'atlas-cloud/fp8']
    require(len(selected) == 1, 'provider metadata ambiguous/missing')
    e = selected[0]
    require(e['provider_name'] == PROVIDER and e['model_id'] == MODEL and e['quantization'] == 'fp8',
            'metadata routing mismatch')
    require(e['name'].split(' | ')[-1] == MODELS[1], 'canonical identity changed')
    require(e['status'] == 0 and e['max_completion_tokens'] >= 65536, 'endpoint unavailable/inadequate')
    required = {'reasoning', 'max_tokens', 'temperature', 'top_p', 'top_k', 'min_p', 'seed',
                'presence_penalty', 'repetition_penalty'}
    require(required <= set(e['supported_parameters']), 'native parameters unsupported')
    for key, maximum in [('prompt', PRICE_IN), ('completion', PRICE_OUT)]:
        price = Decimal(e['pricing'][key])*1000000
        require(price.is_finite() and 0 <= price <= maximum, 'endpoint price exceeds ceiling')
    return e


def prepare(root):
    root = Path(root)
    require(not root.exists(), 'new directory required; no prepare overwrite')
    selected = cases()
    seeds = seed_check()
    with opener().open(METADATA_URL, timeout=20) as response:
        metadata = json.load(response)
    check_metadata(metadata)
    protocol = dict(name='deepseek-transport-diagnostic-v1', intended_calls=4, max_attempts=4,
        prior_usd=str(PRIOR), cap_usd=str(CAP), cumulative_cap_usd=str(PRIOR+CAP),
        workers=4, cases=selected, allowed_models=list(MODELS), provider=PROVIDER,
        receipt_offsets_seconds=list(OFFSETS), receipt_timeout_seconds=10,
        stream_socket_timeout_seconds=900, endpoint_metadata=metadata,
        metadata_observed_unix=time.time(), seed_check=seeds,
        scope='Transport/accounting only. No action-quality selection, new comprehension gate, '
              'inference retry, case replacement, old-episode completion or automatic successor. '
              'All four technical passes are not a population reliability estimate or scientific result.')
    paths = [Path(__file__).resolve(), ROOT/'tests/test_paper3_transport_diagnostic.py']
    paths += [ROOT/c['source_call'] for c in selected]
    snapshot = {str(p.relative_to(ROOT)): p.read_text() for p in paths}
    manifest = dict(protocol=protocol, sources={p: sha(v.encode()) for p, v in snapshot.items()})
    root.mkdir(parents=True, exist_ok=False)
    (root/'calls').mkdir(); (root/'sessions').mkdir()
    save(root/'manifest.json', manifest); save(root/'sources.json', snapshot)
    return sha(canonical(manifest).encode())


def verify_freeze(root, code_root=ROOT):
    root = Path(root); m = load(root/'manifest.json'); snapshot = load(root/'sources.json')
    expected_sources = {'experiments/paper3_transport_diagnostic.py',
                        'tests/test_paper3_transport_diagnostic.py'}
    expected_sources |= {OLD_ROOT+p for p, _ in SOURCE_CASES}
    require(set(m['sources']) == set(snapshot) == expected_sources, 'snapshot inventory mismatch')
    for relative, expected in m['sources'].items():
        p = Path(code_root)/relative
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'unsafe source path')
        require(sha(p.read_bytes()) == sha(snapshot[relative].encode()) == expected, 'frozen source changed')
    p = m['protocol']
    require(p['cases'] == cases(code_root), 'frozen requests changed')
    require(p['intended_calls'] == p['max_attempts'] == p['workers'] == 4, 'call allocation changed')
    require(p['prior_usd'] == str(PRIOR) and p['cap_usd'] == str(CAP), 'budget changed')
    require(p['cumulative_cap_usd'] == str(PRIOR+CAP), 'cumulative ceiling changed')
    require(p['allowed_models'] == list(MODELS) and p['provider'] == PROVIDER, 'identity rule changed')
    require(p['receipt_offsets_seconds'] == list(OFFSETS) and p['receipt_timeout_seconds'] == 10,
            'receipt schedule changed')
    require(p['stream_socket_timeout_seconds'] == 900, 'stream timeout changed')
    require(p['seed_check']['planned'] == list(range(315000,315004)) and not p['seed_check']['overlaps'],
            'seed check missing/failed')
    check_metadata(p['endpoint_metadata'])
    return m, sha(canonical(m).encode())


def redact(value, secret):
    text = json.dumps(value, ensure_ascii=False)
    hit = bool(secret and secret in text)
    if hit:
        text = text.replace(secret, '[REDACTED_CREDENTIAL]')
    text, generic = re.subn(r'sk-or-v1-[A-Za-z0-9_-]{24,}', '[REDACTED_CREDENTIAL]', text)
    return json.loads(text), hit or bool(generic)


def transmit(wire, secret):
    start = time.time()
    out = dict(started_unix=start, http_status=None, generation_header=None, lines=[],
               byte_count=0, first_line_unix=None, last_line_unix=None, error_type=None)
    req = urllib.request.Request(URL, data=wire.encode(), method='POST',
        headers={'Authorization': 'Bearer '+secret, 'Content-Type': 'application/json'})
    try:
        with opener().open(req, timeout=900) as response:
            out.update(http_status=response.status, headers_unix=time.time(),
                       generation_header=response.headers.get('X-Generation-Id'))
            for raw in response:
                now = time.time()
                if out['first_line_unix'] is None: out['first_line_unix'] = now
                out['last_line_unix'] = now
                out['byte_count'] += len(raw)
                out['lines'].append(raw.decode('utf-8', errors='replace').rstrip('\r\n'))
    except urllib.error.HTTPError as exc:
        out.update(http_status=exc.code, error_type='HTTPError')
    except Exception as exc:
        out['error_type'] = type(exc).__name__  # No unsafe exception text/headers.
    out.update(ended_unix=time.time(), line_count=len(out['lines']))
    out, hit = redact(out, secret); out['secret_redacted'] = hit
    return out


def receipt_lookup(generation_id, secret):
    out = dict(started_unix=time.time(), http_status=None, error_type=None, data=None)
    req = urllib.request.Request(RECEIPT_URL+'?'+urllib.parse.urlencode({'id': generation_id}),
        method='GET', headers={'Authorization': 'Bearer '+secret})
    try:
        with opener().open(req, timeout=10) as response:
            out['http_status'] = response.status
            out['data'] = json.load(response).get('data')
    except urllib.error.HTTPError as exc:
        out.update(http_status=exc.code, error_type='HTTPError')
    except Exception as exc:
        out['error_type'] = type(exc).__name__
    out['ended_unix'] = time.time()
    out, hit = redact(out, secret); out['secret_redacted'] = hit
    return out


def stream_summary(trace):
    frames, pending = [], []
    for line in [*trace['lines'], '']:
        if not line:
            if pending: frames.append('\n'.join(pending)); pending = []
        elif line.startswith('data:'):
            pending.append(line[5:].lstrip(' '))
    ids, models, providers, finishes = set(), set(), set(), set()
    done = malformed = errors = after_done = 0
    usage = None; choices_valid = True
    for value in frames:
        if value == '[DONE]': done += 1; continue
        if done: after_done += 1
        try:
            data = json.loads(value)
            if not isinstance(data, dict): raise ValueError('nonobject')
            for key, bucket in [('id',ids), ('model',models), ('provider',providers)]:
                if key in data: bucket.add(str(data[key]))
            if data.get('error'): errors += 1
            if data.get('usage') is not None:
                if usage is not None and usage != data['usage']: errors += 1
                usage = data['usage']
            for choice in data.get('choices') or []:
                choices_valid &= choice.get('index') == 0
                if choice.get('finish_reason'): finishes.add(choice['finish_reason'])
        except (ValueError, TypeError, AttributeError):
            malformed += 1
    header = trace.get('generation_header')
    if header: ids.add(header)
    identity = len(ids) == 1 and len(models) == 1 and models <= set(MODELS) and providers == {PROVIDER}
    complete = (trace['http_status'] == 200 and not trace.get('error_type')
        and not trace.get('secret_redacted') and identity and choices_valid and done == 1
        and len(finishes) == 1 and 'error' not in finishes and not (malformed or errors or after_done)
        and isinstance(usage, dict))
    return dict(generation_id=next(iter(ids)) if len(ids) == 1 else None, ids=sorted(ids),
        models=sorted(models), providers=sorted(providers), finish_reasons=sorted(finishes),
        frame_count=len(frames), done_markers=done, malformed_frames=malformed, error_frames=errors,
        frames_after_done=after_done, complete=complete, usage=usage)


def finite_cost(value, reserve):
    amount = Decimal(str(value))
    require(amount.is_finite() and 0 <= amount <= Decimal(reserve), 'invalid/out-of-bound cost')
    return amount


def receipt_cost(observation, generation_id, reserve):
    require(observation.get('http_status') == 200 and not observation.get('error_type')
            and not observation.get('secret_redacted'), 'receipt transport failed')
    data = observation['data']
    require(isinstance(data, dict) and data.get('id') == generation_id, 'receipt id mismatch')
    require(data.get('model') in MODELS and data.get('provider_name') == PROVIDER, 'receipt identity mismatch')
    return finite_cost(data['total_cost'], reserve)


def assess(row):
    s = stream_summary(row['stream']); reasons = []; receipt_amounts = []; invalid_receipt = False
    reserve = Decimal(row['reserved_usd'])
    stream_cost = None
    try:
        require(s['complete'], 'stream incomplete or invalid')
        u = s['usage']
        require(type(u['prompt_tokens']) is int and 0 < u['prompt_tokens'] <= row['input_token_bound'],
                'prompt accounting invalid')
        require(type(u['completion_tokens']) is int and 0 < u['completion_tokens'] <= OUTPUT_BOUND,
                'completion accounting invalid')
        stream_cost = finite_cost(u['cost'], reserve)
    except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
        reasons.append('stream:'+str(exc))
    for observation in row['receipts']:
        try: receipt_amounts.append(receipt_cost(observation,s['generation_id'],reserve))
        except (ValueError, TypeError, KeyError, InvalidOperation):
            # A later receipt with a changed identity/cost cannot be ignored in
            # favor of an earlier convenient one. A 404 is absence, not conflict.
            invalid_receipt |= observation.get('http_status') == 200
    receipts_consistent = bool(receipt_amounts) and len(set(receipt_amounts)) == 1 and not invalid_receipt
    if not receipts_consistent: reasons.append('receipt:unavailable, invalid or conflicting')
    receipt_amount = receipt_amounts[0] if receipts_consistent else None
    if stream_cost is not None and receipt_amount is not None and stream_cost != receipt_amount:
        reasons.append('stream/receipt charge mismatch')
    # A valid receipt can certify the charge of an incomplete stream; that does
    # NOT make the technical diagnostic pass or authorize an inference reissue.
    certified = receipt_amount if receipts_consistent else None
    if stream_cost is not None and certified is not None and stream_cost != certified: certified = None
    accounted = certified if certified is not None else reserve
    # Never hide a finite reported charge above the conservative reservation.
    for value in [s.get('usage') or {}, *(r.get('data') or {} for r in row['receipts'])]:
        if not isinstance(value, dict): continue
        try:
            amount = Decimal(str(value.get('cost',value.get('total_cost'))))
            if amount.is_finite() and amount > accounted: accounted = amount
        except (InvalidOperation, TypeError, ValueError): pass
    return dict(stream=s, receipt_certified=certified is not None,
        certified_cost_usd=str(certified) if certified is not None else None,
        accounted_usd=str(accounted), reasons=reasons, passed=not reasons,
        length_ending=s['finish_reasons'] == ['length'],
        telemetry={k:row['stream'].get(k) for k in ('started_unix','headers_unix','first_line_unix',
                   'last_line_unix','ended_unix','line_count','byte_count','http_status','error_type')})


def read_key():
    path = ROOT/'.env.local'
    require(path.stat().st_mode & 0o077 == 0, 'key file must be owner-only')
    values = [v.split('=',1)[1].strip().strip('\"\'') for v in path.read_text().splitlines()
              if v.strip().startswith('OPENROUTER_API_KEY=')]
    require(len(values) == 1 and values[0] and not any(c.isspace() for c in values[0]), 'invalid key file')
    return values[0]


def execute(root, secret, transport=transmit, lookup=receipt_lookup, clock=time.time, sleep=time.sleep):
    root = Path(root); m, protocol = verify_freeze(root)
    require(0 <= time.time()-m['protocol']['metadata_observed_unix'] <= 3600, 'stale metadata; do not launch')
    with (root/'writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not list((root/'calls').iterdir()) and not list((root/'sessions').iterdir()), 'execution exists; never restart')
        save(root/'sessions/start.json',dict(protocol=protocol,started_unix=clock()))
        guard = threading.Lock(); stop = threading.Event(); admitted = []
        def one(case):
            i = case['index']
            with guard:
                if stop.is_set(): return dict(index=i,status='not_started')
                existing = [load(p) for p in (root/'calls').glob('*.json')]
                total = sum(Decimal(r.get('assessment',{}).get('accounted_usd',r['reserved_usd'])) for r in existing)
                reserve = Decimal(case['reserved_usd'])
                require(len(existing) < 4 and total+reserve <= CAP and PRIOR+total+reserve <= 10, 'admission budget exceeded')
                row = dict(case,protocol=protocol,status='started',attempt=1,admitted_unix=clock())
                save(root/f'calls/{i}.json',row); admitted.append(i)
            try:
                row['stream'] = transport(case['request_text'], secret)
                row['stream'], hit = redact(row['stream'],secret)
                row['stream']['secret_redacted'] = hit or row['stream'].get('secret_redacted',False)
                row.update(status='stream_ended',receipts=[])
                save(root/f'calls/{i}.json',row)
                summary = stream_summary(row['stream'])
                if not summary['complete']: stop.set()
                if summary['generation_id']:
                    for offset in OFFSETS:
                        sleep(max(0,row['stream']['ended_unix']+offset-clock()))
                        observation = lookup(summary['generation_id'], secret)
                        observation, hit = redact(observation,secret)
                        observation['secret_redacted'] = hit or observation.get('secret_redacted',False)
                        observation['scheduled_offset_seconds'] = offset
                        row['receipts'].append(observation)
                        save(root/f'calls/{i}.json',row)
                row['assessment'] = assess(row)
                row.update(status='recorded',ended_unix=clock())
                if not row['assessment']['passed']: stop.set()
                save(root/f'calls/{i}.json',row)
                return dict(index=i,status='recorded',passed=row['assessment']['passed'])
            except Exception as exc:
                # An unexpected instrument failure cannot trigger another request.
                row.pop('assessment', None)
                stop.set(); row.update(status='instrument_error',error_type=type(exc).__name__,ended_unix=clock())
                save(root/f'calls/{i}.json',row)
                return dict(index=i,status='instrument_error')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(one,m['protocol']['cases']))
        rows = [load(p) for p in (root/'calls').glob('*.json')]
        cost = sum((Decimal(r.get('assessment',{}).get('accounted_usd',r['reserved_usd'])) for r in rows),Decimal(0))
        terminal = dict(protocol=protocol,admitted_indices=sorted(admitted),results=results,
            stopped=stop.is_set(),accounted_usd=str(cost),cumulative_usd=str(PRIOR+cost),ended_unix=clock())
        save(root/'sessions/terminal.json',terminal)
        return terminal


def audit(root, code_root=ROOT):
    root = Path(root); m, protocol = verify_freeze(root,code_root)
    terminal = load(root/'sessions/terminal.json'); start = load(root/'sessions/start.json')
    require(start['protocol'] == terminal['protocol'] == protocol, 'protocol mismatch')
    require(not list(root.rglob('*.partial')), 'partial writes remain')
    require({p.name for p in (root/'sessions').iterdir()} == {'start.json','terminal.json'},
            'unexpected session files')
    require(all(p.is_file() and not p.is_symlink() and re.fullmatch('[0-3]\\.json',p.name)
                for p in (root/'calls').iterdir()), 'unexpected call files')
    rows = {int(p.stem):load(p) for p in (root/'calls').glob('*.json')}
    require(sorted(rows) == terminal['admitted_indices'] and set(rows) <= set(range(4)), 'admission inventory changed')
    results = {r['index']:r for r in terminal['results']}
    require(set(results) == set(range(4)) and len(terminal['results']) == 4, 'assigned inventory changed')
    reports = []; cost = Decimal(0)
    for case in m['protocol']['cases']:
        i = case['index']
        if i not in rows:
            require(results[i]['status']=='not_started','missing admitted call')
            reports.append(dict(index=i,status='not_started')); continue
        row = rows[i]
        require(all(row[k] == v for k,v in case.items()) and row['protocol'] == protocol and row['attempt'] == 1,
                'request/provenance changed')
        require(row['status'] in ('recorded','instrument_error'),'unterminated request')
        require(start['started_unix'] <= row['admitted_unix'] <= row['ended_unix'] <= terminal['ended_unix'],
                'worker chronology invalid')
        if row['status'] == 'recorded':
            trace = row['stream']
            require(row['admitted_unix'] <= trace['started_unix'] <= trace['ended_unix'] <= row['ended_unix'],
                    'stream chronology invalid')
            require(trace['line_count'] == len(trace['lines']) and trace['byte_count'] >= 0,
                    'stream telemetry invalid')
            assessment = assess(row)
            require(assessment == row['assessment'], 'assessment replay mismatch')
            require(results[i] == dict(index=i,status='recorded',passed=assessment['passed']), 'worker result mismatch')
            observations = row['receipts']; summary = assessment['stream']
            require(len(observations) == (4 if summary['generation_id'] else 0), 'receipt count changed')
            for offset, obs in zip(OFFSETS,observations):
                require(obs['scheduled_offset_seconds'] == offset, 'receipt schedule changed')
                require(obs['started_unix'] >= row['stream']['ended_unix']+offset-.01, 'receipt too early')
                require(obs['ended_unix'] >= obs['started_unix'], 'receipt timing invalid')
                require(obs['ended_unix'] <= row['ended_unix'], 'receipt after worker ended')
            cost += Decimal(assessment['accounted_usd'])
            reports.append(dict(index=i,status='recorded',**assessment))
        else:
            require(results[i]['status']=='instrument_error','instrument error inventory mismatch')
            cost += Decimal(row['reserved_usd']); reports.append(dict(index=i,status='instrument_error'))
    require(str(cost) == terminal['accounted_usd'] and str(PRIOR+cost) == terminal['cumulative_usd'], 'cost mismatch')
    require(cost <= CAP and PRIOR+cost <= 10, 'budget exceeded')
    passed = len(rows) == 4 and all(r.get('passed',False) for r in reports)
    require(terminal['stopped'] == (not passed), 'terminal stop mismatch')
    return dict(protocol=protocol,calls=len(rows),assigned=4,cases=reports,all_four_passed=passed,
        accounted_usd=str(cost),cumulative_usd=str(PRIOR+cost),integrity_errors=[],
        scope='Transport-only diagnostic, not institution performance, population reliability or permission for a successor.')


def archive(root, destination, secret=None):
    root, destination = Path(root), Path(destination)
    report = audit(root)
    require(not destination.exists(), 'archive exists; never overwrite')
    source = load(root/'sources.json')
    require(not any(p.is_symlink() for p in root.rglob('*')), 'symlink in run')
    content = {'code/'+k:v.encode() for k,v in source.items()}
    content.update({'run/'+str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.json')})
    content['audit.json'] = json.dumps(report,indent=2).encode()
    inventory = {k:sha(v) for k,v in content.items()}
    content['bundle.json'] = json.dumps(dict(protocol=report['protocol'],files=inventory),indent=2).encode()
    for key,value in content.items():
        require(not Path(key).is_absolute() and '..' not in Path(key).parts, 'unsafe archive path')
        require(not (secret and secret.encode() in value), 'credential found; archive refused')
        require(not re.search(rb'sk-or-v1-[A-Za-z0-9_-]{24,}',value), 'possible credential in archive')
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for k,v in sorted(content.items()): z.writestr(k,v)
    return dict(path=str(destination),sha256=sha(destination.read_bytes()),files=len(inventory))


def replay(bundle, expected_protocol):
    """Verify every extracted payload, then reproduce the frozen audit offline."""
    bundle = Path(bundle)
    metadata = load(bundle/'bundle.json')
    require(metadata['protocol'] == expected_protocol, 'unexpected protocol')
    actual = set()
    for p in bundle.rglob('*'):
        require(not p.is_symlink(), 'symlink in bundle')
        if p.is_file(): actual.add(str(p.relative_to(bundle)))
    require(actual == set(metadata['files']) | {'bundle.json'}, 'bundle inventory mismatch')
    for relative, expected in metadata['files'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts and '\\' not in relative,
                'unsafe bundle path')
        require(sha((bundle/relative).read_bytes()) == expected, 'bundle hash mismatch')
    report = audit(bundle/'run', bundle/'code')
    require(report['protocol'] == expected_protocol and report == load(bundle/'audit.json'),
            'archived audit replay mismatch')
    return report


def offline_guard(event, args):
    if event.startswith(('socket.', 'subprocess.', 'os.system', 'os.exec', 'os.spawn')):
        raise RuntimeError('network/processes forbidden in offline audit')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true')
    group.add_argument('--run',action='store_true')
    group.add_argument('--audit',action='store_true')
    group.add_argument('--archive',type=Path)
    group.add_argument('--replay',action='store_true')
    parser.add_argument('--expected-protocol')
    args = parser.parse_args()
    if args.audit or args.replay: sys.addaudithook(offline_guard)
    if args.run or args.replay:
        require(args.expected_protocol, 'explicit expected protocol required')
    if args.expected_protocol and not args.replay:
        require(verify_freeze(args.root)[1] == args.expected_protocol, 'unexpected protocol')
    if args.prepare: result = dict(protocol=prepare(args.root))
    elif args.run: result = execute(args.root,read_key())
    elif args.audit: result = audit(args.root)
    elif args.replay: result = replay(args.root,args.expected_protocol)
    else: result = archive(args.root,args.archive,read_key())
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
