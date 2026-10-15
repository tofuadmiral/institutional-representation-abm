"""Parameterized reasoning-model calls; old frozen instruments remain untouched.

No historical runner is edited. Request construction, source verification and
action scoring are supplied by each separately frozen experiment. One POST per
admission; no fallbacks, content repair, retries or admission after a safety stop.
"""
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.request

from experiments import paper3_transport_diagnostic as t
from experiments.paper3_coalition_contracts import final_content
from paper3.pivot_b_budget import Ledger, atomic


def safe_error_body(raw,secret):
    text=raw.decode("utf-8",errors="replace")
    text,hit=t.redact(text,secret)
    text,count=re.subn(r"(?i)Bearer\s+[^\s\"'<>]+","Bearer [REDACTED]",text)
    text,partial=re.subn(r"sk-or-v1-[A-Za-z0-9_-]*","[REDACTED]",text)

    # Preserve provider diagnostics, not nonessential account identifiers.
    text=re.sub(r'(?i)("(?:user_id|account_id|user|email)"\s*:\s*)"[^"]*"',r'\1"[REDACTED_ACCOUNT]"',text)
    text=re.sub(r'\buser_[A-Za-z0-9_-]+', '[REDACTED_ACCOUNT]',text)
    return text, bool(hit or count or partial)


def transmit(wire,secret):
    out=dict(started_unix=time.time(),http_status=None,generation_header=None,lines=[],
             byte_count=0,first_line_unix=None,last_line_unix=None,error_type=None,
             http_error_body=None,http_error_body_truncated=False,error_body_redacted=False)
    req=urllib.request.Request(t.URL,data=wire.encode(),method="POST",
        headers={"Authorization":"Bearer "+secret,"Content-Type":"application/json"})
    try:
        with t.opener().open(req,timeout=900) as response:
            out.update(http_status=response.status,headers_unix=time.time(),
                       generation_header=response.headers.get("X-Generation-Id"))
            for raw in response:
                now=time.time()
                if out["first_line_unix"] is None:out["first_line_unix"]=now
                out["last_line_unix"]=now;out["byte_count"]+=len(raw)
                out["lines"].append(raw.decode("utf-8",errors="replace").rstrip("\r\n"))
    except urllib.error.HTTPError as exc:
        out.update(http_status=exc.code,error_type="HTTPError")
        try:
            raw=exc.read(4097)
            out["http_error_body"],out["error_body_redacted"]=safe_error_body(raw[:4096],secret)
            out["http_error_body_truncated"]=len(raw)>4096
        except Exception as body_exc:out["http_error_body_read_error"]=type(body_exc).__name__
        finally:exc.close()
    except Exception as exc:out["error_type"]=type(exc).__name__
    out.update(ended_unix=time.time(),line_count=len(out["lines"]))
    out,hit=t.redact(out,secret);out["secret_redacted"]=hit or out["error_body_redacted"]
    return out


require=t.require
def stream_summary(trace, config):
    frames, pending = [], []
    for line in [*trace['lines'], '']:
        if not line:
            if pending: frames.append('\n'.join(pending)); pending = []
        elif line.startswith('data:'):
            pending.append(line[5:].lstrip(' '))
    ids, models, providers, finishes = set(), set(), set(), set()
    done = malformed = errors = after_done = 0
    usage = None; choices_valid = True; channel_characters = 0
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
                delta=choice.get('delta') or {}
                for key in ('reasoning','reasoning_content'):
                    if isinstance(delta.get(key),str): channel_characters+=len(delta[key].strip())
                for detail in delta.get('reasoning_details') or []:
                    if isinstance(detail,dict) and detail.get('type')=='reasoning.text':
                        if isinstance(detail.get('text'),str):channel_characters+=len(detail['text'].strip())
        except (ValueError, TypeError, AttributeError):
            malformed += 1
    header = trace.get('generation_header')
    if header: ids.add(header)
    identity = len(ids) == 1 and len(models) == 1 and models <= set(config['models']) and providers == {config['provider']}
    complete = (trace['http_status'] == 200 and not trace.get('error_type')
        and not trace.get('secret_redacted') and identity and choices_valid and done == 1
        and len(finishes) == 1 and 'error' not in finishes and not (malformed or errors or after_done)
        and isinstance(usage, dict))
    return dict(generation_id=next(iter(ids)) if len(ids) == 1 else None, ids=sorted(ids),
        models=sorted(models), providers=sorted(providers), finish_reasons=sorted(finishes),
        frame_count=len(frames), done_markers=done, malformed_frames=malformed, error_frames=errors,
        frames_after_done=after_done, complete=complete, usage=usage, reasoning_channel_characters=channel_characters)


def finite_cost(value, reserve):
    amount = Decimal(str(value))
    require(amount.is_finite() and 0 <= amount <= Decimal(reserve), 'invalid/out-of-bound cost')
    return amount


def receipt_cost(observation, generation_id, reserve, config):
    require(observation.get('http_status') == 200 and not observation.get('error_type')
            and not observation.get('secret_redacted'), 'receipt transport failed')
    data = observation['data']
    require(isinstance(data, dict) and data.get('id') == generation_id, 'receipt id mismatch')
    require(data.get('model') in config['models'] and data.get('provider_name') == config['provider'], 'receipt identity mismatch')
    return finite_cost(data['total_cost'], reserve)


def assess(row, config):
    s = stream_summary(row['stream'], config); reasons = []; receipt_amounts = []; invalid_receipt = False
    reserve = Decimal(row['reserved_usd'])
    stream_cost = None
    try:
        require(s['complete'], 'stream incomplete or invalid')
        u = s['usage']
        require(type(u['prompt_tokens']) is int and 0 < u['prompt_tokens'] <= row['input_token_bound'],
                'prompt accounting invalid')
        require(type(u['completion_tokens']) is int and 0 < u['completion_tokens'] <= config['output_bound'],
                'completion accounting invalid')
        stream_cost = finite_cost(u['cost'], reserve)
    except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
        reasons.append('stream:'+str(exc))
    for observation in row['receipts']:
        try: receipt_amounts.append(receipt_cost(observation,s['generation_id'],reserve,config))
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


def native_evidence(summary):
    usage=summary.get("usage") or {}
    details=usage.get("completion_tokens_details") or {}
    n=details.get("reasoning_tokens") if isinstance(details,dict) else None
    total=usage.get("completion_tokens")
    valid_count=n is None or (type(n) is int and type(total) is int and 0<=n<=total)
    channel=summary.get("reasoning_channel_characters",0)>0
    return dict(present=valid_count and ((type(n) is int and n>0) or channel),
                reported_tokens=n,nonempty_native_channel=channel)


class Calls:
    def __init__(self,root,ledger_root,stage,max_calls,verify,score,config,secret=None,
                 send=None,lookup=None,clock=time.time,sleep=time.sleep):
        self.root=Path(root);self.ledger=Ledger(ledger_root);self.stage=stage;self.max_calls=max_calls
        self.config=config;self.verify,self.score=verify,score;self.protocol=verify()[1];self.secret=secret
        self.send=send or transmit;self.lookup=lookup or t.receipt_lookup
        self.clock,self.sleep=clock,sleep;self.guard=threading.Lock();self.stop=threading.Event()
        self.transport_failures=0

    def one(self,case):
        key=case["id"];path=self.root/"calls"/(key+".json");reserve=Decimal(case["reserved_usd"])
        with self.guard:
            if self.stop.is_set():return dict(id=key,status="not_started")
            try:
                t.require(self.verify()[1]==self.protocol,"source/protocol changed")
                t.require(len(list((self.root/"calls").glob("*.json")))<self.max_calls,"attempt ceiling")
                t.require(t.canonical(case["request"])==case["request_text"] and t.sha(case["request_text"].encode())==case["request_sha256"],"request hash")
                self.ledger.reserve(self.stage,self.stage+"-"+key,reserve,case["request_sha256"])
                row=dict(**case,protocol=self.protocol,status="admitted",attempt=1,admitted_unix=self.clock())
                atomic(path,row)
            except Exception as exc:
                self.stop.set();return dict(id=key,status="admission_failed",error_type=type(exc).__name__)
        try:
            row["stream"]=self.send(case["request_text"],self.secret)
            row["stream"],hit=t.redact(row["stream"],self.secret)
            row["stream"]["secret_redacted"]=hit or row["stream"].get("secret_redacted",False)
            row.update(status="stream_ended",receipts=[]);atomic(path,row)
            s=stream_summary(row["stream"],self.config)
            if ((s["models"] and not set(s["models"])<=set(self.config["models"])) or
                (s["providers"] and s["providers"]!=[self.config["provider"]]) or len(s["models"])>1 or
                len(s["ids"])>1 or row["stream"]["secret_redacted"]):self.stop.set()
            if s["generation_id"]:
                for offset in (0,20,40,60):
                    self.sleep(max(0,row["stream"]["ended_unix"]+offset-self.clock()))
                    observation=self.lookup(s["generation_id"],self.secret)
                    observation,hit=t.redact(observation,self.secret)
                    observation["secret_redacted"]=hit or observation.get("secret_redacted",False)
                    observation["scheduled_offset_seconds"]=offset
                    row["receipts"].append(observation);atomic(path,row)
                    current=assess(row,self.config)
                    if current["receipt_certified"]:break
                    if observation.get("http_status")==200:self.stop.set();break
            row["assessment"]=assess(row,self.config);row.update(status="recorded",ended_unix=self.clock())
            a=row["assessment"];s=a["stream"]
            row["final_content"]=final_content(row["stream"]) if s["complete"] else None
            row["result"]=self.score(row,case)
            atomic(path,row)
            self.ledger.settle(self.stage+"-"+key,a["accounted_usd"],a["receipt_certified"],t.sha(path.read_bytes()))
            native=native_evidence(s)["present"]
            if Decimal(a["accounted_usd"])>reserve or (s["complete"] and not native) or s["finish_reasons"]==["length"]:self.stop.set()
            if not a["passed"]:
                with self.guard:
                    self.transport_failures+=1
                    if self.transport_failures>=2:self.stop.set()
            print(json.dumps(dict(event="b_call_terminal",id=key,result=row["result"],budget=self.ledger.snapshot())),flush=True)
            return dict(id=key,status="recorded")
        except Exception as exc:
            self.stop.set();row.update(status="instrument_error",instrument_error=type(exc).__name__)
            atomic(path,row);return dict(id=key,status="instrument_error")


def audit_records(root,ledger_root,stage,protocol,cases,terminal,score,config):
    root=Path(root);ledger_root=Path(ledger_root);reports=[];matched=set();cost=Decimal(0)
    t.require(not list(root.rglob("*.partial")),"partial writes remain")
    t.require([r["id"] for r in terminal["results"]]==[c["id"] for c in cases],"assigned inventory")
    for case,status in zip(cases,terminal["results"]):
        key=case["id"];path=root/"calls"/(key+".json");ep=ledger_root/"entries"/(stage+"-"+key+".json")
        if not path.exists():
            t.require(status["status"] in ("not_started","admission_failed"),"missing admitted call")
            if ep.exists():
                e=t.load(ep);matched.add(e["request_id"])
                t.require(e["status"]=="reserved" and e["request_sha256"]==case["request_sha256"] and e["reserved_usd"]==case["reserved_usd"],"orphan reservation")
                cost+=Decimal(e["reserved_usd"])
            reports.append(dict(id=key,status=status["status"],result=None));continue
        row=t.load(path);e=t.load(ep);matched.add(e["request_id"])
        t.require(all(row.get(k)==v for k,v in case.items()) and row["protocol"]==protocol and row["attempt"]==1,"call provenance")
        t.require(row["status"]==status["status"],"terminal call status")
        t.require(e["request_sha256"]==case["request_sha256"] and e["reserved_usd"]==case["reserved_usd"],"ledger request")
        result=score(row,case)
        if not row.get("instrument_error"):
            a=assess(row,config)
            t.require(row["assessment"]==a and row["result"]==result,"assessment/action changed")
            t.require(row["final_content"]==(final_content(row["stream"]) if a["stream"]["complete"] else None),"final changed")
            t.require(e["status"]=="settled" and e["evidence_sha256"]==t.sha(path.read_bytes()),"settlement evidence")
            t.require(e["accounted_usd"]==a["accounted_usd"] and e["certified"]==a["receipt_certified"],"accounting changed")
        cost+=Decimal(e.get("accounted_usd",e["reserved_usd"]))
        reports.append(dict(id=key,status=row["status"],result=result))
    t.require({p.stem for p in (root/"calls").glob("*.json")}<={c["id"] for c in cases},"unexpected calls")
    entries=[t.load(p) for p in (ledger_root/"entries").glob("*.json")]
    t.require({e["request_id"] for e in entries if e["stage"]==stage}==matched,"unmatched stage spending")
    return reports,cost
