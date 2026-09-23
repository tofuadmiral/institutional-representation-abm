"""Authority x disclosure-timing pilot, rerun a3 of the a2 design (a2 preserved unchanged).

a2 produced no complete profile because local network outages reset every open
stream roughly every 5-6 minutes. a3 reruns the identical design, instrument and
four theory-selected profiles on fresh inference seeds (a discovery replication
attempt, not a continuation of a2 and not confirmation). Only the name, seeds,
prior-spend accounting and predecessor record differ.


Identical to paper3_deepseek_disclosure.py (a1, preserved unchanged) except the
lottery gate asks for expected_utility as a JSON string. a1 failed its gate 6/8:
both invalid answers carried stray CJK tokens exactly where an unquoted number
followed the colon, while all string fields were clean and the reasoning text
contained the correct values. The 8/8 valid-and-exact standard is unchanged.
One bounded successor attempt; if this gate fails, stop.

Per profile: early D and early B episodes (unchanged agenda_rights), and a late
condition whose nine-decision prefix is played under a public 50/50 rule lottery
and then cloned into fresh D and B continuations (paper3/agenda_disclosure.py).

Transport, declared prospectively (the only change from the fresh-profile
runner besides the design): requests are streamed so provider keep-alive
comments prevent idle connection resets. If a stream ends without a final
finish_reason and usage, its charge is certified through OpenRouter's
generation endpoint and the identical request is re-issued exactly once. The
lost answer is never observed, so re-issue cannot select on content. A second
transport failure fails only that episode/branch. An uncertifiable charge
keeps its full reservation and halts the shard. Served model/provider mismatch
halts every shard. No answer repair, fallbacks or other retries.
"""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3 import agenda_rights as game
from paper3 import agenda_disclosure as late
from paper3.agenda_benchmarks import generated_profile
from paper3.agenda_disclosure_benchmarks import disclosure_benchmark
from paper3.audit_runtime import PilotStore, digest
from experiments import paper3_deepseek_fresh_profiles as base
from experiments.paper3_bonsai_structured_agenda import case_for

NAME = "deepseek-authority-disclosure-pilot-a3"
MODEL, PROVIDER_NAME = base.MODEL, base.PROVIDER_NAME
GENERATION_URL = "https://openrouter.ai/api/v1/generation?id="
PRIOR_ADDITIONAL_USD = Decimal("1.115910811")  # audited through deepseek_disclosure_a2
AUTHORIZED_USD = Decimal("10")
LIMITS = {"gate": (8, Decimal("0.10")), "episodes": (120, Decimal("0.60"))}
SHARDS = 4
SEED_BASE = 261000
GATE_SEED = 260000


class TransportFailed(ValueError):
    """Declared transport failure after the single re-issue; fails only this episode."""


def frame():
    selection = late.select_profiles()
    seeds = selection["positive"] + selection["zero_control"]
    return selection, seeds


def schedule(index):
    """Counterbalanced run order within a profile; conditions share inference seeds."""
    order = [("early", "D"), ("early", "B"), ("late", "DB" if index % 2 == 0 else "BD")]
    return order[index % 3:] + order[:index % 3]


def request_for(case):
    request = base.request_for(case)
    request["stream"] = True
    request["usage"] = dict(include=True)  # final stream chunk carries usage and cost
    return request


# ---------------------------------------------------------------- transport

def stream_transmit(request_text, secret):
    req = urllib.request.Request(base.URL, data=request_text.encode(), method="POST",
        headers={"Authorization": "Bearer " + secret, "Content-Type": "application/json"})
    lines, generation_id = [], None
    try:
        with urllib.request.urlopen(req, timeout=900) as response:
            generation_id = response.headers.get("X-Generation-Id")
            for raw in response:
                lines.append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
            return dict(http_status=response.status, lines=lines, generation_id=generation_id, error=None)
    except urllib.error.HTTPError as exc:
        return dict(http_status=exc.code, lines=exc.read().decode("utf-8", errors="replace").splitlines(),
                    generation_id=generation_id, error="HTTPError")
    except Exception as exc:
        # Never serialize exception text/headers, which could include credentials.
        return dict(http_status=None, lines=lines, generation_id=generation_id, error=type(exc).__name__)


def fetch_generation(generation_id, secret, attempts=12, wait=20.0, sleep=time.sleep):
    for i in range(attempts):
        req = urllib.request.Request(GENERATION_URL + generation_id, method="GET",
                                     headers={"Authorization": "Bearer " + secret})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8")).get("data")
                if data and data.get("total_cost") is not None:
                    return data
        except Exception:
            pass
        if i + 1 < attempts:
            sleep(wait)
    return None


def assemble(lines):
    """Rebuild a non-streamed response object from SSE lines; keep-alive comments skipped."""
    content, reasoning = [], []
    response, finish, usage, error, done = {}, None, None, None, False
    for line in lines:
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            done = True
            continue
        chunk = json.loads(data)
        for field in ("id", "model", "provider", "created", "object"):
            if field in chunk and field not in response:
                response[field] = chunk[field]
        if chunk.get("error"):
            error = chunk["error"]
        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
            if delta.get("reasoning"):
                reasoning.append(delta["reasoning"])
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]
    response.update(choices=[dict(index=0, finish_reason=finish,
        message=dict(role="assistant", content="".join(content), reasoning="".join(reasoning) or None))],
        usage=usage)
    if error:
        response["error"] = error
    complete = done and finish is not None and usage is not None and error is None
    return response, complete


def certify(data, row):
    if data is None:
        raise ValueError("generation charge unavailable")
    if not str(data.get("model", "")).startswith(MODEL) or data.get("provider_name") != PROVIDER_NAME:
        raise ValueError("served model/provider mismatch")
    cost = Decimal(str(data["total_cost"]))
    if not cost.is_finite() or cost < 0 or cost > Decimal(row["reserved_usd"]):
        raise ValueError("certified cost invalid or above reservation")
    return cost


def row_cost(row):
    """Verified cost, certified transport cost, or the full reservation."""
    if row.get("verified_cost_usd"):
        return Decimal(row["verified_cost_usd"])
    if row.get("certified_cost_usd"):
        return Decimal(row["certified_cost_usd"])
    return Decimal(row["reserved_usd"])


class Backend:
    def __init__(self, store, secret, phase, transport=None, generation=None):
        self.store, self.secret, self.phase = store, secret, phase
        self.transport = transport or stream_transmit
        self.generation = generation or fetch_generation
        self.halt = None

    def stop_path(self):
        return self.store.root.parent / "batch_stop.json"

    def rows(self):
        return [json.loads(p.read_text()) for p in (self.store.root / "calls").glob("*.json")]

    def guard(self, reserve):
        rows = self.rows()
        limit_calls, limit_usd = LIMITS[self.phase]
        if len(rows) >= limit_calls:
            raise base.Halt("authorized phase call limit reached")
        if sum((row_cost(r) for r in rows), Decimal(0)) + reserve > limit_usd:
            raise base.Halt("authorized phase spending ceiling reached")

    def batch_stop(self, key):
        with base.admission_lock(self.store.root):
            try:
                with self.stop_path().open("x") as stream:
                    json.dump(dict(shard=self.store.root.name, call_key=key, created_unix=time.time()), stream)
            except FileExistsError:
                pass

    def fail(self, reason, key=None, batch=False):
        self.halt = reason
        if batch:
            self.batch_stop(key)
        raise base.Halt(reason)

    def call(self, case):
        request = request_for(case)
        for attempt in (1, 2):
            key = digest(dict(request=request, phase=self.phase, protocol=self.store.protocol_hash, attempt=attempt))
            path = self.store.root / "calls" / (key + ".json")
            if path.exists():
                row = json.loads(path.read_text())
                if row["status"] != "recorded":
                    self.fail("interrupted call is never regenerated")
                if row.get("outcome") == "transport_certified":
                    if attempt == 1:
                        continue
                    raise TransportFailed("transport failed on both declared attempts")
                if row.get("accounting_error"):
                    self.fail(row["accounting_error"])
                return key, row
            if self.stop_path().exists():
                self.fail("coordinated batch safety halt")
            try:
                bound, reserve = base.reserve_for(request)
                self.guard(reserve)
            except base.Halt as exc:
                self.fail(str(exc))
            wire = base.encoded_request(request)
            row = dict(request=request, request_text=wire, phase=self.phase, attempt=attempt,
                       protocol_hash=self.store.protocol_hash, input_token_bound=bound,
                       reserved_usd=str(reserve), started_unix=time.time(), status="started")
            with base.admission_lock(self.store.root):
                if self.stop_path().exists():
                    self.fail("coordinated batch safety halt")
                self.store.save("calls", key, row)
            sent = self.transport(wire, self.secret)
            text = "\n".join(sent["lines"])
            redacted = self.secret in text
            lines = [l.replace(self.secret, "[REDACTED_CREDENTIAL]") for l in sent["lines"]]
            row.update(status="recorded", http_status=sent["http_status"], stream_lines=lines,
                       generation_id=sent["generation_id"], secret_redacted=redacted,
                       elapsed_seconds=time.time() - row["started_unix"])
            if sent["error"]:
                row["transport_error"] = sent["error"]
            try:
                response, complete = assemble(lines) if sent["http_status"] == 200 else ({}, False)
            except (ValueError, TypeError):
                response, complete = {}, False
            row["response"] = response
            if response.get("id") and not row["generation_id"]:
                row["generation_id"] = response["id"]
            if complete and not sent["error"] and not redacted:
                try:
                    row["verified_cost_usd"] = str(base.accounting(row))
                    row["outcome"] = "answered"
                except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                    row["accounting_error"] = type(exc).__name__ + ": " + str(exc)
                    self.store.save("calls", key, row)
                    self.fail("transport/accounting/routing failure", key,
                              batch="mismatch" in str(exc))
                self.store.save("calls", key, row)
                self._log(case, row)
                return key, row
            # Incomplete stream: certify the charge, then the single declared re-issue.
            try:
                if redacted:
                    raise ValueError("credential echo")
                cost = certify(self.generation(row["generation_id"], self.secret)
                               if row["generation_id"] else None, row)
                row.update(certified_cost_usd=str(cost), outcome="transport_certified")
                self.store.save("calls", key, row)
                self._log(case, row)
            except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                row["accounting_error"] = type(exc).__name__ + ": " + str(exc)
                self.store.save("calls", key, row)
                self.fail("uncertified transport failure; reservation retained", key,
                          batch="mismatch" in str(exc))
        raise TransportFailed("transport failed on both declared attempts")

    def _log(self, case, row):
        usage = (row.get("response") or {}).get("usage") or {}
        print("CALL", self.phase, case["name"], "attempt", row["attempt"], row.get("outcome"),
              "tokens", usage.get("completion_tokens"),
              "cost", row.get("verified_cost_usd") or row.get("certified_cost_usd"), flush=True)


def answer(backend, case):
    key, row = backend.call(case)
    try:
        return key, base.checked_answer(row)
    except (KeyError, TypeError, IndexError, ArithmeticError) as exc:
        raise ValueError("invalid API answer: " + type(exc).__name__) from None


# ---------------------------------------------------------------- gate

def gate_cases():
    """Eight private lottery-comprehension checks; fixed history, fair undrawn rule."""
    cases = []
    for majority in ("policy_k", "policy_m"):
        for leader in ("policy_k", "policy_m"):
            for flip in (False, True):
                utilities = dict(policy_k=-3 if flip else 7, policy_m=6 if flip else -2, q=0)
                other = "policy_m" if majority == "policy_k" else "policy_k"
                ballots = {r: majority if i < 4 else other for i, r in enumerate(game.ROLES)}
                selected = dict(D=leader, B=majority)
                expected_utility = Decimal(utilities[selected["D"]] + utilities[selected["B"]]) / 2
                context = dict(representative="r3", leader="r0", sponsor="r1", locked_proposal="policy_k",
                               amendment="policy_m", pairwise_ballots=ballots, leader_choice=leader,
                               own_principal_utilities=utilities)
                system = ("You are representative r3, entrusted to maximize principal r3's final policy utility. "
                          + late.rules_late(None) + " " + game.FINAL)
                task = ("This is a private interface check of an already supplied voting history; the rule has not "
                        "been drawn. Assume whichever candidate is selected is enacted. Report which candidate would "
                        "be selected under the leader rule and under the ballot rule, and your principal's expected "
                        "utility before the fair draw. Return exactly selected_if_leader_rule (string), "
                        "selected_if_ballot_rule (string) and expected_utility (string holding the exact decimal value, e.g. \"12.5\").")
                n = len(cases)
                cases.append(dict(name=f"lottery{n}", seed=GATE_SEED + n,
                    messages=[dict(role="system", content=system),
                              dict(role="user", content=json.dumps(context, sort_keys=True) + "\n" + task)],
                    expected=dict(selected_if_leader_rule=selected["D"], selected_if_ballot_rule=selected["B"],
                                  expected_utility=str(expected_utility))))
    return cases


def gate_score(raw, expected):
    try:
        value = game.decode(raw)
        if set(value) != set(expected):
            raise ValueError("wrong keys")
        eu = value["expected_utility"]
        if type(eu) is not str or type(value["selected_if_leader_rule"]) is not str \
                or type(value["selected_if_ballot_rule"]) is not str:
            raise ValueError("wrong types")
        exact = (value["selected_if_leader_rule"] == expected["selected_if_leader_rule"]
                 and value["selected_if_ballot_rule"] == expected["selected_if_ballot_rule"]
                 and Decimal(eu.strip()) == Decimal(expected["expected_utility"]))
        return dict(status="completed", valid=True, exact=exact, reply=value)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        return dict(status="failed", valid=False, exact=False, error=str(exc))


# ---------------------------------------------------------------- episodes

def run_early(backend, profile, arm, seed):
    keys = []
    def ask(messages):
        if len(keys) >= 25:
            raise ValueError("episode decision cap reached")
        key, raw = answer(backend, case_for(messages, seed + len(keys)))
        keys.append(key)
        return raw
    result = game.run_episode(profile, arm, ask)
    return dict(result, call_keys=keys)


def run_late_condition(backend, profile, order, seed):
    keys = []
    def ask(messages, position):
        key, raw = answer(backend, case_for(messages, seed + position))
        keys.append(key)
        return raw
    result = late.run_late(profile, ask, tuple(order))
    return dict(result, call_keys=keys)


def protocol(index=None):
    selection, seeds = frame()
    shared = dict(name=NAME, model=MODEL, provider=PROVIDER_NAME,
        endpoint_snapshot=json.loads((ROOT / "paper3/deepseek_provider_snapshot.json").read_text()),
        inference=request_for(case_for(game.messages(generated_profile(seeds[0]), "D",
            generated_profile(seeds[0])["leader"], "opening", []), SEED_BASE)),
        profile_selection=selection, profiles=[generated_profile(s) for s in seeds],
        disclosure_benchmarks={str(s): disclosure_benchmark(generated_profile(s)) for s in seeds},
        rules_late_undrawn=late.rules_late(None), rules_late_drawn={a: late.rules_late(a) for a in game.ARMS},
        design="per profile: early D (25), early B (25), late prefix under public 1/2 lottery (9) cloned into D and B "
               "continuations (16 each) = 91 unique decisions; every path has 25 decisions; shared seeds "
               f"{SEED_BASE}+1000*index+position across all four paths; run order rotated by index",
        estimand="primary: (late B - late D) - (early B - early D) in enacted mean normalized regret and leader "
                 "advantage, with all principal utilities; plus locked-proposal choices early D/B vs late. Late D/B "
                 "prefixes are identical by construction; that zero is not a finding. Branches share history; "
                 "authority x information-timing interaction, not natural mediation",
        strata="two positive-information profiles and two zero-information controls chosen by the frozen theory-only "
               "rule before any call; profiles are the experimental units",
        gate="8 fresh lottery-comprehension checks at the same cap; all 8 valid and exact required before episodes; "
             "the inherited plain selector gate (16/16 valid, 12/12 exact) remains a prerequisite",
        transport_policy=__doc__.split("Transport, declared prospectively", 1)[1].strip(),
        failure_policy="invalid action ends that episode or branch; prefix failure fails both late branches; no "
                       "imputation of unobserved outcomes; failed profiles are retained and reported with finite-menu bounds",
        budget=dict(prior_additional_usd=str(PRIOR_ADDITIONAL_USD), gate=dict(calls=8, usd="0.10"),
                    per_profile=dict(calls=120, usd="0.60"), shards=SHARDS,
                    maximum_total_usd=str(LIMITS["gate"][1] + SHARDS * LIMITS["episodes"][1]),
                    authorization="Fuad approved option (b) on 2026-09-22 within the cumulative $10 additional allowance"),
        scope="discovery pilot, not confirmation; no automatic follow-on or replacement profiles",
        rerun_of="deepseek_disclosure_a2: gate 8/8, 166 calls, 0/4 complete profiles from local network outages; archive SHA-256 a630b560534ea3d6393228f0ec66f2b7929e3c5c1191b1c4295b2b42503028bc; fresh seeds, same profiles, disclosed as a replication attempt",
        predecessor="deepseek_disclosure_a1 gate failed 6/8 (protocol 162e359b301e860a5ddffc8e29603219165af9a472b01de08777adf4ca7ae73f); preserved unchanged; only the gate answer encoding differs",
        shard=index)
    if PRIOR_ADDITIONAL_USD + LIMITS["gate"][1] + SHARDS * LIMITS["episodes"][1] > AUTHORIZED_USD:
        raise base.Halt("allocation would exceed cumulative $10 authorization")
    return shared


SOURCES = [Path(__file__).resolve(), ROOT / "experiments/paper3_deepseek_disclosure.py",
           ROOT / "experiments/paper3_deepseek_disclosure_a2.py", ROOT / "tests/test_paper3_deepseek_disclosure_a3.py",
           ROOT / "analysis/paper3_deepseek_disclosure_audit.py", ROOT / "paper3/agenda_disclosure.py", ROOT / "paper3/agenda_rights.py",
           ROOT / "paper3/agenda_benchmarks.py", ROOT / "paper3/agenda_disclosure_benchmarks.py",
           ROOT / "paper3/audit_runtime.py", ROOT / "experiments/paper3_deepseek_fresh_profiles.py",
           ROOT / "experiments/paper3_bonsai_structured_agenda.py", ROOT / "experiments/paper3_bonsai_format_gate.py",
           ROOT / "paper3/deepseek_provider_snapshot.json", ROOT / "tests/test_paper3_agenda_disclosure.py",
           ROOT / "tests/test_paper3_deepseek_disclosure.py"]


def open_store(root, index):
    store = PilotStore(root, protocol(index), SOURCES)
    if not (root / "sources.json").exists():
        with (root / "sources.json").open("x") as stream:
            json.dump({str(p.relative_to(ROOT)): p.read_text() for p in SOURCES}, stream, indent=2)
    return store


def run_gate(root, secret, transport=None, generation=None):
    store = open_store(root / "gate", None)
    terminal = root / "gate" / "sessions" / "terminal.json"
    if terminal.exists():
        return json.loads(terminal.read_text())
    backend = Backend(store, secret, "gate", transport, generation)
    results = []
    for case in gate_cases():
        try:
            key, raw = answer(backend, case)
            result = dict(gate_score(raw, case["expected"]), name=case["name"], call_key=key)
        except TransportFailed as exc:
            result = dict(status="failed", valid=False, exact=False, error=str(exc), name=case["name"])
        except base.Halt:
            break
        except ValueError as exc:
            result = dict(status="failed", valid=False, exact=False, error=str(exc), name=case["name"])
        store.save("sessions", case["name"], result)
        results.append(result)
        print("CHECK", case["name"], result["valid"], result["exact"], flush=True)
    passed = len(results) == 8 and all(r["valid"] and r["exact"] for r in results)
    out = dict(protocol_hash=store.protocol_hash, passed=passed, checks=len(results),
               valid=sum(r["valid"] for r in results), exact=sum(r["exact"] for r in results), halt=backend.halt,
               accounted_usd=str(sum((row_cost(r) for r in backend.rows()), Decimal(0))))
    store.save("sessions", "terminal", out)
    print("GATE", json.dumps(out), flush=True)
    return out


def run_shard(root, index, secret, transport=None, generation=None):
    gate = root / "gate" / "sessions" / "terminal.json"
    if not gate.exists() or not json.loads(gate.read_text())["passed"]:
        raise base.Halt("lottery gate has not passed")
    inherited = json.loads((ROOT / "results/paper3/deepseek_plain_agenda_a1/sessions/terminal.json").read_text())
    if not inherited["gate_passed"]:
        raise base.Halt("inherited selector gate missing")
    shard = root / f"profile-{index}"
    store = open_store(shard, index)
    if (shard / "sessions" / "terminal.json").exists():
        return json.loads((shard / "sessions" / "terminal.json").read_text())
    if any(json.loads(p.read_text())["status"] == "started" for p in (shard / "calls").glob("*.json")):
        raise base.Halt("interrupted call requires inspection; never regenerate")
    _, seeds = frame()
    profile = generated_profile(seeds[index])
    seed = SEED_BASE + 1000 * index
    backend = Backend(store, secret, "episodes", transport, generation)
    conditions = {}
    for condition, arm in schedule(index):
        name = f"{condition}-{arm}"
        path = shard / "sessions" / (name + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            print("EPISODE START", profile["name"], name, flush=True)
            result = (run_early(backend, profile, arm, seed) if condition == "early"
                      else run_late_condition(backend, profile, arm, seed))
            result = dict(result, condition=condition, arm=arm, halt=backend.halt)
            store.save("sessions", name, result)
        conditions[name] = result["status"]
        print("EPISODE", name, result["status"], flush=True)
        if backend.halt:
            break
    terminal = dict(protocol_hash=store.protocol_hash, profile=profile["name"], conditions=conditions,
                    halt=backend.halt, calls=len(backend.rows()),
                    accounted_usd=str(sum((row_cost(r) for r in backend.rows()), Decimal(0))))
    store.save("sessions", "terminal", terminal)
    print("TERMINAL", json.dumps(terminal), "No automatic follow-on", flush=True)
    return terminal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--gate", action="store_true")
    group.add_argument("--index", type=int, choices=range(SHARDS))
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.freeze_only:
        for index in [None] + list(range(SHARDS)):
            store = open_store(args.output / ("gate" if index is None else f"profile-{index}"), index)
            print("FROZEN", "gate" if index is None else index, store.protocol_hash, flush=True)
        return
    secret = base.read_key()
    if args.gate:
        run_gate(args.output, secret)
    else:
        run_shard(args.output, args.index, secret)


if __name__ == "__main__":
    main()
