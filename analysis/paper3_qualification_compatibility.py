"""Offline pinned-source compatibility inspection; not an institutional runner."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


def deny_network(event, args):
    if event in ("socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.bind"):
        raise RuntimeError("network prohibited during compatibility inspection")


def source_snapshot(code, inventory, expected_sha):
    raw = inventory.read_bytes()
    if sha256(raw).hexdigest() != expected_sha:
        raise ValueError("external source inventory pin changed")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate source inventory key")
            result[key] = value
        return result
    rows = json.loads(raw, object_pairs_hook=unique)
    if type(rows) is not dict or not rows:
        raise ValueError("nonempty source snapshot required")
    actual = {p.relative_to(code).as_posix() for p in code.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in code.rglob("*")):
        raise ValueError("symlink in source snapshot")
    if actual != set(rows):
        raise ValueError("source snapshot inventory changed")
    for name, expected in rows.items():
        if type(expected) is not str or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("invalid source digest")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError("unsafe source snapshot path")
        path = code / relative
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("symlink in source snapshot")
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("source snapshot hash changed")
    return len(rows)


def main():
    sys.dont_write_bytecode = True
    sys.addaudithook(deny_network)
    import socket
    try:
        socket.getaddrinfo("127.0.0.1", 1)
    except RuntimeError as exc:
        if str(exc) != "network prohibited during compatibility inspection":
            raise
    else:
        raise ValueError("network guard self-test failed")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("qualified_directory", type=Path)
    parser.add_argument("--qualified-zip", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--sources-sha256", required=True)
    parser.add_argument("--expected-proof-sha256", required=True)
    parser.add_argument("--allow-menu-bound-instantiation", action="store_true",
                        help="Explicit OFFLINE inspection only, not launch/inheritance approval.")
    args = parser.parse_args()
    code = Path(__file__).resolve().parents[1]
    count = source_snapshot(code, args.sources, args.sources_sha256)
    sys.path.insert(0, str(code))
    from paper3 import retrospective_anticipation_design as design
    from paper3 import retrospective_qualification_inheritance as proof
    report = proof.prove(args.qualified_directory.resolve(strict=True),
        args.qualified_zip.resolve(strict=True), design.assignments(),
        allow_menu_bound_instantiation=args.allow_menu_bound_instantiation)
    digest = sha256(proof.canonical(report).encode()).hexdigest()
    if digest != args.expected_proof_sha256:
        raise ValueError("entire compatibility proof differs from external pin")
    print(proof.canonical(dict(full_proof_matched=True, proof_sha256=digest,
        source_snapshot_files=count, source_snapshot_verified=True, qualified_full_gate_reproduced=True,
        compared_assignments=report["compared_assignments"], compared_slots=report["compared_slots"],
        literal_full_schema_equal=report["literal_full_schema_equal"],
        slots_with_declared_menu_delta=report["slots_with_declared_menu_delta"],
        network_guard_self_test=True, actual_model_calls=0, inheritance_authorized=False,
        launch_authorized=False, publication_evidence=False)))


if __name__ == "__main__":
    main()
