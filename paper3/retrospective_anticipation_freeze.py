"""Prospective source/design freeze component; NO allocation or live runner.

Full admission and explicit caller-supplied approval are prerequisites, never
inferred from a compatibility proof. Sources, cases, analysis, old qualification,
whole-pilot bounds and pre-stage reservations are pinned before any execution.
Tests use private directories/copied authority; no actual successor is prepared.
"""
from fractions import Fraction
from functools import cache
import json
from pathlib import Path

from paper3 import retrospective_accountability as institution
from paper3 import retrospective_anticipation_analysis as science
from paper3 import retrospective_anticipation_audit as audit
from paper3 import retrospective_anticipation_baselines as baselines
from paper3 import retrospective_anticipation_design as design
from paper3 import retrospective_contract_route_v2 as route
from paper3 import retrospective_episode_journal as journal
from paper3 import retrospective_extended_budget as budget
from paper3 import retrospective_qualification_inheritance as qualification
from paper3.pivot_b_budget import atomic, amount
from paper3.retrospective_source_closure import closure

FORMAT = "paper3-anticipation-freeze-v1"
APPROVAL_FIELDS = {"first_term_primary", "full_two_term_inventory", "declared_menu_bound_policy",
                   "independent_safe_failure_policy"}
READINESS_FILE = "results/paper3/pivot_b_retrospective_anticipation_v1_preflight.json"
AUTHORIZATION_FILE = "results/paper3/pivot_b_retrospective_anticipation_v1_authorization.json"
RUNNER_FILE = "experiments/paper3_retrospective_anticipation_v1.py"


def authorization_check(repo, pin):
    """Pinned human evidence is necessary, but a hash cannot authenticate consent."""
    institution.require(type(pin) is dict and set(pin) == {"path", "sha256"} and
                        pin["path"] == AUTHORIZATION_FILE, "exact operating authorization required")
    journal._protocol(pin["sha256"])
    path = Path(repo) / pin["path"]
    institution.require(not path.is_symlink() and qualification.file_sha(path) == pin["sha256"],
                        "external authorization pin changed")
    value = journal.load(path)
    institution.require(type(value) is dict and set(value) == {
        "format", "human_statement", "source_thread_id", "approved_at", "scope",
        "both_blocks_approved", "credit_purchases_authorized"} and
        value["format"] == "paper3-anticipation-authorization-v1" and
        all(type(value[k]) is str and value[k].strip() for k in
            ("human_statement", "source_thread_id", "approved_at")) and
        value["both_blocks_approved"] is True and value["credit_purchases_authorized"] is False,
        "explicit full-pilot human evidence required")
    approval_check(value["scope"])
    return value


def readiness_pin_check(value):
    institution.require(type(value) is dict and set(value) == {"path", "sha256"} and
                        value["path"] == READINESS_FILE, "exact prospective readiness path/pin required")
    journal._protocol(value["sha256"])
    return dict(value)


def approval_check(approval):
    institution.require(type(approval) is dict and set(approval) == APPROVAL_FIELDS and
        all(v is True for v in approval.values()), "explicit entire prospective scope approval required")
    # This checks declared scope, not human identity. The operating agent must
    # obtain genuine approval before supplying this record outside fabricated tests.


@cache
def _specification_text():
    items = design.assignments()
    science.validate(items, {a["id"]: (None, None) for a in items})
    return journal.canonical(journal.encode(dict(format=FORMAT, assignments=items, bound=design.full_bound(),
        primary="first_term_mean_normalized_district_regret_interaction",
        minimum_effect=Fraction(1, 25), aligned_fraction=Fraction(1, 2),
        analysis_source=science.__name__, audit_source=audit.__name__,
        execution_source="paper3.retrospective_anticipation_coordinator",
        continuation="Batch1 only after audited batch0/no global safety stop and ACTUAL "
            "fresh isolated archive replay, regardless of the scientific outcome.",
        workers=1, reissues_per_block=1, retry_cooldown_seconds=300,
        qualified_protocol=qualification.PROTOCOL, qualified_archive_sha256=qualification.ARCHIVE_SHA,
        qualified_width=4, task_width=6, total_cap_usd=str(budget.TOTAL_CAP),
        publication_evidence=False,
        limitation="Two selected conditional frames/one model: discovery only, not a "
        "population or motive claim. Both horizons, all citizens and failed cases remain.")))


def specification():
    # Cached immutable text avoids repeated legal-history enumeration; returned
    # mutable objects never alias the reference specification or one another.
    return json.loads(_specification_text())


def inventory(ledger_root):
    return {p.name: qualification.file_sha(p) for p in sorted((Path(ledger_root) / "entries").glob("*.json"))}


def source_roots(repo, operating_readiness=None, operating_authorization=None):
    repo = Path(repo)
    # Static import closure plus explicit dynamic archive-helper and pinned data.
    old = repo / "results/paper3/pivot_b_retrospective_score_ledger_gate_v1"
    previous = journal.load(old / "manifest.json")
    institution.require(journal.physical.t.sha(journal.physical.t.canonical(previous).encode()) ==
        qualification.PROTOCOL, "pinned old qualification manifest changed")
    roots = [repo / "paper3/retrospective_anticipation_freeze.py",
        repo / "paper3/retrospective_anticipation_coordinator.py",
        repo / "paper3/retrospective_anticipation_archive.py",
        repo / "paper3/retrospective_anticipation_operating.py",
        repo / RUNNER_FILE,
        repo / "analysis/paper3_anticipation_replay.py",
        repo / "analysis/paper3_contracts_archive.py", repo / "requirements.txt",
        repo / "results/paper3/pivot_b_budget/authority.json",
        repo / "results/paper3/pivot_b_budget" / budget.PREVIOUS_EXTENSION_FILE,
        repo / "results/paper3/pivot_b_budget" / budget.EXTENSION_FILE,
        old / "manifest.json", old / "sources.json"]
    for name, digest in previous["sources"].items():
        relative = Path(name)
        institution.require(not relative.is_absolute() and ".." not in relative.parts and
            qualification.file_sha(repo / relative) == digest, "old qualification source closure changed")
        roots.append(repo / relative)
    institution.require(len(previous["sources"]) == 58, "entire old qualification closure required")
    if operating_readiness is not None:
        pin = readiness_pin_check(operating_readiness)
        path = repo / pin["path"]
        institution.require(not path.is_symlink() and qualification.file_sha(path) == pin["sha256"],
                            "operating readiness file changed")
        from paper3 import retrospective_anticipation_operating as operating
        # Include the tests referenced by readiness without importing/running them.
        roots += [path, *(repo / command[3] for command in operating.REQUIRED_CHECKS.values())]
    if operating_authorization is not None:
        authorization_check(repo, operating_authorization)
        roots.append(repo / operating_authorization["path"])
    return roots


def prepare(root, repo, ledger_root, qualified_directory, qualified_zip, *, approval, metadata,
            operating_readiness=None, operating_authorization=None):
    """Freeze ONCE only after FULL16-case admission, without spending or stages.

Metadata must be independently observed by the caller; this function never
fetches it, reads a key or transmits. The finished production runner must add
reviewed readiness/real launch authority, route freshness and live-process checks.
"""
    root, repo, ledger_root = Path(root), Path(repo).resolve(), Path(ledger_root)
    institution.require(not root.exists(), "fresh freeze only; never restart")
    approval_check(approval)
    if operating_authorization is not None:
        institution.require(authorization_check(repo, operating_authorization)["scope"] == approval,
                            "human scope differs from frozen approval")
    route.check_endpoint(metadata)
    pin = None
    if operating_readiness is not None:
        from paper3 import retrospective_anticipation_operating as operating
        pin = readiness_pin_check(operating_readiness)
        operating.readiness_check(repo, repo / pin["path"], pin["sha256"])
    ledger = budget.ExtendedLedger(ledger_root)
    with ledger.locked():
        entries = ledger._entries()
        used, commitments = ledger._total(entries), ledger._commitments(entries)
        full_bound = amount(journal.decode(specification())["bound"]["full_reservation_usd"])
        institution.require(used + commitments + full_bound <= budget.TOTAL_CAP,
                            "full16-assignment budget admission denied; no partial pilot")
        prior = inventory(ledger_root)
        seeds = design.seed_audit(repo)
        proof = qualification.prove(qualified_directory, qualified_zip, design.assignments(),
                                   allow_menu_bound_instantiation=True)
        institution.require(proof["compared_assignments"] == 16 and proof["compared_slots"] == 480 and
            proof["slots_with_declared_menu_delta"] == 256 and
            proof["literal_full_schema_equal"] is False and
            proof["native_system_and_template_compatible"] is True and
            proof["inheritance_authorized"] is False, "exact declared qualification/task boundary")
        mechanical = tuple(baselines.check_pair(p) for p in design.pairs())
        snapshots = {p.relative_to(repo).as_posix(): p.read_text()
                     for p in closure(repo, source_roots(repo, pin, operating_authorization))}
        manifest = dict(format=FORMAT, specification=specification(), approval=approval,
            sources={name: journal.physical.t.sha(value.encode()) for name, value in snapshots.items()},
            prior_entries=prior, pre_stage_accounted_usd=str(used),
            pre_stage_unused_commitments_usd=str(commitments), full_bound_usd=str(full_bound),
            endpoint_metadata=metadata, seed_audit=seeds, qualification_proof=journal.encode(proof),
            mechanical_baselines=journal.encode(mechanical), actual_model_calls=0,
            allocation_authorized=False, launch_authorized=False, operating_readiness=pin,
            operating_authorization=operating_authorization)
        # Recheck all old financial evidence and sources before irreversible creation.
        institution.require(inventory(ledger_root) == prior and all(
            qualification.file_sha(repo / name) == digest for name, digest in manifest["sources"].items()),
            "preparation evidence changed")
        root.mkdir(parents=True, exist_ok=False)
        atomic(root / "sources.json", snapshots)
        atomic(root / "manifest.json", manifest)
    return journal.physical.t.sha(journal.canonical(manifest).encode())


def verify(root, repo, expected_protocol):
    """Exact source/specification closure; no inference, repair or financial write."""
    root, repo = Path(root), Path(repo).resolve()
    institution.require(not list(root.glob("*.partial")), "interrupted freeze; never reprepare")
    manifest, snapshots = journal.load(root / "manifest.json"), journal.load(root / "sources.json")
    journal._protocol(expected_protocol)
    digest = journal.physical.t.sha(journal.canonical(manifest).encode())
    institution.require(digest == expected_protocol, "external freeze protocol pin changed")
    approval_check(manifest["approval"])
    pin = manifest["operating_readiness"]
    authorization = manifest["operating_authorization"]
    if authorization is not None:
        institution.require(authorization_check(repo, authorization)["scope"] == manifest["approval"],
                            "pinned human scope differs from manifest")
    if pin is not None:
        readiness_pin_check(pin)
    institution.require(manifest["format"] == FORMAT and
        journal.canonical(manifest["specification"]) == journal.canonical(specification()) and
        set(manifest["sources"]) == set(snapshots) ==
            {p.relative_to(repo).as_posix() for p in closure(repo, source_roots(repo, pin, authorization))},
        "complete source/specification inventory changed")
    for name, expected in manifest["sources"].items():
        relative = Path(name)
        institution.require(not relative.is_absolute() and ".." not in relative.parts and
            not (repo / relative).is_symlink() and
            journal.physical.t.sha(snapshots[name].encode()) == expected == qualification.file_sha(repo / relative),
            "frozen source changed: " + name)
    institution.require(manifest["actual_model_calls"] == 0 and
        manifest["allocation_authorized"] is False and manifest["launch_authorized"] is False and
        not manifest["seed_audit"]["overlap"] and
        amount(manifest["full_bound_usd"]) ==
            amount(journal.decode(specification())["bound"]["full_reservation_usd"]),
        "freeze scope, seed or full bound changed")
    route.check_endpoint(manifest["endpoint_metadata"])
    if pin is not None:
        from paper3 import retrospective_anticipation_operating as operating
        operating.readiness_check(repo, repo / pin["path"], pin["sha256"])
    return manifest, digest
