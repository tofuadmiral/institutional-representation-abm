"""One frozen fresh-profile pair, with a disjoint share of a $3 batch budget.

No model fallbacks, retries, answer repair, secret logging or local inference.
"""
from __future__ import annotations
import argparse
import copy
from contextlib import contextmanager
from decimal import Decimal
import fcntl
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
from paper3.agenda_benchmarks import generated_profile, certificate
from paper3.agenda_objective_benchmarks import objective_benchmarks
from paper3.audit_runtime import PilotStore, digest
from experiments import paper3_bonsai_format_gate as fixtures
from experiments.paper3_bonsai_structured_agenda import case_for

NAME = "deepseek-eight-fresh-profile-discovery-v1"
MODEL = "deepseek/deepseek-v3.2"
PROVIDER, PROVIDER_NAME = "atlas-cloud/fp8", "AtlasCloud"
URL = "https://openrouter.ai/api/v1/chat/completions"
PROFILE_INDEX = 0
PROFILE_SEEDS = tuple(range(1002000, 1002008))
SEEDS = (241000,)


def configure(index):
    global PROFILE_INDEX, SEEDS
    if type(index) is not int or index not in range(8):
        raise ValueError("profile index must be an integer from0 through7")
    PROFILE_INDEX, SEEDS = index, (241000 + index*1000,)

MAX_OUTPUT = 65536  # Requested combined reasoning + final output.
BILLING_OUTPUT_BOUND = MAX_OUTPUT + 16  # Disclosed provider token-accounting tolerance.
LIMITS = {"gate": (0, Decimal("0")), "episodes": (50, Decimal("0.375"))}
PRICE_IN, PRICE_OUT = Decimal("0.269"), Decimal("0.4")  # Maximum USD/million.


class Halt(ValueError):
    pass


@contextmanager
def admission_lock(root):
    with (root.parent / "admission.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def read_key(path=ROOT / ".env.local"):
    # Never source a shell file or write this value into a request artifact.
    values = [line.split("=", 1)[1].strip().strip('"').strip("'")
              for line in path.read_text().splitlines()
              if line.strip().startswith("OPENROUTER_API_KEY=")]
    if len(values) != 1 or not values[0] or any(c.isspace() for c in values[0]):
        raise ValueError("missing, duplicate or malformed OPENROUTER_API_KEY")
    return values[0]


def gate_cases():
    return []  # Reuse the completed lower-budget plain-output gate, explicitly disclosed.


def specifications():
    profile = generated_profile(PROFILE_SEEDS[PROFILE_INDEX])
    arms = ("D", "B") if PROFILE_INDEX % 2 == 0 else ("B", "D")
    return [dict(name=f"{profile['name']}-s{SEEDS[0]}-{arm}",
        profile=copy.deepcopy(profile), arm=arm, seed=SEEDS[0]) for arm in arms]


def request_for(case):
    return dict(model=MODEL, messages=copy.deepcopy(case["messages"]), seed=case["seed"],
        max_tokens=MAX_OUTPUT, temperature=1.0, top_p=0.95, top_k=20, min_p=0.0,
        presence_penalty=0.0, repetition_penalty=1.0,
        reasoning=dict(enabled=True, exclude=False), stream=False, plugins=[],
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
    return bound, (bound*PRICE_IN + BILLING_OUTPUT_BOUND*PRICE_OUT) / Decimal(1000000)


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
    if type(prompt) is not int or type(completion) is not int or not (0 < prompt <= row["input_token_bound"] and 0 < completion <= BILLING_OUTPUT_BOUND):
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
        with urllib.request.urlopen(req, timeout=1800) as response:
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
        if (self.store.root.parent / "batch_stop.json").exists():
            self.halt = "coordinated batch safety halt"
            raise Halt(self.halt)
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
        with admission_lock(self.store.root):
            if (self.store.root.parent / "batch_stop.json").exists():
                self.halt = "coordinated batch safety halt"
                raise Halt(self.halt)
            row["started_unix"] = time.time()
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
        if row.get("accounting_error"):
            # Stop admission at other workers' next call boundary. Already
            # admitted network calls finish and retain their reservations.
            with admission_lock(self.store.root):
                try:
                    with (self.store.root.parent / "batch_stop.json").open("x") as stream:
                        json.dump(dict(shard=self.store.root.name, call_key=key,
                            created_unix=time.time()), stream)
                except FileExistsError:
                    pass
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


def prerequisite():
    previous_root = ROOT / "results/paper3/deepseek_long_agenda_a1"
    terminal = json.loads((previous_root / "sessions/terminal.json").read_text())
    if terminal["episodes"] != {"conflict39-s232000-B": "completed", "conflict39-s232000-D": "completed"} or terminal["halt"]:
        raise Halt("both 64K feasibility episodes must complete before fresh-profile inference")
    from analysis.paper3_deepseek_long_agenda_audit import audit
    if audit(previous_root)["integrity_errors"]:
        raise Halt("64K prerequisite failed its provenance audit")
    # Existing uncertain4K reservation remains reserved, never silently released.
    prior = Decimal("0.086293343") + sum(Decimal(row["accounted_usd"]) for row in terminal["budgets"].values())
    if prior + Decimal("3") > Decimal("10"):
        raise Halt("fresh-profile allocation would exceed cumulative$10 authorization")
    return dict(terminal=terminal,
        protocol_hash=digest(json.loads((previous_root / "manifest.json").read_text())),
        prior_conservative_usd=str(prior))


def prepare():
    predecessor = prerequisite()
    diagnostic = json.loads((ROOT / "results/paper3/deepseek_output_a1/sessions/terminal.json").read_text())
    if not diagnostic["completed"] or diagnostic["halt"] or diagnostic["modes"]["plain"]["exact"] != 8 or diagnostic["modes"]["plain"]["valid"] != 8:
        raise Halt("plain-output diagnostic prerequisite not satisfied")
    prior = json.loads((ROOT / "results/paper3/deepseek_plain_agenda_a1/sessions/terminal.json").read_text())
    if not prior["gate_passed"] or prior["checks"] != 16 or prior["exact"] != 12 or prior["valid"] != 16:
        raise Halt("completed plain gate prerequisite missing")
    snapshot = json.loads((ROOT / "paper3/deepseek_provider_snapshot.json").read_text())
    protocol = dict(name=NAME, model=MODEL, endpoint_snapshot=snapshot,
        profile_index=PROFILE_INDEX, profile_seeds=list(PROFILE_SEEDS), inference_seeds=list(SEEDS),
        fresh_frame=[generated_profile(seed) for seed in PROFILE_SEEDS],
        analytic_certificates=[certificate(generated_profile(seed)) for seed in PROFILE_SEEDS],
        set_valued_objective_benchmarks=[objective_benchmarks(generated_profile(seed)) for seed in PROFILE_SEEDS],
        benchmark_interpretation="secondary descriptive set membership only: arbitrary tied proposal labels are not errors; scripted continuation assumptions do not establish actual best responses or motives; frozen primary endpoints unchanged",
        prerequisite=predecessor,
        batch_scope="eight unfiltered consecutive profiles;16episodes/400calls;8 disjoint$0.375 allocations=$3; max4 independent pair workers; serial calls within each pair",
        pair_scope="one assigned profile pair; no effects imputed for failed episodes; all8pairs retained regardless of sign",
        stages="primary locked-proposal leader advantage B-D and enacted mean regret B-D; allprincipal changes, worstregret, statusquo harm, passage, failures, stage choices and descriptive replays",
        sampling_scope="discovery, one paired requested seed per profile, not seed-stability evidence; profiles are experimental units, not calls/votes",
        scale_gate="fewer than7completepairs blocks scaleup;7/8 still needs missingness diagnosis and bounds, not silent complete-case confirmation",
        missingness="full-menu bounds for every assigned profile, not confidence intervals; retain a valid locked choice even if a later stage fails; never impute an unobserved enacted policy",

        cases=[], episodes=specifications(), max_calls=50,
        inherited_gate=json.loads((ROOT / "results/paper3/deepseek_plain_agenda_a1/sessions/terminal.json").read_text()),
        inherited_gate_protocol=digest(json.loads((ROOT / "results/paper3/deepseek_plain_agenda_a1/manifest.json").read_text())),
        inherited_gate_scope="16/16 valid,12/12 exact at4000 output cap; reused as prerequisite, not claimed retested at65536; original failure preserved",
        billing_output_bound=BILLING_OUTPUT_BOUND, request_timeout_seconds=1800,
        output_interface="API response_format omitted; explicit JSON schema instruction retained; local strict parser, no action repair",
        fresh_gate="none: explicit completed lower-budget plain-output gate reused",
        predecessor_diagnostic_hash=digest(json.loads((ROOT / "results/paper3/deepseek_output_a1/manifest.json").read_text())),
        predecessor_diagnostic_terminal=json.loads((ROOT / "results/paper3/deepseek_output_a1/sessions/terminal.json").read_text()),
        continuing_budget="predecessor conservative accounting plus disjoint8x$0.375 allocation <= $10; one coordinated batch, no overlapping predecessor/successor",
        phase_limits={p:dict(calls=n, usd=str(d)) for p,(n,d) in LIMITS.items()},
        max_output_tokens_per_call=MAX_OUTPUT, inference=request_for(case_for(game.messages(specifications()[0]["profile"], specifications()[0]["arm"], specifications()[0]["profile"]["leader"], "opening", []), SEEDS[0])),
        authorization="Fuad approved continued investigation within $10 additional OpenRouter maximum; allocate $3/400calls split8x$0.375/50calls to fresh-profile discovery; no credit purchases",
        gate="inherited completed16-call plain gate; no new gate calls, no retrospective forgiveness of earlier failures",
        design="unfiltered generator seeds1002000..1002007; inference241000+1000*index+decisionoffset; D-first evenindex/B-first oddindex; no outcome-based filtering",
        measures="locked-proposal leader advantage B-D; enacted mean normalized regret B-D; all principal utilities, passage, consistency, fixed-output replay and failures; retain all signs",
        inference_scope="provider-reported FP8 DeepSeek, not local Bonsai; reasoning enabled with65536 requested combined output cap and65552 provider accounting bound, no local 1024-token forced closure; within-model authority comparison only",
        audit_limits="provider model/quantization labels are not weight hashes; requested seeds do not guarantee determinism; no access to provider tokenizer, hidden templates, grammar processor or internal token traces",
        budget_policy="reserve UTF-8 request bytes plus 1024 input tokens and full output cap at max_price before each call; verify returned usage/cost; halt on uncertainty; no new gate calls, $0.375/50call per-pair ceiling; reserve65552 tokens including16-token accounting margin",
        failure_policy="no retries/repair/fallbacks; invalid action ends episode; HTTP/routing/accounting failure writes batch_stop, workers stop at next call boundary, admitted calls finish; pair allocation stop halts own shard and prevents new shards; never regenerate started calls",
        scope="fresh-profile exploratory discovery after adaptive instrument development; not confirmation; retain all failures and all eight profiles",
        no_follow_on="stop each shard after its two episodes or safety halt; one predetermined eight-pair batch, no replacement profiles or automatic confirmation")
    parent = json.loads((ROOT / "results/paper3/deepseek_plain_agenda_a1/manifest.json").read_text())
    sources = sorted(set([Path(p) for p in parent["sources"]] + [Path(__file__).resolve(),
        ROOT / "analysis/paper3_deepseek_fresh_profiles_audit.py", ROOT / "tests/test_paper3_deepseek_fresh_profiles.py",
        ROOT / "paper3/deepseek_provider_snapshot.json", ROOT / "paper3/agenda_benchmarks.py",
        ROOT / "paper3/agenda_objective_benchmarks.py", ROOT / "tests/test_paper3_agenda_objective_benchmarks.py",
        ROOT / "experiments/paper3_deepseek_fresh_batch.py",
        ROOT / "analysis/paper3_deepseek_fresh_batch_audit.py",
        ROOT / "analysis/paper3_agenda_adaptation.py", ROOT / "analysis/paper3_agenda_fidelity.py"]))
    return protocol, sources


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--index", type=int, choices=range(8), default=0)
    args = parser.parse_args()
    configure(args.index)
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
            if any(json.loads((args.output / "calls" / (k+".json")).read_text()).get("accounting_error") for k in result["call_keys"]):
                backend.halt = "transport/accounting/routing failure"
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
    passed = len(checks) == 0 and protocol["inherited_gate"]["gate_passed"]
    if passed and not backend.halt:
        for spec in protocol["episodes"]:
            path = args.output / "sessions" / (spec["name"]+".json")
            if path.exists():
                result = json.loads(path.read_text())
                if any(json.loads((args.output / "calls" / (k+".json")).read_text()).get("accounting_error") for k in result["call_keys"]):
                    backend.halt = "transport/accounting/routing failure"
                elif result.get("unsubmitted_request") is not None:
                    backend.halt = result["error"]
            else:
                print("EPISODE START", spec["name"], flush=True)
                result = dict(run_one(backend, spec), protocol_hash=store.protocol_hash)
                store.save("sessions", spec["name"], result)
            episodes[spec["name"]] = result["status"]
            print("EPISODE", spec["name"], result["status"], result.get("resolution"), flush=True)
            if backend.halt:
                break
    terminal = dict(protocol_hash=store.protocol_hash, gate_passed=passed, checks=len(checks),
        gate_reused_from=protocol["inherited_gate_protocol"],
        valid=sum(r["valid"] for r in checks), exact=sum(r["exact"] is True for r in checks),
        episodes=episodes, halt=backend.halt,
        budgets={p:dict(calls=ledger(backend.rows(), p)[0], accounted_usd=str(ledger(backend.rows(), p)[1])) for p in LIMITS})
    store.save("sessions", "terminal", terminal)
    print("TERMINAL", json.dumps(terminal), "No automatic follow-on", flush=True)


if __name__ == "__main__":
    main()
