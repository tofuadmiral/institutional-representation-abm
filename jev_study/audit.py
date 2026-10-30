"""Read raw Jev outputs; keep invalid requests out of probability scores, not counts."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jev_study.bill_choice import score
from jev_study.run import RATE
from paper3.audit_runtime import digest


def audit(root):
    manifest = json.loads((root / "manifest.json").read_text())
    protocol_hash = digest(manifest)
    groups, pairs = defaultdict(list), defaultdict(dict)
    errors, wrong, tokens, not_run = [], [], 0, 0
    for case, wire in zip(manifest["protocol"]["cases"], manifest["protocol"]["wire_requests"]):
        path = root / "calls" / (case["name"] + ".json")
        if not path.exists():
            not_run += 1
            continue
        call = json.loads(path.read_text())
        if call["wire_request"] != wire or call["protocol_hash"] != protocol_hash:
            raise ValueError("raw request provenance mismatch")
        row = dict(case=case["name"], valid=False)
        try:
            response = json.loads(call["response_text"])
            tokens += response.get("usage", {}).get("input_tokens", 0)
            if response["model"] != manifest["protocol"]["model"]:
                raise ValueError("model mismatch")
            metrics = score(case, response)
            row.update(valid=True, **metrics)
            if not metrics["correct"]:
                wrong.append(dict(case=case["name"], expected=case["expected"],
                    choice=response["answers"]["bill"]["choice"],
                    probability=metrics["selected_probability"], loss=metrics["stipulated_priority_loss"]))
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(dict(case=case["name"], error_type=type(exc).__name__))
        groups[case["arm"]].append(row)
        pairs[case["base_seed"]][case["arm"]] = row
    summary = {}
    for arm, rows in groups.items():
        valid = [r for r in rows if r["valid"]]
        summary[arm] = dict(n=len(rows), valid=len(valid), correct=sum(r["correct"] for r in valid),
            mean_brier=sum(r["brier"] for r in valid)/len(valid) if valid else None,
            infinite_log_loss_count=sum(r["infinite_log_loss"] for r in valid),
            mean_selected_probability=sum(r["selected_probability"] for r in valid)/len(valid) if valid else None,
            probability_at_least_90_count=sum(r["selected_probability"] >= .9 for r in valid),
            probability_at_least_90_errors=sum(r["selected_probability"] >= .9 and not r["correct"] for r in valid))
    contrasts = {}
    for arm in ("reverse_order", "relabel", "nonbinding_endorsement"):
        comparable = [(p["plain"], p[arm]) for p in pairs.values()
                      if "plain" in p and arm in p and p["plain"]["valid"] and p[arm]["valid"]]
        contrasts[arm] = dict(pairs=len(comparable),
            policy_changes=sum(a["chosen_policy_index"] != b["chosen_policy_index"] for a,b in comparable),
            repairs=sum(not a["correct"] and b["correct"] for a,b in comparable),
            corruptions=sum(a["correct"] and not b["correct"] for a,b in comparable))
    return dict(protocol_hash=protocol_hash, not_run=not_run, arms=summary, paired_contrasts=contrasts,
        failures=errors, wrong=wrong, input_tokens=tokens, estimated_cost_usd=tokens*RATE,
        caveat="Paired presentations are dependent. Price-based estimate is not an account billing receipt.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    print(json.dumps(audit(parser.parse_args().root), indent=2))
