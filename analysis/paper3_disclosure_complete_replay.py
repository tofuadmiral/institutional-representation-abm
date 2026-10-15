"""Offline supplemental provenance check for COMPLETE, no-reissue disclosure a3.

Does not modify frozen runners, manifests, records or archives. This deliberately
does not certify interrupted a1/a2 runs or transport-reissue billing. Requires the
matching local source tree; not a portable clean-clone reproduction claim.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from experiments import paper3_deepseek_disclosure_a3 as run
from paper3.audit_runtime import digest


def load(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


class ReplayBackend:
    """Only return stored completions after reconstructing exact request bytes."""

    def __init__(self, records, protocol_hash, phase):
        self.records, self.protocol_hash, self.phase = records, protocol_hash, phase
        self.used = []

    def call(self, case):
        request = run.request_for(case)
        key = digest(dict(request=request, phase=self.phase,
                          protocol=self.protocol_hash, attempt=1))
        require(key in self.records, "missing exact request: " + key)
        row = self.records[key]
        require(row["request"] == request, "request object mismatch")
        require(row["request_text"] == run.base.encoded_request(request),
                "serialized request mismatch")
        self.used.append(key)
        return key, row


def verify_record(key, row, ph, phase):
    require(row["status"] == "recorded" and row["outcome"] == "answered"
            and row["attempt"] == 1, "unsupported incomplete/reissue record")
    require(row["protocol_hash"] == ph and row["phase"] == phase, "record protocol/phase mismatch")
    require(key == digest(dict(request=row["request"], phase=phase, protocol=ph, attempt=1)),
            "record key mismatch")
    require(json.loads(row["request_text"]) == row["request"], "wire/object mismatch")
    require(row["http_status"] == 200 and not row.get("transport_error")
            and not row.get("secret_redacted") and not row.get("accounting_error"), "call error")
    response, complete = run.assemble(row["stream_lines"])
    require(complete and response == row["response"], "stream/response mismatch")
    require(row["generation_id"] == response["id"], "generation id mismatch")
    bound, reserve = run.base.reserve_for(row["request"])
    require(row["input_token_bound"] == bound and Decimal(row["reserved_usd"]) == reserve,
            "reservation mismatch")
    cost = run.base.accounting(row)
    require(Decimal(row["verified_cost_usd"]) == cost, "verified cost mismatch")
    run.base.checked_answer(row)  # normal stop, native reasoning evidence, no tools
    require(row["started_unix"] > 0 and row["elapsed_seconds"] >= 0, "invalid timestamps")
    return cost


def verify_shard(root, index):
    manifest = load(root / "manifest.json")
    require(manifest["protocol"] == run.protocol(index), "frozen protocol mismatch")
    snapshots = load(root / "sources.json")
    expected_sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in run.SOURCES}
    require(manifest["sources"] == expected_sources, "frozen source hashes mismatch")
    require(set(snapshots) == {str(p.relative_to(run.ROOT)) for p in run.SOURCES},
            "source snapshot inventory mismatch")
    for p in run.SOURCES:
        require(hashlib.sha256(snapshots[str(p.relative_to(run.ROOT))].encode()).hexdigest()
                == expected_sources[str(p)], "source snapshot mismatch: " + str(p))
    ph = digest(manifest)
    records = {p.stem: load(p) for p in (root / "calls").glob("*.json")}
    sessions = {p.stem: load(p) for p in (root / "sessions").glob("*.json")}
    phase = "gate" if index is None else "episodes"
    cost = sum((verify_record(k, r, ph, phase) for k, r in records.items()), Decimal(0))
    backend = ReplayBackend(records, ph, phase)
    if index is None:
        expected_names = {"terminal"}
        checks = []
        for case in run.gate_cases():
            key, raw = run.answer(backend, case)
            scored = dict(run.gate_score(raw, case["expected"]), name=case["name"], call_key=key)
            require(sessions[case["name"]] == scored, "gate score mismatch")
            checks.append(scored)
            expected_names.add(case["name"])
        terminal = dict(protocol_hash=ph, passed=all(c["valid"] and c["exact"] for c in checks),
                        checks=8, valid=sum(c["valid"] for c in checks),
                        exact=sum(c["exact"] for c in checks), halt=None, accounted_usd=str(cost))
        require(terminal["passed"], "gate did not pass")
    else:
        profile = run.generated_profile(run.frame()[1][index])
        seed = run.SEED_BASE + 1000 * index
        conditions, expected_names = {}, {"terminal"}
        for condition, arm in run.schedule(index):
            name = f"{condition}-{arm}"
            result = (run.run_early(backend, profile, arm, seed) if condition == "early"
                      else run.run_late_condition(backend, profile, arm, seed))
            expected = dict(result, condition=condition, arm=arm, halt=None)
            require(result["status"] == "completed", "not a complete episode: " + name)
            require(sessions[name] == expected, "exact episode replay mismatch: " + name)
            conditions[name] = result["status"]
            expected_names.add(name)
        terminal = dict(protocol_hash=ph, profile=profile["name"], conditions=conditions,
                        halt=None, calls=len(records), accounted_usd=str(cost))
    require(set(sessions) == expected_names, "session inventory mismatch")
    require(sessions["terminal"] == terminal, "terminal mismatch")
    require(Counter(backend.used) == Counter({k: 1 for k in records}),
            "unattached or duplicate calls")
    require(len(records) == (8 if index is None else 91), "call count mismatch")
    prior = Decimal(0)
    for key in backend.used:
        row = records[key]
        require(prior + Decimal(row["reserved_usd"]) <= run.LIMITS[phase][1],
                "pre-request spending cap exceeded")
        prior += Decimal(row["verified_cost_usd"])
    ordered = [records[k] for k in backend.used]
    require(all(b["started_unix"] >= a["started_unix"] + a["elapsed_seconds"]
                for a, b in zip(ordered, ordered[1:])), "overlapping/out-of-order shard requests")
    require(not list(root.rglob("*.partial")), "partial writes present")
    return dict(calls=len(records), accounted_usd=str(cost), protocol_hash=ph)


def audit(root):
    root = Path(root)
    errors, shards = [], {}
    expected = {"gate"} | {f"profile-{i}" for i in range(run.SHARDS)}
    found = {p.name for p in root.glob("profile-*") if p.is_dir()} | ({"gate"} if (root / "gate").is_dir() else set())
    if found != expected:
        errors.append("shard inventory mismatch")
    for index in [None] + list(range(run.SHARDS)):
        name = "gate" if index is None else f"profile-{index}"
        try:
            shards[name] = verify_shard(root / name, index)
        except (ValueError, KeyError, TypeError, IndexError, OSError, ArithmeticError) as exc:
            errors.append(name + ": " + str(exc))
    total = sum((Decimal(s["accounted_usd"]) for s in shards.values()), Decimal(0))
    if run.PRIOR_ADDITIONAL_USD + total > run.AUTHORIZED_USD:
        errors.append("cumulative authorization exceeded")
    if (root / "batch_stop.json").exists():
        errors.append("unexpected batch stop for complete no-reissue audit")
    return dict(integrity_errors=errors, shards=shards,
                calls=sum(s["calls"] for s in shards.values()),
                verified_shard_cost_usd=str(total),
                cumulative_additional_usd=str(run.PRIOR_ADDITIONAL_USD + total),
                scope="Supplemental complete-a3 exact request/action/stream replay, matching local sources; "
                      "not a portable audit, provider-internal verification, or certification of failed predecessors.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    result = audit(parser.parse_args().root)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["integrity_errors"]))
