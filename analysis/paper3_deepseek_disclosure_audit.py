"""Read-only audit and readout for results/paper3/deepseek_disclosure_a2 (gate a1 failed and is preserved separately).

Integrity: every call row recorded (none left started), costs verified or
certified, session call keys exist, resolutions recomputed from recorded
actions. Readout: per-profile locked proposals and enacted outcomes in all four
cells, the frozen interaction contrast (paper3.agenda_disclosure.interaction)
for complete profiles, and finite-menu bounds for incomplete ones. Descriptive
discovery only; branches share a prefix; profiles are the units.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper3 import agenda_rights as game
from paper3 import agenda_disclosure as late
from paper3.agenda_benchmarks import generated_profile
from paper3.agenda_disclosure_benchmarks import disclosure_benchmark
import importlib

RUNNERS = {"deepseek-authority-disclosure-pilot-a2": "experiments.paper3_deepseek_disclosure_a2",
           "deepseek-authority-disclosure-pilot-a3": "experiments.paper3_deepseek_disclosure_a3"}


def runner_for(root):
    """Pick the runner whose frozen protocol produced this run (default a2)."""
    manifest = Path(root) / "gate" / "manifest.json"
    name = json.loads(manifest.read_text())["protocol"]["name"] if manifest.exists() else None
    return importlib.import_module(RUNNERS.get(name, RUNNERS["deepseek-authority-disclosure-pilot-a2"]))


def load(path):
    return json.loads(path.read_text())


def recompute(profile, arm, actions):
    stage = lambda name: [a for a in actions if a["stage"] == name]
    proposal = stage("locked_proposal")[0]["action"]["policy_id"]
    amendment = stage("amendment")[0]["action"]["policy_id"]
    ballots = {a["actor"]: a["action"]["policy_id"] for a in stage("pairwise")}
    choice = stage("leader_selection")[0]["action"]["policy_id"]
    cards = {a["actor"]: a["action"]["votes"] for a in stage("ratification")}
    return game.resolve(profile, arm, proposal, amendment, ballots, choice, cards)


def bounds(profile, outcomes):
    """Finite-menu bounds of the interaction over every unobserved enacted policy."""
    menu = [p["policy_id"] for p in profile["catalog"]]
    cells = [(c, a) for c in ("early", "late") for a in game.ARMS]
    options = [[outcomes[c][a]] if a in outcomes.get(c, {}) else menu for c, a in cells]
    values = {"mean_regret": [], "leader_advantage": []}
    def walk(i, chosen):
        if i == len(cells):
            filled = {"early": {}, "late": {}}
            for (c, a), p in zip(cells, chosen):
                filled[c][a] = p
            result = late.interaction(profile, filled)
            values["mean_regret"].append(result["mean_regret_interaction"])
            values["leader_advantage"].append(result["leader_advantage_interaction"])
            return
        for p in options[i]:
            walk(i + 1, chosen + [p])
    walk(0, [])
    return {k: [min(v), max(v)] for k, v in values.items()}


def audit(root):
    root = Path(root)
    run = runner_for(root)
    errors, calls, spent, transport_reissues, profiles = [], 0, Decimal(0), 0, {}
    gate = load(root / "gate/sessions/terminal.json") if (root / "gate/sessions/terminal.json").exists() else None
    for shard in sorted([root / "gate"] + sorted(root.glob("profile-*"))):
        for path in (shard / "calls").glob("*.json"):
            row = load(path)
            calls += 1
            if row["status"] != "recorded":
                errors.append(f"{shard.name}: unrecorded call {path.stem}")
                continue
            if row.get("secret_redacted"):
                errors.append(f"{shard.name}: credential echo {path.stem}")
            if row.get("outcome") == "transport_certified":
                transport_reissues += 1
            elif row.get("outcome") != "answered" and not row.get("accounting_error"):
                errors.append(f"{shard.name}: unknown call outcome {path.stem}")
            spent += run.row_cost(row)
    _, seeds = run.frame()
    selection = late.select_profiles()
    for index, seed in enumerate(seeds):
        shard = root / f"profile-{index}"
        profile = generated_profile(seed)
        stratum = "positive" if seed in selection["positive"] else "zero_control"
        benchmark = disclosure_benchmark(profile)
        cell = {"early": {}, "late": {}}
        locked, statuses = {}, {}
        for path in sorted((shard / "sessions").glob("*.json")) if shard.exists() else []:
            if path.stem == "terminal":
                continue
            session = load(path)
            for key in session.get("call_keys", []):
                if not (shard / "calls" / (key + ".json")).exists():
                    errors.append(f"{shard.name}: missing call row {key}")
            if session["condition"] == "early":
                arm = session["arm"]
                statuses[f"early-{arm}"] = session["status"]
                acts = session.get("actions", [])
                if any(a["stage"] == "locked_proposal" for a in acts):
                    locked[f"early-{arm}"] = next(a for a in acts if a["stage"] == "locked_proposal")["action"]["policy_id"]
                if session["status"] == "completed":
                    if recompute(profile, arm, session["actions"]) != session["resolution"]:
                        errors.append(f"{shard.name}: early-{arm} resolution mismatch")
                    cell["early"][arm] = session["resolution"]["outcome"]
            else:
                if session.get("locked_proposal"):
                    locked["late"] = session["locked_proposal"]
                for arm, branch in session.get("branches", {}).items():
                    statuses[f"late-{arm}"] = branch["status"]
                    if branch["status"] == "completed":
                        if branch["actions"][:9] != session["prefix_actions"]:
                            errors.append(f"{shard.name}: late-{arm} prefix differs from shared prefix")
                        if recompute(profile, arm, branch["actions"]) != branch["resolution"]:
                            errors.append(f"{shard.name}: late-{arm} resolution mismatch")
                        cell["late"][arm] = branch["resolution"]["outcome"]
        complete = all(set(cell[c]) == set(game.ARMS) for c in cell)
        entry = dict(seed=seed, stratum=stratum, statuses=statuses, locked=locked, enacted=cell,
            theory=dict(early_own_best=benchmark["early_own_best_proposals"],
                        late_own_best=benchmark["late_own_best_proposals"],
                        normalized_information_value=benchmark["leader_value_of_information_normalized_exact"]),
            locked_matches_theory=dict(
                {f"early-{a}": locked.get(f"early-{a}") in benchmark["early_own_best_proposals"][a]
                 for a in game.ARMS if f"early-{a}" in locked},
                **({"late": locked["late"] in benchmark["late_own_best_proposals"]} if "late" in locked else {})),
            complete=complete)
        if complete:
            result = late.interaction(profile, cell)
            entry["interaction"] = {k: v for k, v in result.items() if k != "outcomes"}
        entry["interaction_bounds"] = bounds(profile, cell)
        profiles[str(index)] = entry
    by_stratum = {}
    for entry in profiles.values():
        if entry["complete"]:
            by_stratum.setdefault(entry["stratum"], []).append(entry["interaction"]["mean_regret_interaction"])
    return dict(integrity_errors=errors, calls=calls, transport_reissues=transport_reissues,
        accounted_usd=str(spent), cumulative_additional_usd=str(run.PRIOR_ADDITIONAL_USD + spent),
        gate=gate, profiles=profiles, complete_profiles=sum(e["complete"] for e in profiles.values()),
        stratum_mean_regret_interaction={k: sum(v) / len(v) for k, v in by_stratum.items()},
        scope="discovery pilot; four theory-selected profiles; branch continuations share the prefix; "
              "bounds are finite-menu missingness bounds, not confidence intervals; no causal-mediation claim")


def archive(root, target):  # noqa: E302
    root, target = Path(root), Path(target)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.name.endswith(".lock"):
                z.write(path, path.relative_to(root.parent))
    return hashlib.sha256(target.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    report = audit(args.root)
    if args.archive:
        report = dict(report, archive=str(args.archive), archive_sha256=archive(args.root, args.archive))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
