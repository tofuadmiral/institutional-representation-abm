"""Fresh-only billing-separated service; full reservation survives absent receipt."""
from __future__ import annotations

from decimal import Decimal
import json

from experiments import paper3_transport_diagnostic as t
from experiments.paper3_coalition_contracts import final_content
from paper3 import hosted_reasoning_calls as base
from paper3.pivot_b_budget import atomic
from paper3.retrospective_billing_separation import assess, absent_observation


def native_evidence(summary):
    usage = summary.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    count = details.get("reasoning_tokens") if isinstance(details, dict) else None
    total = usage.get("completion_tokens")
    channel = summary.get("reasoning_channel_characters", 0) > 0
    return dict(present=channel, nonempty_native_channel=channel,
                reported_tokens=count,
                reported_count_consistent=(count is None or
                                           (type(count) is int and type(total) is int
                                            and 0 <= count <= total)))


class Calls(base.Calls):
    """Keep all parent transport/billing behavior, changing only native evidence."""

    def one(self, case):
        key = case["id"]
        path = self.root / "calls" / (key + ".json")
        reserve = Decimal(case["reserved_usd"])
        with self.guard:
            if self.stop.is_set():
                return dict(id=key, status="not_started")
            try:
                t.require(self.verify()[1] == self.protocol, "source/protocol changed")
                t.require(len(list((self.root / "calls").glob("*.json"))) < self.max_calls,
                          "attempt ceiling")
                t.require(t.canonical(case["request"]) == case["request_text"] and
                          t.sha(case["request_text"].encode()) == case["request_sha256"],
                          "request hash")
                self.ledger.reserve(self.stage, self.stage + "-" + key, reserve,
                                    case["request_sha256"])
                row = dict(**case, protocol=self.protocol, status="admitted", attempt=1,
                           admitted_unix=self.clock())
                atomic(path, row)
            except Exception as exc:
                self.stop.set()
                return dict(id=key, status="admission_failed",
                            error_type=type(exc).__name__)
        try:
            row["stream"] = self.send(case["request_text"], self.secret)
            row["stream"], hit = t.redact(row["stream"], self.secret)
            row["stream"]["secret_redacted"] = (
                hit or row["stream"].get("secret_redacted", False))
            row.update(status="stream_ended", receipts=[])
            atomic(path, row)
            summary = base.stream_summary(row["stream"], self.config)
            if ((summary["models"] and not set(summary["models"]) <=
                 set(self.config["models"])) or
                    (summary["providers"] and summary["providers"] !=
                     [self.config["provider"]]) or len(summary["models"]) > 1 or
                    len(summary["ids"]) > 1 or row["stream"]["secret_redacted"]):
                self.stop.set()
            if summary["generation_id"]:
                for offset in (0, 20, 40, 60):
                    self.sleep(max(0, row["stream"]["ended_unix"] + offset - self.clock()))
                    observation = self.lookup(summary["generation_id"], self.secret)
                    observation, hit = t.redact(observation, self.secret)
                    observation["secret_redacted"] = (
                        hit or observation.get("secret_redacted", False))
                    observation["scheduled_offset_seconds"] = offset
                    row["receipts"].append(observation)
                    atomic(path, row)
                    current = base.assess(row, self.config)
                    if current["receipt_certified"]:
                        break
                    if observation.get("http_status") == 200:
                        self.stop.set()
                        break
                    if not absent_observation(observation):
                        self.stop.set()
                        break
            row["assessment"] = assess(row, self.config)
            row.update(status="recorded", ended_unix=self.clock())
            assessed = row["assessment"]
            summary = assessed["stream"]
            row["final_content"] = (final_content(row["stream"])
                                    if summary["complete"] else None)
            row["result"] = self.score(row, case)
            atomic(path, row)
            self.ledger.settle(self.stage + "-" + key, assessed["accounted_usd"],
                               assessed["receipt_certified"], t.sha(path.read_bytes()))
            if (Decimal(assessed["accounted_usd"]) > reserve or
                    (summary["complete"] and not native_evidence(summary)["present"]) or
                    summary["finish_reasons"] == ["length"]):
                self.stop.set()
            if not assessed["passed"]:
                with self.guard:
                    self.transport_failures += 1
                    if self.transport_failures >= 2:
                        self.stop.set()
            print(json.dumps(dict(event="b_call_terminal", id=key,
                                  result=row["result"],
                                  budget=self.ledger.snapshot())), flush=True)
            return dict(id=key, status="recorded")
        except Exception as exc:
            self.stop.set()
            row.update(status="instrument_error", instrument_error=type(exc).__name__)
            atomic(path, row)
            return dict(id=key, status="instrument_error")


def audit_records(root, ledger_root, stage, protocol, cases, terminal, score, config):
    """Recompute expense and scientific validity separately from saved evidence."""
    from pathlib import Path
    root, ledger_root = Path(root), Path(ledger_root)
    reports, matched, cost = [], set(), Decimal(0)
    t.require(not list(root.rglob("*.partial")), "partial writes remain")
    t.require([r["id"] for r in terminal["results"]] == [c["id"] for c in cases], "assigned inventory")
    for case, status in zip(cases, terminal["results"], strict=True):
        key = case["id"]
        path = root / "calls" / (key + ".json")
        ep = ledger_root / "entries" / (stage + "-" + key + ".json")
        if not path.exists():
            t.require(status["status"] in ("not_started", "admission_failed"), "missing admitted call")
            if ep.exists():
                e = t.load(ep)
                matched.add(e["request_id"])
                t.require(e["status"] == "reserved" and e["request_sha256"] == case["request_sha256"]
                    and e["reserved_usd"] == case["reserved_usd"], "orphan reservation")
                cost += Decimal(e["reserved_usd"])
            reports.append(dict(id=key, status=status["status"], result=None))
            continue
        row, e = t.load(path), t.load(ep)
        matched.add(e["request_id"])
        t.require(all(row.get(k) == v for k, v in case.items()) and row["protocol"] == protocol
            and row["attempt"] == 1, "call provenance")
        t.require(row["status"] == status["status"], "terminal call status")
        t.require(e["request_sha256"] == case["request_sha256"] and e["reserved_usd"] == case["reserved_usd"],
            "ledger request")
        result = score(row, case)
        if not row.get("instrument_error"):
            a = assess(row, config)
            t.require(row["assessment"] == a and row["result"] == result, "assessment/action changed")
            t.require(row["final_content"] == (final_content(row["stream"]) if a["stream"]["complete"] else None),
                "final changed")
            t.require(e["status"] == "settled" and e["evidence_sha256"] == t.sha(path.read_bytes()),
                "settlement evidence")
            t.require(e["accounted_usd"] == a["accounted_usd"] and e["certified"] == a["receipt_certified"],
                "accounting changed")
        cost += Decimal(e.get("accounted_usd", e["reserved_usd"]))
        reports.append(dict(id=key, status=row["status"], result=result))
    t.require({p.stem for p in (root / "calls").glob("*.json")} <= {c["id"] for c in cases}, "unexpected calls")
    entries = [t.load(p) for p in (ledger_root / "entries").glob("*.json")]
    t.require({e["request_id"] for e in entries if e["stage"] == stage} == matched, "unmatched stage spending")
    return reports, cost
