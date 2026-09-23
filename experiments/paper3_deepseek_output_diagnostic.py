"""Sixteen paired output-interface checks; no legislature or automatic follow-on."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import paper3_deepseek_agenda as base
from paper3.audit_runtime import PilotStore, digest

NAME = "deepseek-output-interface-diagnostic-v1"
MODES = ("strict", "plain")


def cases():
    result = []
    for i, original in enumerate(base.gate_cases()[:8]):
        for mode in MODES if i % 2 == 0 else tuple(reversed(MODES)):
            row = copy.deepcopy(original)
            row.update(name=f"selector-{i}-{mode}", fixture=i, mode=mode, seed=200000+i)
            result.append(row)
    return result


def request_for(case):
    request = base.request_for(case)
    if case["mode"] == "plain":
        del request["response_format"]
    elif case["mode"] != "strict":
        raise ValueError("unknown output mode")
    return request


def reasoning_report(row, case, final):
    """Descriptive last complete schema-valid JSON in returned reasoning, if any.

    Never infer missing text, score prose by judgment, or substitute it for actions.
    """
    try:
        message = row["response"]["choices"][0]["message"]
        text = message.get("reasoning")
        if not isinstance(text, str):
            return dict(json_count=0, available=False)
        found = []
        decoder = json.JSONDecoder()
        for i, char in enumerate(text):
            if char != "{":
                continue
            try:
                value, end = decoder.raw_decode(text[i:])
                checked = base.game.gate_score(json.dumps(value), case["expected"])
                if checked["status"] == "completed":
                    found.append((i, i+end, value))
            except (ValueError, KeyError, TypeError):
                continue
        if not found:
            return dict(json_count=0, available=False)
        start, end, value = found[-1]
        return dict(json_count=len(found), available=True, span=[start, end], reply=value,
            exact=value == case["expected"],
            agrees_with_final=value == final["reply"] if final["valid"] else None)
    except (KeyError, TypeError, IndexError):
        return dict(json_count=0, available=False)


def score(row, case):
    final = base.gate_score(row, case)
    return dict(final, reasoning_observation=reasoning_report(row, case, final))


class Backend(base.Backend):
    def call(self, case, phase="gate"):
        if phase != "gate":
            raise base.Halt("diagnostic has no episode phase")
        request = request_for(case)
        key = digest(dict(request=request, phase=phase, protocol=self.store.protocol_hash))
        path = self.store.root / "calls" / (key+".json")
        if path.exists():
            row = json.loads(path.read_text())
            if row["status"] != "recorded":
                raise base.Halt("interrupted call is never retried")
            if row.get("accounting_error"):
                self.halt = "transport/accounting/routing failure"
            return key, row
        try:
            bound, reserve = base.reserve_for(request)
            base.budget_guard(self.rows(), phase, reserve)
        except base.Halt as exc:
            self.halt = str(exc)
            raise
        wire = base.encoded_request(request)
        row = dict(request=request, request_text=wire, phase=phase, protocol_hash=self.store.protocol_hash,
            input_token_bound=bound, reserved_usd=str(reserve), started_unix=time.time(), status="started")
        self.store.save("calls", key, row)
        status, raw, error = self.transport(wire, self.secret)
        redacted = self.secret in raw
        if redacted:
            raw = raw.replace(self.secret, "[REDACTED_CREDENTIAL]")
        row.update(status="recorded", http_status=status, response_text=raw,
            elapsed_seconds=time.time()-row["started_unix"], secret_redacted=redacted)
        if error:
            row["transport_error"] = error
        try:
            row["response"] = json.loads(raw)
        except (ValueError, TypeError):
            row["response"] = {}
        try:
            row["verified_cost_usd"] = str(base.accounting(row))
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            self.halt = "transport/accounting/routing failure"
            row["accounting_error"] = type(exc).__name__+": "+str(exc)
        self.store.save("calls", key, row)
        print("CALL", case["name"], "cost", row.get("verified_cost_usd", "uncertain"), flush=True)
        return key, row


def summarize(checks):
    result = {}
    for mode in MODES:
        rows = [r for r in checks if r["mode"] == mode]
        result[mode] = dict(calls=len(rows), valid=sum(r["valid"] for r in rows),
            exact=sum(r["exact"] is True for r in rows),
            reasoning_json_available=sum(r["reasoning_observation"]["available"] for r in rows),
            reasoning_final_mismatches=sum(r["reasoning_observation"].get("agrees_with_final") is False for r in rows))
    return result


def terminal(checks, rows, ph, halt):
    count, amount = base.ledger(rows, "gate")
    return dict(protocol_hash=ph, checks=len(checks), completed=len(checks) == 16,
        halt=halt, budget=dict(calls=count, accounted_usd=str(amount)),
        modes=summarize(checks), episodes={}, no_follow_on=True)


def prepare():
    parent = json.loads((ROOT / "results/paper3/deepseek_agenda_a1/manifest.json").read_text())
    protocol = dict(name=NAME, parent_protocol_hash=digest(parent), cases=cases(), max_calls=16,
        max_usd="0.10", max_output=base.MAX_OUTPUT, inference=request_for(cases()[0]),
        authorization="Fuad approved 16-call same-model structured-versus-plain diagnostic capped at $0.10",
        contrast="only response_format removed for plain; identical messages including schema instruction, paired fresh seeds 200000..200007; strict first for even fixtures, plain first for odd",
        selection="all eight previous selector fixtures, not only two failed items; selected instrument discovery, not untouched cases",
        measures="strict local parse and exact final decision; last complete schema-valid JSON in returned reasoning if present, descriptive mismatch only; all paired final fields and failures retained",
        reasoning_limits="returned text is not verified cognition; absence of JSON is missing, not agreement; no repair or substitution from reasoning",
        request_policy="same DeepSeek/AtlasCloud FP8 endpoint, 4000 combined output cap, reasoning on, no fallback, retries or local inference",
        budget_policy="inherit gate-only 16-call/$0.10 pre-request reservation; halt on transport, routing, billing uncertainty; no budget transfer",
        conclusion_limits="one sample per cell, noisy paired seeds not guaranteed coupled randomness; cannot identify provider internals or establish causal source of mismatch; no competence-gate pass or institutional effect",
        no_follow_on="no legislature calls or other models; requires separate design decision")
    sources = sorted(set([Path(p) for p in parent["sources"]] + [Path(__file__).resolve(),
        ROOT / "analysis/paper3_deepseek_output_audit.py", ROOT / "tests/test_paper3_deepseek_output.py"]))
    return protocol, sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    protocol, sources = prepare()
    store = PilotStore(args.output, protocol, sources)
    if not (args.output / "sources.json").exists():
        with (args.output / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)):p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    if (args.output / "sessions/terminal.json").exists():
        print("Already terminal; no inference", flush=True)
        return
    if any(json.loads(p.read_text())["status"] == "started" for p in (args.output / "calls").glob("*.json")):
        raise base.Halt("interrupted call is never retried")
    backend = Backend(store, base.read_key())
    checks = []
    for case in protocol["cases"]:
        path = args.output / "sessions" / (case["name"]+".json")
        if path.exists():
            result = json.loads(path.read_text())
            for key in result["call_keys"]:
                if json.loads((args.output / "calls" / (key+".json")).read_text()).get("accounting_error"):
                    backend.halt = "transport/accounting/routing failure"
        else:
            try:
                key, row = backend.call(case)
            except base.Halt:
                break
            result = dict(score(row, case), name=case["name"], fixture=case["fixture"], mode=case["mode"],
                call_keys=[key], protocol_hash=store.protocol_hash)
            store.save("sessions", case["name"], result)
        checks.append(result)
        print("CHECK", case["name"], result["valid"], result["exact"], flush=True)
        if backend.halt:
            break
    result = terminal(checks, backend.rows(), store.protocol_hash, backend.halt)
    store.save("sessions", "terminal", result)
    print("TERMINAL", json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
