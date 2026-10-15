"""Standalone, standard-library replay entry point for a trusted policy-relabeling bundle.

This is an offline replay, not fresh inference or a security sandbox for arbitrary
Python. It runs the bundled research code. Review it before running an untrusted
bundle. Run with Python 3.11+ on macOS/Linux: python3 -I -S replay.py.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def safe_path(root, relative):
    p = PurePosixPath(relative)
    require(bool(p.parts) and not p.is_absolute() and '..' not in p.parts and '\\' not in relative,
            'unsafe bundle path')
    target = root.joinpath(*p.parts)
    require(not any(q.is_symlink() for q in [target, *target.parents] if q != root.parent),
            'symlink in bundle path')
    require(target.resolve().is_relative_to(root.resolve()), 'path escapes bundle')
    return target


def verify_inventory(root, expected_protocol=None):
    metadata = json.loads((root/'bundle.json').read_text())
    require(metadata['format'] == 'paper3-disclosure-relabel-portable-v1', 'unknown bundle format')
    expected = metadata['files']
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p != root/'bundle.json'}
    require(actual == set(expected), 'bundle file inventory mismatch')
    for name, sha in expected.items():
        require(hashlib.sha256(safe_path(root, name).read_bytes()).hexdigest() == sha,
                'bundle file hash mismatch: '+name)
    manifest = json.loads((root/'run/manifest.json').read_text())
    require(digest(manifest) == metadata['coordinator_protocol'], 'coordinator hash mismatch')
    if expected_protocol is not None:
        require(expected_protocol == metadata['coordinator_protocol'], 'unexpected coordinator protocol')
    return metadata


def relocated_sources(auditor, root, index):
    """Resolve old absolute source keys; never rewrite manifests or call keys."""
    run = auditor.run
    manifest = run.load(root/'manifest.json')
    require(manifest['protocol'] == run.protocol(index), 'protocol mismatch')
    snapshot = run.load(root/'sources.json')
    relative = {str(p.relative_to(run.ROOT)) for p in run.sources()}
    require(set(snapshot) == relative, 'frozen snapshot inventory mismatch')
    first = sorted(relative)[0]
    matches = [k[:-len(first)] for k in manifest['sources'] if k.endswith('/'+first)]
    require(len(matches) == 1, 'ambiguous original source root')
    prefix = matches[0]
    require(set(manifest['sources']) == {prefix+p for p in relative}, 'source key inventory mismatch')
    for p in relative:
        sha = manifest['sources'][prefix+p]
        require(hashlib.sha256(snapshot[p].encode()).hexdigest() == sha, 'frozen snapshot hash mismatch')
        require(hashlib.sha256(safe_path(run.ROOT, p).read_bytes()).hexdigest() == sha,
                'relocated source mismatch')
    return digest(manifest)


def forbid_network_and_processes(event, args):
    if event.startswith(('socket.', 'urllib.', 'subprocess.')) or event in ('os.system', 'os.exec', 'os.posix_spawn'):
        raise RuntimeError('offline replay forbids network and child processes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-protocol')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    metadata = verify_inventory(root, args.expected_protocol)
    sys.dont_write_bytecode = True
    sys.addaudithook(forbid_network_and_processes)
    sys.path.insert(0, str(root/'code'))
    # The initializer remains hashed in the bundle, but its unrelated plotting
    # imports are bypassed explicitly. No experiment/scoring source is changed.
    import types
    namespace = types.ModuleType('analysis')
    namespace.__path__ = [str(root/'code/analysis'), str(root/'tools')]
    namespace.__package__ = 'analysis'
    sys.modules['analysis'] = namespace
    from analysis import paper3_disclosure_identification_audit as original_auditor
    from analysis import paper3_disclosure_relabel_audit as auditor
    # Adapt source-path resolution without modifying the original evidence.
    # The analysis initializer is included and verified, but replaced by a
    # namespace package at import time. Frozen source bytes are unchanged.
    auditor.sources = lambda path, index: relocated_sources(auditor, path, index)
    original_auditor.sources = lambda path, index: relocated_sources(original_auditor, path, index)
    report = auditor.audit(root/'run')
    report['portable_replay'] = dict(
        protocol=metadata['coordinator_protocol'],
        post_freeze_tools=metadata['post_freeze_tools'], adapter=metadata['adapter'],
        limitation='All experiment/audit local dependencies were frozen before inference. '
                   'Packaging and path/import adapters for both auditors are '
                   'separate post-freeze tools, not backdated. '
                   'Saved requests/actions are replayed exactly; the unrelated plotting initializer '
                   'is hashed but not executed. The original gate evidence is bundled, not charged twice. '
                   'Scientific robustness success is a separate field. No weights/provider reexecution. '
                   'Hashes establish consistency, not authorship or provider authenticity.')
    print(json.dumps(report, indent=2))
    return bool(report['integrity_errors'])


if __name__ == '__main__':
    raise SystemExit(main())
