"""Read-only raw-response audit; descriptive, not a confirmatory analysis."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3.audit_runtime import digest
from paper3.commitment_memory import parse
from paper3.native_inference import final_answer as ministral_final
from experiments.paper3_bonsai_validation import final_answer as bonsai_final
from experiments.paper3_pivotal_budget import replay_checks


def design_coverage(cases):
    """Describe task opportunities, not model outcomes or independent sample size."""
    bases = {}
    for case in cases:
        key = case.get("base_case", case["name"])
        if key not in bases:
            bases[key] = dict(base_case=key, expected=case["expected"], views=[])
        bases[key]["views"].append(case.get("view"))
    rows = list(bases.values())
    return dict(base_cases=len(rows),
        costly_due_cases=sum(r["expected"]["obligation_due"] and
                            r["expected"]["current_project_utility"] < 0 for r in rows),
        costly_unbound_cases=sum(not r["expected"]["obligation_due"] and
                                r["expected"]["current_project_utility"] < 0 for r in rows),
        profitable_cases=sum(r["expected"]["current_project_utility"] > 0 for r in rows),
        rows=rows)


def audit(root, parent=None):
    manifest = json.loads((root / "manifest.json").read_text())
    protocol = manifest["protocol"]
    expected_hash = digest(manifest)
    extract = bonsai_final if protocol["name"].startswith("bonsai2") else ministral_final
    stages = protocol.get("stages", {"pivotal": protocol.get("cases", [])})
    counts, by_view = defaultdict(Counter), defaultdict(Counter)
    rows, integrity = [], []
    for stage, cases in stages.items():
        for case in cases:
            path = root / "sessions" / (case["name"] + ".json")
            if not path.exists():
                counts[stage]["not_run"] += 1
                continue
            saved = json.loads(path.read_text())
            if saved["protocol_hash"] != expected_hash or saved["expected"] != case["expected"]:
                integrity.append(case["name"] + ": session provenance mismatch")
            call = json.loads((root / "calls" / (saved["call_keys"][0] + ".json")).read_text())
            if call["protocol_hash"] != expected_hash or call["request"]["messages"] != case["messages"]:
                integrity.append(case["name"] + ": request provenance mismatch")
            choice = call["response"]["choices"][0]
            valid, reply = False, None
            try:
                if choice["finish_reason"] != "stop":
                    raise ValueError("not normally terminated")
                schema = {k: {"bool": bool, "str": str, "int": int}[t] for k, t in case["schema"].items()}
                reply = parse(extract(choice["message"]["content"]), schema)
                valid = True
            except ValueError:
                pass
            exact = valid and reply == case["expected"]
            if (valid != (saved["status"] == "completed") or exact != saved["exact"]
                    or valid and reply != saved["reply"]):
                integrity.append(case["name"] + ": saved score differs from raw response")
            metrics = dict(calls=1, valid=int(valid), exact=int(exact),
                length=int(choice["finish_reason"] == "length"),
                prompt_tokens=call["response"]["usage"]["prompt_tokens"],
                output_tokens=call["response"]["usage"]["completion_tokens"])
            row = dict(case=case["name"], valid=valid, exact=exact, finish=choice["finish_reason"],
                generated_tokens=metrics["output_tokens"], elapsed_seconds=call["elapsed_seconds"],
                peak_memory_gb=call["peak_memory_gb"])
            if stage == "pivotal":
                e = case["expected"]
                metrics.update(action_error=int(not valid or reply["vote"] != e["vote"]),
                    state_error=int(not valid or reply["obligation_due"] != e["obligation_due"]),
                    identity_error=int(not valid or reply["principal_id"] != e["principal_id"]),
                    utility_error=int(not valid or reply["current_project_utility"] != e["current_project_utility"]),
                    harmful_unbound_yes=int(valid and not e["obligation_due"] and e["current_project_utility"] < 0 and reply["vote"]),
                    due_no=int(valid and e["obligation_due"] and not reply["vote"]))
                if valid:
                    metrics.update(false_obligation=int(reply["obligation_due"] and not e["obligation_due"]),
                        missed_obligation=int(not reply["obligation_due"] and e["obligation_due"]),
                        state_error_correct_action=int(reply["obligation_due"] != e["obligation_due"] and reply["vote"] == e["vote"]),
                        action_error_correct_state=int(reply["obligation_due"] == e["obligation_due"] and reply["vote"] != e["vote"]))
                by_view[case["view"]].update(metrics)
                row.update(view=case["view"], expected=e, reply=reply,
                    marginal_payoff=e["current_project_utility"] * int(reply["vote"]) if valid else None)
            if parent:
                old_row = json.loads((parent / "sessions" / (case["name"] + ".json")).read_text())
                old = json.loads((parent / "calls" / (old_row["call_keys"][0] + ".json")).read_text())
                row["replay"] = replay_checks(old, call)
            counts[stage].update(metrics)
            rows.append(row)
    return dict(protocol_hash=expected_hash, stages=dict(counts), views=dict(by_view), integrity_errors=integrity,
        design_coverage=design_coverage(stages.get("pivotal", [])),
        replay_all_checks_pass=all(all(r["replay"].values()) for r in rows) if parent and rows else None,
        elapsed_generation_seconds=sum(r["elapsed_seconds"] for r in rows),
        peak_mlx_memory_gb=max((r["peak_memory_gb"] for r in rows), default=None), rows=rows,
        limitation="Descriptive audit of dependent synthetic fixtures; not a causal cross-model estimate or paper-quality result.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    report = audit(args.root, args.parent)
    if args.compact:
        report.pop("rows")
    print(json.dumps(report, indent=2))
