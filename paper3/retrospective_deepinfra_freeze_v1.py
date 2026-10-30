"""Fresh approved provider migration; old qualification is NOT inherited.

All sixteen assignments and both blocks are frozen before model answers.
The included first preassigned episode is the technical shakedown; no separate
paid gate, case replacement, weaker action parser or scientific-screen change.
"""
from fractions import Fraction
from functools import cache
import json
from pathlib import Path

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_anticipation_baselines as baselines
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_deepinfra_design_v1 as design
from paper3 import retrospective_deepinfra_route_v1 as route
from paper3 import retrospective_deepinfra_budget_v1 as budget
from paper3 import retrospective_deepinfra_retirement_v1 as retirement
from paper3 import retrospective_deepinfra_recovery_policy_v1 as policy
from paper3 import retrospective_deepinfra_failure_v1 as failure
from paper3.retrospective_source_closure import closure

FORMAT = design.FORMAT
AUTHORIZATION_FILE = "results/paper3/pivot_b_retrospective_deepinfra_pilot_v1_authorization.json"
AUTHORIZATION_SHA = retirement.AUTHORIZATION_SHA
RETIREMENT_PINS = {retirement.previous_retirement.STAGE: retirement.PREVIOUS_RETIREMENT_SHA}
READINESS_FILE = "results/paper3/pivot_b_retrospective_deepinfra_pilot_v1_preflight.json"
RUNNER_FILE = "experiments/paper3_retrospective_deepinfra_pilot_v1.py"
OLD_RUN = retirement.RUN


def authorization_check(repo):
    path = Path(repo) / AUTHORIZATION_FILE
    institution.require(not path.is_symlink() and journal._digest(path) == AUTHORIZATION_SHA,
                        "exact new human run/precision authority changed")
    record = journal.load(path)
    expected = dict(model=route.MODEL, provider=route.PROVIDER, endpoint=route.TAG,
        precision="fp4", economic_design_unchanged=True, assigned_episodes=16,
        logical_actions=480, maximum_physical_requests=560, workers=1,
        standalone_paid_qualification_calls=0, inherited_provider_qualification_pass=False,
        first_included_episode_is_technical_shakedown=True,
        both_blocks_conditionally_approved=True, first_term_primary=True,
        full_two_term_mandate_retained=True, accepted_actions_unchanged=True,
        both_directions_and_no_lead_accepted=True, pilot_cap_usd="9.00",
        total_authority_usd="19.00", automatic_successor_authorized=False,
        old_run_reopen_authorized=False, credit_purchases_authorized=False)
    institution.require(all(type(record[k]) is type(v) and record[k] == v for k,v in expected.items()),
                        "new bounded-attempt authority scope differs")
    return dict(path=AUTHORIZATION_FILE, sha256=AUTHORIZATION_SHA)


def readiness_pin_check(value):
    institution.require(type(value) is dict and set(value) == {"path", "sha256"} and
                        value["path"] == READINESS_FILE, "exact new readiness required")
    journal._protocol(value["sha256"])
    return dict(value)


@cache
def _specification_text():
    items = design.assignments()
    science.validate(items, {a["id"]:(None,None) for a in items})
    return journal.canonical(journal.encode(dict(format=FORMAT, assignments=items,
        bound=design.full_bound(), recovery=policy.specification(),
        primary="first_term_mean_normalized_district_regret_interaction",
        minimum_effect=Fraction(1,25), aligned_fraction=Fraction(1,2),
        model=route.MODEL, provider=route.PROVIDER, endpoint=route.TAG, quantization="fp4",
        output_bound=route.OUTPUT_BOUND, pilot_cap_usd="9.00", total_cap_usd="19.00",
        standalone_paid_qualification_calls=0, inherited_provider_qualification_pass=False,
        technical_shakedown="First included preassigned complete episode; not a separate paid gate.",
        resource_failure_policy=failure.VERSION, accepted_actions_unchanged=True,
        retirement_pins=RETIREMENT_PINS, migration_retirement_sha256=budget.MIGRATION_CERTIFICATE_SHA,
        continuation="Batch1 only after terminal batch0 without global safety stop, exact audit, "
            "unused-cap closure and actual isolated partial replay, regardless of effect. "
            "No successor, replacement cases, content repair or output-budget reduction.",
        workers=1, publication_evidence=False,
        limitation="Two selected conditional frames/one model/explicitly changed precision. "
            "Discovery only, not a provider comparison or intrinsic-motive claim. "
            "All failures, both horizons and seven-district/63-citizen harms remain.")))


def specification():
    return json.loads(_specification_text())


inventory = retirement.inventory


def source_roots(repo, operating_readiness=None):
    repo = Path(repo)
    roots = [repo / RUNNER_FILE, repo / "analysis/paper3_deepinfra_replay_v1.py",
        repo / "paper3/retrospective_deepinfra_freeze_v1.py",
        repo / "paper3/retrospective_deepinfra_operating_v1.py",
        repo / "analysis/paper3_contracts_archive.py", repo / AUTHORIZATION_FILE,
        repo / "requirements.txt"]
    ledger = repo / "results/paper3/pivot_b_budget"
    roots += [ledger / name for name in budget.AUTHORITY_FILES]
    roots += [ledger / retirement.DIRECTORY / (retirement.STAGE + ".json")]
    old = repo / OLD_RUN
    previous = journal.load(old / "manifest.json")
    institution.require(journal.physical.t.sha(journal.canonical(previous).encode()) == retirement.PROTOCOL,
                        "original terminal protocol changed")
    roots += [old / "manifest.json", old / "sources.json"]
    for name, expected in previous["sources"].items():
        path = repo / name
        institution.require(not path.is_symlink() and journal._digest(path) == expected,
                            "historical frozen source changed: " + name)
        roots.append(path)
    if operating_readiness is not None:
        from paper3 import retrospective_deepinfra_operating_v1 as operating
        pin = readiness_pin_check(operating_readiness)
        path = repo / pin["path"]
        institution.require(not path.is_symlink() and journal._digest(path) == pin["sha256"],
                            "new genuine readiness pin changed")
        roots.append(path)
        roots += [repo / arg for command in operating.REQUIRED_CHECKS.values()
                  for arg in command[3:] if arg.endswith(".py")]
    return roots


def prepare(root, repo, ledger_root, qualified_directory=None, qualified_zip=None, *,
            metadata, operating_readiness=None):
    root, repo = Path(root), Path(repo).resolve()
    institution.require(not root.exists(), "fresh migration only; never restart")
    authority = authorization_check(repo)
    route.check_endpoint(metadata)
    institution.require(operating_readiness is not None, "genuine new readiness required")
    from paper3 import retrospective_deepinfra_operating_v1 as operating
    pin = readiness_pin_check(operating_readiness)
    operating.readiness_check(repo, repo / pin["path"], pin["sha256"])
    ledger = budget.RecoveryLedger(ledger_root, retirement_pins=RETIREMENT_PINS)
    with ledger.locked():
        rows = ledger._entries()
        used, held = ledger._total(rows), ledger._commitments(rows)
        bound = budget.amount(design.full_bound()["full_reservation_usd"])
        institution.require(bound <= budget.amount("9") and used + held + bound <= budget.TOTAL_CAP,
                            "whole unchanged study does not fit; no partial allocation")
        prior = inventory(ledger_root)
        seeds = design.seed_audit(repo)
        mechanical = tuple(baselines.check_pair(pair) for pair in design.pairs())
        snapshots = {p.relative_to(repo).as_posix():p.read_text()
                     for p in closure(repo, source_roots(repo, pin))}
        manifest = dict(format=FORMAT, specification=specification(),
            sources={k:journal.physical.t.sha(v.encode()) for k,v in snapshots.items()},
            prior_entries=prior, pre_stage_accounted_usd=str(used),
            pre_stage_unused_commitments_usd=str(held), full_bound_usd=str(bound),
            endpoint_metadata=metadata, seed_audit=seeds,
            mechanical_baselines=journal.encode(mechanical), retirement_pins=RETIREMENT_PINS,
            migration_retirement_sha256=budget.MIGRATION_CERTIFICATE_SHA,
            inherited_provider_qualification_pass=False, actual_model_calls=0,
            allocation_authorized=False, launch_authorized=False,
            operating_readiness=pin, operating_authorization=authority)
        institution.require(prior == inventory(ledger_root) and all(
            journal._digest(repo/k) == v for k,v in manifest["sources"].items()),
            "preparation evidence changed")
        root.mkdir(parents=True, exist_ok=False)
        budget.atomic(root / "sources.json", snapshots)
        budget.atomic(root / "manifest.json", manifest)
    return journal.physical.t.sha(journal.canonical(manifest).encode())


def verify(root, repo, expected_protocol):
    root, repo = Path(root), Path(repo).resolve()
    manifest, snapshots = journal.load(root/"manifest.json"), journal.load(root/"sources.json")
    journal._protocol(expected_protocol)
    institution.require(not list(root.glob("*.partial")) and
        journal.physical.t.sha(journal.canonical(manifest).encode()) == expected_protocol,
        "frozen migration protocol changed")
    pin = readiness_pin_check(manifest["operating_readiness"])
    institution.require(manifest["format"] == FORMAT and
        manifest["operating_authorization"] == authorization_check(repo) and
        manifest["retirement_pins"] == RETIREMENT_PINS and
        manifest["migration_retirement_sha256"] == budget.MIGRATION_CERTIFICATE_SHA and
        journal.canonical(manifest["specification"]) == journal.canonical(specification()) and
        set(manifest["sources"]) == set(snapshots) == {
            p.relative_to(repo).as_posix() for p in closure(repo, source_roots(repo,pin))},
        "whole source/specification/authority closure changed")
    for name, expected in manifest["sources"].items():
        path = Path(name)
        institution.require(not path.is_absolute() and ".." not in path.parts and
            not (repo/path).is_symlink() and
            journal._digest(repo/path) == journal.physical.t.sha(snapshots[name].encode()) == expected,
            "frozen migration source changed: " + name)
    institution.require(manifest["actual_model_calls"] == 0 and
        manifest["inherited_provider_qualification_pass"] is False and
        not manifest["seed_audit"]["overlap"], "no inherited model passes or seed reuse")
    route.check_endpoint(manifest["endpoint_metadata"])
    return manifest, expected_protocol
