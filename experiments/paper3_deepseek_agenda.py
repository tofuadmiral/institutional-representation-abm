"""Frozen hosted reasoning screen, then at most six 25-decision episodes.

No model fallbacks, retries, answer repair, secret logging or local inference.
"""
from __future__ import annotations
import argparse
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3 import agenda_rights as game
from paper3.audit_runtime import PilotStore, digest
from experiments import paper3_bonsai_format_gate as fixtures
from experiments.paper3_bonsai_structured_agenda import case_for

NAME = "deepseek-hosted-agenda-discovery-v1"
MODEL = "deepseek/deepseek-v3.2"
PROVIDER, PROVIDER_NAME = "atlas-cloud/fp8", "AtlasCloud"
URL = "https://openrouter.ai/api/v1/chat/completions"
SEEDS = (191000, 192000, 193000)
MAX_OUTPUT = 4000  # Combined reasoning + final answer, provider-reported.
LIMITS = {"gate": (16, Decimal("0.10")), "episodes": (150, Decimal("0.36"))}
PRICE_IN, PRICE_OUT = Decimal("0.269"), Decimal("0.4")  # Maximum USD/million.


class Halt(ValueError):
    pass


def read_key(path=ROOT / ".env.local"):
    # Never source a shell file or write this value into a request artifact.
    values = [line.split("=", 1)[1].strip().strip('"').strip("'")
              for line in path.read_text().splitlines()
              if line.strip().startswith("OPENROUTER_API_KEY=")]
    if len(values) != 1 or not values[0] or any(c.isspace() for c in values[0]):
        raise ValueError("missing, duplicate or malformed OPENROUTER_API_KEY")
    return values[0]


def gate_cases():
    result = copy.deepcopy(fixtures.cases())
    for i, case in enumerate(result):
        case["seed"] = 190000 + i
    return result


def specifications():
    return [dict(name=f"conflict39-s{seed}-{arm}", profile=copy.deepcopy(game.profiles()[0]), arm=arm, seed=seed)
            for seed, arms in zip(SEEDS, (("D", "B"), ("B", "D"), ("D", "B"))) for arm in arms]


def request_for(case):
    return dict(model=MODEL, messages=copy.deepcopy(case["messages"]), seed=case["seed"],
        max_tokens=MAX_OUTPUT, temperature=1.0, top_p=0.95, top_k=20, min_p=0.0,
        presence_penalty=0.0, repetition_penalty=1.0,
        reasoning=dict(enabled=True, exclude=False), stream=False, plugins=[],
        response_format=dict(type="json_schema", json_schema=dict(
            name="institutional_action", strict=True, schema=copy.deepcopy(case["schema"]))),
        provider=dict(only=[PROVIDER], order=[PROVIDER], allow_fallbacks=False,
            require_parameters=True, quantizations=["fp8"],
            max_price=dict(prompt=float(PRICE_IN), completion=float(PRICE_OUT), request=0)))


def encoded_request(request):
    # Preserve schema insertion order in the actual transmitted JSON.
    return json.dumps(request, ensure_ascii=False, separators=(",", ":"))


def reserve_for(request):
    # Conservative byte-based estimate including schema and a template allowance;
    # provider tokenizer is not available locally. Verify returned usage against it.
    bound = len(encoded_request(request).encode("utf-8")) + 1024
    if bound > 65536:
        raise Halt("request exceeds frozen byte bound")
    return bound, (bound*PRICE_IN + MAX_OUTPUT*PRICE_OUT) / Decimal(1000000)


def accounting(row):
    if row.get("transport_error") or row.get("secret_redacted"):
        raise ValueError("transport failure or credential echo; cost not certified")
    response = row["response"]
    if not isinstance(response, dict):
        raise ValueError("API response is not an object")
    if response.get("error"):
        raise ValueError("API error response")
    if response.get("model") != MODEL or response.get("provider") != PROVIDER_NAME:
        raise ValueError("served model/provider mismatch")
    usage = response["usage"]
    prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
    if type(prompt) is not int or type(completion) is not int or not (0 < prompt <= row["input_token_bound"] and 0 < completion <= MAX_OUTPUT):
        raise ValueError("token accounting outside frozen bounds")
    cost = Decimal(str(usage["cost"]))
    if not cost.is_finite() or cost < 0 or cost > Decimal(row["reserved_usd"]):
        raise ValueError("missing/invalid cost or reservation exceeded")
    return cost


def checked_answer(row):
    accounting(row)
    choices = row["response"]["choices"]
    if len(choices) != 1 or choices[0]["finish_reason"] != "stop":
        raise ValueError("non-normal or ambiguous completion")
    message = choices[0]["message"]
    if message.get("refusal") or message.get("tool_calls"):
        raise ValueError("refusal or unexpected tool call")
    details = row["response"]["usage"].get("completion_tokens_details") or {}
    count = details.get("reasoning_tokens")
    text = message.get("reasoning")
    evidence = isinstance(text, str) and bool(text.strip())
    if count is not None and (type(count) is not int or count <= 0):
        raise ValueError("reported reasoning tokens not positive")
    if count is None and not evidence:
        raise ValueError("reasoning execution not evidenced")
    answer = message.get("content")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("empty final answer")
    return answer


def gate_score(row, case):
    try:
        raw = checked_answer(row)
        value = game.decode(raw)
        if case["stage"] == "selector":
            result = game.gate_score(raw, case["expected"])
            if result["status"] != "completed":
                raise ValueError(result["error"])
        else:
            game.validate_action(raw, case["stage"], case["candidates"])
        exact = value == case["expected"] if case["expected"] is not None else None
        return dict(status="completed", valid=True, exact=exact, passed=exact is not False, reply=value)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return dict(status="failed", valid=False, exact=None, passed=False, error=str(exc))


def ledger(rows, phase):
    subset = [r for r in rows if r["phase"] == phase]
    total = Decimal(0)
    for row in subset:
        try:
            amount = accounting(row) if row["status"] == "recorded" else Decimal(row["reserved_usd"])
        except (ValueError, KeyError, TypeError, ArithmeticError):
            amount = Decimal(row["reserved_usd"])
        total += amount
    return len(subset), total


def budget_guard(rows, phase, reserve):
    count, spent = ledger(rows, phase)
    limit_calls, limit_usd = LIMITS[phase]
    if count >= limit_calls:
        raise Halt("authorized phase call limit reached")
    if spent + reserve > limit_usd:
        raise Halt("authorized phase spending ceiling reached")


def transmit(request_text, secret):
    req = urllib.request.Request(URL, data=request_text.encode(), method="POST",
        headers={"Authorization": "Bearer "+secret, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as response:
            return response.status, response.read().decode("utf-8"), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace"), "HTTPError"
    except Exception as exc:
        # Do not serialize exception text/headers, which could include credentials.
        return None, "", type(exc).__name__


class Backend:
    def __init__(self, store, secret, transport=None):
        self.store, self.secret, self.transport = store, secret, transport or transmit
        self.halt = None

    def rows(self):
        return [json.loads(p.read_text()) for p in (self.store.root / "calls").glob("*.json")]

    def call(self, case, phase):
        request = request_for(case)
        key = digest(dict(request=request, phase=phase, protocol=self.store.protocol_hash))
        path = self.store.root / "calls" / (key+".json")
        if path.exists():
            row = json.loads(path.read_text())
            if row["status"] != "recorded":
                raise Halt("interrupted call is never retried")
            if row.get("accounting_error"):
                self.halt = "transport/accounting/routing failure"
            return key, row
        try:
            bound, reserve = reserve_for(request)
            budget_guard(self.rows(), phase, reserve)
        except Halt as exc:
            self.halt = str(exc)
            raise
        wire = encoded_request(request)
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
            cost = accounting(row)
            row["verified_cost_usd"] = str(cost)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            # Retain response and reservation; halt globally on uncertain billing/routing.
            self.halt = "transport/accounting/routing failure"
            row["accounting_error"] = type(exc).__name__ + ": " + str(exc)
        self.store.save("calls", key, row)
        usage = row["response"].get("usage", {}) if isinstance(row["response"], dict) else {}
        print("CALL", phase, case["name"], "tokens", usage.get("completion_tokens"),
              "cost", row.get("verified_cost_usd", "uncertain"), flush=True)
        return key, row


def run_one(backend, spec):
    keys, pending = [], None
    def ask(messages):
        nonlocal pending
        if len(keys) >= 25:
            raise ValueError("episode decision cap reached")
        case = case_for(messages, spec["seed"]+len(keys))
        pending = case
        key, row = backend.call(case, "episodes")
        keys.append(key)
        pending = None
        try:
            return checked_answer(row)
        except (KeyError, TypeError, IndexError, ArithmeticError) as exc:
            raise ValueError("invalid API answer: "+type(exc).__name__) from None
    result = game.run_episode(spec["profile"], spec["arm"], ask)
    return dict(result, name=spec["name"], profile=spec["profile"], arm=spec["arm"],
                call_keys=keys, unsubmitted_request=pending)


def prepare():
    snapshot = json.loads((ROOT / "paper3/deepseek_provider_snapshot.json").read_text())
    protocol = dict(name=NAME, model=MODEL, endpoint_snapshot=snapshot,
        cases=gate_cases(), episodes=specifications(), max_calls=166,
        phase_limits={p:dict(calls=n, usd=str(d)) for p,(n,d) in LIMITS.items()},
        max_output_tokens_per_call=MAX_OUTPUT, inference=request_for(gate_cases()[0]),
        authorization="Fuad approved the 16-call check capped at $0.10 and the subsequent 150-call run estimated $0.13-$0.36; enforce $0.36 as its ceiling",
        gate="all 16 valid normal reasoning-evidenced answers, all 8 selector and all 4 pivotal ratification checks exact; 4 pairwise format-only",
        design="three paired stochastic seeds on unchanged selected conflict39; 191000 D/B, 192000 B/D, 193000 D/B; offsets 0..24; one worker",
        measures="locked-proposal leader advantage B-D; enacted mean normalized regret B-D; all principal utilities, passage, consistency, fixed-output replay and failures; retain all signs",
        inference_scope="provider-reported FP8 DeepSeek, not local Bonsai; reasoning enabled with 4000 combined output cap, no local 1024-token forced closure; within-model authority comparison only",
        audit_limits="provider model/quantization labels are not weight hashes; requested seeds do not guarantee determinism; no access to provider tokenizer, hidden templates, grammar processor or internal token traces",
        budget_policy="reserve UTF-8 request bytes plus 1024 input tokens and full output cap at max_price before each call; verify returned usage/cost; halt on uncertainty; separate $0.10/$0.36 ceilings, no transfer",
        failure_policy="no retries, automatic fallbacks, repair or substituted votes; bad action ends own episode; HTTP/routing/accounting/budget error halts whole run; started request never regenerated",
        scope="instrument screen and single-selected-profile discovery, not confirmation or population evidence; preserve incomplete Bonsai separately",
        no_follow_on="stop after screen failure or six episodes; no additional models, profiles or calls")
    parent = json.loads((ROOT / "results/paper3/bonsai_structured_agenda_a1/manifest.json").read_text())
    sources = sorted(set([Path(p) for p in parent["sources"]] + [Path(__file__).resolve(),
        ROOT / "analysis/paper3_deepseek_agenda_audit.py", ROOT / "tests/test_paper3_deepseek_agenda.py",
        ROOT / "paper3/deepseek_provider_snapshot.json"]))
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
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in sources}, stream, indent=2)
    print("FROZEN", store.protocol_hash, flush=True)
    if args.freeze_only:
        return
    if (args.output / "sessions/terminal.json").exists():
        print("Already terminal; no inference", flush=True)
        return
    if any(json.loads(p.read_text())["status"] == "started" for p in (args.output / "calls").glob("*.json")):
        raise Halt("interrupted call requires inspection; never regenerate")
    backend = Backend(store, read_key())
    checks, episodes = [], {}
    for case in protocol["cases"]:
        name = "gate-"+case["name"]
        path = args.output / "sessions" / (name+".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            try:
                key, row = backend.call(case, "gate")
            except Halt:
                break
            result = dict(gate_score(row, case), name=name, call_keys=[key], protocol_hash=store.protocol_hash)
            store.save("sessions", name, result)
        checks.append(result)
        print("CHECK", name, result["valid"], result["exact"], flush=True)
        if backend.halt:
            break
    passed = len(checks) == 16 and all(r["passed"] for r in checks)
    if passed and not backend.halt:
        for spec in protocol["episodes"]:
            path = args.output / "sessions" / (spec["name"]+".json")
            if path.exists():
                result = json.loads(path.read_text())
            else:
                print("EPISODE START", spec["name"], flush=True)
                result = dict(run_one(backend, spec), protocol_hash=store.protocol_hash)
                store.save("sessions", spec["name"], result)
            episodes[spec["name"]] = result["status"]
            print("EPISODE", spec["name"], result["status"], result.get("resolution"), flush=True)
            if backend.halt:
                break
    terminal = dict(protocol_hash=store.protocol_hash, gate_passed=passed, checks=len(checks),
        valid=sum(r["valid"] for r in checks), exact=sum(r["exact"] is True for r in checks),
        episodes=episodes, halt=backend.halt,
        budgets={p:dict(calls=ledger(backend.rows(), p)[0], accounted_usd=str(ledger(backend.rows(), p)[1])) for p in LIMITS})
    store.save("sessions", "terminal", terminal)
    print("TERMINAL", json.dumps(terminal), "No automatic follow-on", flush=True)


if __name__ == "__main__":
    main()
