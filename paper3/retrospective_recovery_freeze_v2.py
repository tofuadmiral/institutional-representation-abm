"""Distinct prospective recovery freeze; no key, network, allocation or launch.

Pins the unchanged economic study, approved fresh cases, bounded transport,
entire original qualification, $17 authority chain and one already-executed
retirement. Component freezes without operating readiness are NOT runnable.
Never edits or opens an older run for execution.
"""
from fractions import Fraction
from functools import cache
import json
from pathlib import Path

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_anticipation_baselines as baselines
from paper3 import retrospective_anticipation_recovery_policy as policy
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_qualification_inheritance as qualification
from paper3 import retrospective_recovery_budget_v2 as budget
from paper3 import retrospective_recovery_design_v2 as design
from paper3 import retrospective_recovery_retirement_v2 as retirement
from paper3 import retrospective_recovery_science_v2 as audit
from paper3.pivot_b_budget import atomic, amount
from paper3.retrospective_source_closure import closure

FORMAT = design.FORMAT
AUTHORIZATION_FILE = retirement.AUTHORIZATION_FILE
RETIREMENT_SHA = "ac9070f7ac2c0404a8150623a57f48452d05821325f3c5c58ffda1bdd7949028"
RETIREMENT_PINS = {retirement.STAGE: RETIREMENT_SHA}
READINESS_FILE = "results/paper3/pivot_b_retrospective_anticipation_recovery_v2_preflight.json"
RUNNER_FILE = "experiments/paper3_retrospective_anticipation_recovery_v2.py"


def authorization_check(repo):
    path = Path(repo) / AUTHORIZATION_FILE
    institution.require(not path.is_symlink() and
        qualification.file_sha(path) == retirement.AUTHORIZATION_SHA,
        "exact directly approved recovery authority changed")
    value = journal.load(path)
    expected = dict(format="paper3-anticipation-recovery-authorization-v2",
        human_response="kapproved", economic_design_unchanged=True, assigned_episodes=16,
        logical_actions=480, both_blocks_conditionally_approved=True, first_term_primary=True,
        full_two_term_mandate_retained=True, maximum_reissues_per_action=3,
        maximum_reissues_per_block=40, maximum_physical_requests=560,
        cooldown_seconds=[300, 600, 1200], block_deadline_seconds=86400, workers=1,
        draft_frame_seeds=list(design.FRAME_SEEDS), draft_order_seed=design.ORDER_SEED,
        draft_paired_request_bases=[design.DECISION_SEED_BASE, design.DECISION_SEED_BASE + 64],
        unused_old_block1_abandonment_approved=True, paid_qualification_calls_authorized=0,
        credit_purchases_authorized=False, old_run_reopen_authorized=False,
        scientific_successor_authorized=False)
    institution.require(all(type(value[k]) is type(v) and value[k] == v for k, v in expected.items()),
                        "recovery authority scope differs from fixed study")
    # Historical abandonment_executed=False is an approval-time observation,
    # not a denial of the later separately pinned disposition. Never rewrite it.
    return dict(path=AUTHORIZATION_FILE, sha256=retirement.AUTHORIZATION_SHA)


def readiness_pin_check(value):
    institution.require(type(value) is dict and set(value) == {"path", "sha256"} and
                        value["path"] == READINESS_FILE, "exact recovery readiness path required")
    journal._protocol(value["sha256"])
    return dict(value)


@cache
def _specification_text():
    items = design.assignments()
    science.validate(items, {a["id"]: (None, None) for a in items})
    return journal.canonical(journal.encode(dict(format=FORMAT, assignments=items,
        bound=design.full_bound(), recovery=policy.specification(),
        primary="first_term_mean_normalized_district_regret_interaction",
        minimum_effect=Fraction(1, 25), aligned_fraction=Fraction(1, 2),
        analysis_source=science.__name__, audit_source=audit.__name__,
        execution_source="paper3.retrospective_recovery_coordinator_v2",
        continuation="Batch1 only after clean terminal batch0/no global safety stop, "
            "audited unused-cap closure and ACTUAL fresh isolated full-report archive replay, "
            "regardless of scientific outcome; no study shrinking or automatic successor.",
        workers=1, qualified_protocol=qualification.PROTOCOL,
        qualified_archive_sha256=qualification.ARCHIVE_SHA, qualified_width=4, task_width=6,
        total_cap_usd=str(budget.TOTAL_CAP), retirement_pins=RETIREMENT_PINS,
        publication_evidence=False,
        limitation="Two selected conditional frames/one model: discovery only. "
            "Both horizons, all citizens, raw/executed actions and failures remain; "
            "qualification is not long-run reliability or a motive/population claim.")))


def specification():
    return json.loads(_specification_text())


def inventory(ledger_root):
    return retirement.inventory(ledger_root)


def source_roots(repo, operating_readiness=None):
    repo = Path(repo)
    old = repo / "results/paper3/pivot_b_retrospective_score_ledger_gate_v1"
    previous = journal.load(old / "manifest.json")
    institution.require(journal.physical.t.sha(journal.physical.t.canonical(previous).encode()) ==
                        qualification.PROTOCOL, "pinned original qualification manifest changed")
    roots = [repo / "paper3" / name for name in (
        "retrospective_recovery_freeze_v2.py", "retrospective_recovery_coordinator_v2.py",
        "retrospective_recovery_science_v2.py", "retrospective_recovery_archive_v2.py",
        "retrospective_recovery_operating_v2.py",
        "retrospective_recovery_calls_v2.py", "retrospective_recovery_journal_v2.py")]
    roots += [repo / RUNNER_FILE, repo / "analysis/paper3_recovery_replay_v2.py",
        repo / "analysis/paper3_contracts_archive.py",
        repo / "requirements.txt", repo / AUTHORIZATION_FILE,
        repo / "results/paper3/pivot_b_budget" / retirement.DIRECTORY / (retirement.STAGE + ".json"),
        old / "manifest.json", old / "sources.json"]
    roots += [repo / "results/paper3/pivot_b_budget" / name for name in budget.AUTHORITY_FILES]
    institution.require(len(previous["sources"]) == 58, "entire original qualification closure required")
    for name, digest in previous["sources"].items():
        relative = Path(name)
        institution.require(not relative.is_absolute() and ".." not in relative.parts and
            not (repo / relative).is_symlink() and qualification.file_sha(repo / relative) == digest,
            "original qualification source changed")
        roots.append(repo / relative)
    if operating_readiness is not None:
        from paper3 import retrospective_recovery_operating_v2 as operating
        pin = readiness_pin_check(operating_readiness)
        path = repo / pin["path"]
        institution.require(not path.is_symlink() and qualification.file_sha(path) == pin["sha256"],
                            "pinned recovery readiness file changed")
        roots += [path, *(repo / argument for command in operating.REQUIRED_CHECKS.values()
                         for argument in command[3:] if argument.endswith(".py"))]
    return roots


def prepare(root, repo, ledger_root, qualified_directory, qualified_zip, *, metadata,
            operating_readiness=None):
    """Freeze ONCE after full funds, scope and inherited proof; never allocates."""
    root, repo, ledger_root = Path(root), Path(repo).resolve(), Path(ledger_root)
    institution.require(not root.exists(), "fresh recovery freeze only; never restart")
    authorization = authorization_check(repo)
    route.check_endpoint(metadata)
    pin = None
    if operating_readiness is not None:
        from paper3 import retrospective_recovery_operating_v2 as operating
        pin = readiness_pin_check(operating_readiness)
        operating.readiness_check(repo, repo / pin["path"], pin["sha256"])
    ledger = budget.RecoveryLedger(ledger_root, retirement_pins=RETIREMENT_PINS)
    with ledger.locked():
        entries = ledger._entries()
        used, commitments = ledger._total(entries), ledger._commitments(entries)
        full_bound = amount(journal.decode(specification())["bound"]["full_reservation_usd"])
        institution.require(used + commitments + full_bound <= budget.TOTAL_CAP,
                            "full16-assignment recovery budget denied; no partial pilot")
        prior = inventory(ledger_root)
        seeds = design.seed_audit(repo)
        proof = qualification.prove(qualified_directory, qualified_zip, design.assignments(),
                                   allow_menu_bound_instantiation=True)
        institution.require(proof["compared_assignments"] == 16 and proof["compared_slots"] == 480 and
            proof["slots_with_declared_menu_delta"] == 256 and
            proof["literal_full_schema_equal"] is False and
            proof["native_system_and_template_compatible"] is True and
            proof["inheritance_authorized"] is False, "exact inherited qualification/task boundary")
        mechanical = tuple(baselines.check_pair(pair) for pair in design.pairs())
        snapshots = {p.relative_to(repo).as_posix(): p.read_text()
                     for p in closure(repo, source_roots(repo, pin))}
        manifest = dict(format=FORMAT, specification=specification(),
            sources={name: journal.physical.t.sha(text.encode()) for name, text in snapshots.items()},
            prior_entries=prior, pre_stage_accounted_usd=str(used),
            pre_stage_unused_commitments_usd=str(commitments), full_bound_usd=str(full_bound),
            endpoint_metadata=metadata, seed_audit=seeds, qualification_proof=journal.encode(proof),
            mechanical_baselines=journal.encode(mechanical), retirement_pins=dict(RETIREMENT_PINS),
            actual_model_calls=0, allocation_authorized=False, launch_authorized=False,
            operating_readiness=pin, operating_authorization=authorization)
        institution.require(inventory(ledger_root) == prior and all(
            qualification.file_sha(repo / name) == digest for name, digest in manifest["sources"].items()),
            "preparation evidence changed")
        root.mkdir(parents=True, exist_ok=False)
        atomic(root / "sources.json", snapshots)
        atomic(root / "manifest.json", manifest)
    return journal.physical.t.sha(journal.canonical(manifest).encode())


def verify(root, repo, expected_protocol):
    root, repo = Path(root), Path(repo).resolve()
    institution.require(not list(root.glob("*.partial")), "interrupted freeze; never reprepare")
    manifest, snapshots = journal.load(root / "manifest.json"), journal.load(root / "sources.json")
    journal._protocol(expected_protocol)
    digest = journal.physical.t.sha(journal.canonical(manifest).encode())
    institution.require(digest == expected_protocol, "external recovery protocol pin changed")
    pin = manifest["operating_readiness"]
    if pin is not None:
        readiness_pin_check(pin)
    institution.require(manifest["operating_authorization"] == authorization_check(repo) and
        manifest["retirement_pins"] == RETIREMENT_PINS and manifest["format"] == FORMAT and
        journal.canonical(manifest["specification"]) == journal.canonical(specification()) and
        set(manifest["sources"]) == set(snapshots) ==
            {p.relative_to(repo).as_posix() for p in closure(repo, source_roots(repo, pin))},
        "complete recovery source/specification/authority inventory changed")
    for name, expected in manifest["sources"].items():
        relative = Path(name)
        institution.require(not relative.is_absolute() and ".." not in relative.parts and
            not (repo / relative).is_symlink() and
            journal.physical.t.sha(snapshots[name].encode()) == expected == qualification.file_sha(repo / relative),
            "frozen recovery source changed: " + name)
    institution.require(type(manifest["actual_model_calls"]) is int and manifest["actual_model_calls"] == 0 and
        manifest["allocation_authorized"] is False and manifest["launch_authorized"] is False and
        not manifest["seed_audit"]["overlap"] and amount(manifest["full_bound_usd"]) ==
        amount(journal.decode(specification())["bound"]["full_reservation_usd"]), "recovery scope or bound changed")
    route.check_endpoint(manifest["endpoint_metadata"])
    if pin is not None:
        from paper3 import retrospective_recovery_operating_v2 as operating
        operating.readiness_check(repo, repo / pin["path"], pin["sha256"])
    return manifest, digest
