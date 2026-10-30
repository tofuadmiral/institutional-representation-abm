"""Prospective B calls with a shared ledger and bounded sanitized HTTP errors.

No historical runner is edited. Request construction, source verification and
action scoring are supplied by each separately frozen experiment. One POST per
admission; no fallbacks, content repair, retries or admission after a safety stop.
"""
from decimal import Decimal
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


class Calls:
    def __init__(self,root,ledger_root,stage,max_calls,verify,score,secret=None,
                 send=None,lookup=None,clock=time.time,sleep=time.sleep):
        self.root=Path(root);self.ledger=Ledger(ledger_root);self.stage=stage;self.max_calls=max_calls
        self.verify,self.score=verify,score;self.protocol=verify()[1];self.secret=secret
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
            s=t.stream_summary(row["stream"])
            if ((s["models"] and not set(s["models"])<=set(t.MODELS)) or
                (s["providers"] and s["providers"]!=[t.PROVIDER]) or len(s["models"])>1 or
                len(s["ids"])>1 or row["stream"]["secret_redacted"]):self.stop.set()
            if s["generation_id"]:
                for offset in (0,20,40,60):
                    self.sleep(max(0,row["stream"]["ended_unix"]+offset-self.clock()))
                    observation=self.lookup(s["generation_id"],self.secret)
                    observation,hit=t.redact(observation,self.secret)
                    observation["secret_redacted"]=hit or observation.get("secret_redacted",False)
                    observation["scheduled_offset_seconds"]=offset
                    row["receipts"].append(observation);atomic(path,row)
                    current=t.assess(row)
                    if current["receipt_certified"]:break
                    if observation.get("http_status")==200:self.stop.set();break
            row["assessment"]=t.assess(row);row.update(status="recorded",ended_unix=self.clock())
            a=row["assessment"];s=a["stream"]
            row["final_content"]=final_content(row["stream"]) if s["complete"] else None
            row["result"]=self.score(row,case)
            atomic(path,row)
            self.ledger.settle(self.stage+"-"+key,a["accounted_usd"],a["receipt_certified"],t.sha(path.read_bytes()))
            usage=s.get("usage") or {};n=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            native=type(n) is int and 0<n<=usage.get("completion_tokens",0)
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


def audit_records(root,ledger_root,stage,protocol,cases,terminal,score):
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
            a=t.assess(row)
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
