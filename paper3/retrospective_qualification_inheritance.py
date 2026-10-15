"""Read-only candidate compatibility proof; NEVER qualification/launch authority.

Pins the archived completed gate and recomputes its original production audit.
Literal schema equality is the default. Explicit offline inspection may permit
only the declared game-dependent policy maximum, recording that task change.
This cannot certify reliability on larger games or authorize paid work.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import zipfile

from experiments import paper3_retrospective_score_ledger_gate_v1 as qualified
from paper3 import retrospective_accountability as institution
from paper3 import retrospective_score_ledger_budget as budget
from paper3 import retrospective_score_ledger_qualification as qualification
from paper3.pivot_b_budget import identifier

PROTOCOL = "d733dca23f88442915be3a6628e398d746d1cafdf85089c718f2a150d46cb1c3"
ARCHIVE_SHA = "df71e50f370d4ac528d4e48195f004048cb8ceeed5b4221c3b36f1dea289edbc"
NATIVE_OMISSIONS = {"messages", "tools", "seed"}  # Task data/schema and paired request seed only.


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def file_sha(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compare(reference, request, *, qualified_width, task_width, phase,
            allow_menu_bound_instantiation=False):
    """No comparison result edits a wire or loosens the execution classifier."""
    institution.require(type(allow_menu_bound_instantiation) is bool and
        type(qualified_width) is int and type(task_width) is int and
        2 <= qualified_width <= 8 and 2 <= task_width <= 8 and
        phase in ("draft", "response", "final", "vote"), "explicit bounded task-schema policy")
    institution.require(set(reference) == set(request) and type(request["seed"]) is int and
        request["seed"] >= 0 and request["messages"][0] == reference["messages"][0],
        "native field inventory, system instruction or seed type changed")
    def native(value):
        return {k: v for k, v in value.items() if k not in NATIVE_OMISSIONS}
    institution.require(canonical(native(reference)) == canonical(native(request)),
                        "qualified native configuration changed")
    original, target = reference["tools"], request["tools"]
    institution.require(type(original) is list and len(original) == 1 and
                        type(target) is list and len(target) == 1, "one qualified AUTO tool")
    expected = deepcopy(original)
    deltas = []
    if phase != "vote":
        name = "counter_policy" if phase == "response" else "policy"
        prop = expected[0]["function"]["parameters"]["properties"][name]
        institution.require(type(prop["maximum"]) is int and prop["maximum"] == qualified_width - 1,
                            "qualified legal policy bound")
        if qualified_width != task_width:
            institution.require(allow_menu_bound_instantiation, "literal schema equality fails; explicit policy required")
            prop["maximum"] = task_width - 1
            deltas.append(dict(path=f"tools[0].function.parameters.properties.{name}.maximum",
                               qualified=qualified_width - 1, proposed=task_width - 1))
    institution.require(canonical(expected) == canonical(target),
                        "tool schema/template differs beyond declared menu maximum")
    return dict(phase=phase, qualified_width=qualified_width, task_width=task_width,
        native_equal=True, system_equal=True, literal_full_schema_equal=canonical(original) == canonical(target),
        declared_task_deltas=tuple(deltas), template_equal_after_declared_instantiation=True,
        inheritance_authorized=False, qualification_at_task_width_established=task_width == qualified_width)


def verify_archive(directory, archive):
    """No locks, writes or new audit files inside the immutable old archive."""
    directory, archive = Path(directory), Path(archive)
    institution.require(not directory.is_symlink() and not archive.is_symlink(), "pinned archive paths")
    institution.require(file_sha(archive) == ARCHIVE_SHA, "qualified ZIP hash changed")
    with zipfile.ZipFile(archive) as zipped:
        institution.require(zipped.read("bundle.json") == (directory / "bundle.json").read_bytes(),
                            "extracted qualified metadata differs from pinned ZIP")
    metadata = qualified.archive_helper().verify_bundle(directory, PROTOCOL)
    institution.require(metadata["experiment_family"] == qualified.STAGE, "different qualification family")
    report = qualified._audit_locked(directory / "run", directory / "ledger")  # Immutable offline snapshot.
    expected = qualified.t.load(directory / "expected_report.json")
    institution.require(canonical(report) == canonical(expected) and report["protocol"] == PROTOCOL and
        report["gate_passed"] is True and len(report["assignments"]) == 24 and report["calls"] == 25 and
        all(r["failure_scope"] == "passed" for r in report["assignments"]),
        "original full24 qualification/retry/accounting audit did not reproduce")
    return report, metadata


def prove(directory, archive, assignments, *, allow_menu_bound_instantiation=False):
    """Inspect every supplied fresh assignment without inference or allocation.

The candidate wrapper must validate/freeze the complete inventory separately.
Zero-policy scripted histories here construct genuine legal messages to compare
native/tool templates only; they are not proposed or observed bargaining outcomes.
Complete legal-history coverage/cost, source closure and authority are separate.
"""
    institution.require(type(assignments) is tuple and bool(assignments) and
        type(allow_menu_bound_instantiation) is bool, "explicit prospective inventory/policy")
    ids = [row["id"] for row in assignments]
    for key in ids:
        identifier(key)
    institution.require(len(set(ids)) == len(ids), "unique compatibility assignment inventory")
    report, metadata = verify_archive(directory, archive)
    actions = [case for case in qualification.cases() if case["kind"] == "action"]
    original = {case["context"]["case_id"]: case["request"] for case in qualification.requests()}
    references = {}
    for case in actions:
        request = original[case["id"]]
        rebuilt = budget.structured(case["messages"], case["game"], case["stage"])
        institution.require(canonical(rebuilt["messages"]) == canonical(request["messages"]) and
            canonical(rebuilt["tools"]) == canonical(request["tools"]) and
            rebuilt["tool_choice"] == request["tool_choice"], "qualification action fragment changed")
        phase = case["stage"]
        if phase in references:
            previous = references[phase]
            institution.require(canonical(previous["tools"]) == canonical(request["tools"]),
                                "qualified schema varies within phase")
        references[phase] = request
    institution.require(set(references) == {"draft", "response", "final", "vote"} and len(actions) == 12,
                        "all four qualified phases/twelve action fragments")
    q_width = len(qualification.game().utilities[0][0][0])
    rows = []
    for assignment in assignments:
        game, arm = assignment["game"], assignment["arm"]
        task_width = len(game.utilities[0][0][0])
        slots = []
        def ask(actor, identity, term, phase, context, index):
            request = budget.action_request(game, arm, assignment["seed_base"],
                actor, identity, term, phase, context, index)
            slots.append(dict(index=index, term=term, **compare(references[phase], request,
                qualified_width=q_width, task_width=task_width, phase=phase,
                allow_menu_bound_instantiation=allow_menu_bound_instantiation)))
            if phase in ("draft", "final"):
                return dict(policy=0, message="offline compatibility construction")
            if phase == "response":
                return dict(support=False, counter_policy=0, message="offline compatibility construction")
            return dict(vote=False)
        institution.episode(game, arm, ask)
        institution.require(len(slots) == 30, "all prospective interface slots")
        rows.append(dict(id=assignment["id"], slots=tuple(slots)))
    slots = [slot for row in rows for slot in row["slots"]]
    return dict(qualified_protocol=PROTOCOL, qualified_archive_sha256=ARCHIVE_SHA,
        qualified_payload_files=len(metadata["files"]), full_gate_passed=report["gate_passed"],
        qualified_action_fragments=12, assignments=tuple(rows), compared_slots=len(slots),
        compared_assignments=len(rows),
        allow_menu_bound_instantiation=allow_menu_bound_instantiation,
        literal_full_schema_equal=all(s["literal_full_schema_equal"] for s in slots),
        slots_with_declared_menu_delta=sum(bool(s["declared_task_deltas"]) for s in slots),
        native_system_and_template_compatible=True, inheritance_authorized=False,
        launch_authorized=False, actual_model_calls=0, publication_evidence=False,
        limitations="A four-option qualification is not six-option or long-run reliability. "
        "Explicit menu-bound inspection is not waiver/approval of literal equality. "
        "Zero-policy histories are unsent engineering constructs, not behavior. "
        "Require prospective human policy/authority, full source/config freeze, "
        "all legal-history cost/coverage, safe persistence and portable replay before paid use.")
