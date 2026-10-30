"""Export a terminal held-out validation as a self-contained offline replay bundle.

Does not modify the experiment, call a model, or include credentials. Keeps old
absolute-path manifests byte-for-byte; replay resolves source roots separately.
Supplemental transitive imports are explicitly post-freeze, never backdated.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.paper3_portable_replay import digest, require, safe_path


def dependency_closure(root, frozen):
    payload = dict(frozen)
    pending = [p for p in frozen if p.endswith('.py') and not p.startswith('tests/')]
    seen = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        modules = []
        for node in ast.walk(ast.parse(payload[path])):
            if isinstance(node, ast.Import):
                modules.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                modules.append(node.module)
                modules.extend(node.module+'.'+a.name for a in node.names)
        for module in modules:
            for relative in (module.replace('.', '/')+'.py', module.replace('.', '/')+'/__init__.py'):
                file = safe_path(root, relative)
                if file.is_file():
                    if relative not in payload:
                        payload[relative] = file.read_text()
                    if relative not in seen:
                        pending.append(relative)
    return payload


def check_credentials(data, secret=None):
    require(not secret or secret.encode() not in data, 'credential found; bundle refused')
    require(not re.search(rb'sk-or-v1-[A-Za-z0-9_-]{24,}', data), 'possible API credential; bundle refused')
    require(not re.search(rb'Bearer\s+[A-Za-z0-9_-]{24,}', data), 'possible bearer credential; bundle refused')


def git_evidence(root, name, text):
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=False)
    head = git('rev-parse', 'HEAD')
    blob = git('show', 'HEAD:'+name)
    return dict(captured_after_freeze=True,
                matches_committed_head=blob.returncode == 0 and blob.stdout == text.encode(),
                head=head.stdout.decode().strip() if head.returncode == 0 else None)


def build(run_root, target, secret=None):
    from analysis import paper3_disclosure_validation_audit as auditor
    run_root, target = Path(run_root).resolve(), Path(target).absolute()
    require((run_root/'sessions/terminal.json').is_file(), 'run is not terminal; do not package live data')
    require(not target.exists(), 'destination exists; never overwrite a bundle')
    report = auditor.audit(run_root)
    require(not report['integrity_errors'], 'terminal integrity audit failed; do not package')
    frozen = json.loads((run_root/'sources.json').read_text())
    payload = dependency_closure(ROOT, frozen)
    require('analysis/__init__.py' not in payload,
            'analysis initializer now required; revisit namespace adapter instead of silently dropping it')
    supplemental = {p:git_evidence(ROOT, p, text) for p,text in payload.items() if p not in frozen}
    content = {'code/'+p:text.encode() for p,text in payload.items()}
    for p in run_root.rglob('*'):
        require(not p.is_symlink(), 'run contains symlink')
        if p.is_file() and p.suffix in ('.json', '.log'):
            content['run/'+str(p.relative_to(run_root))] = p.read_bytes()
    content['replay.py'] = (ROOT/'analysis/paper3_portable_replay.py').read_bytes()
    content['README.md'] = (
        '# Paper 3 held-out validation: offline replay\n\n'
        'Requires Python 3.11+ on macOS or Linux; standard library only. No API key, '
        'network, model weights, or original checkout is needed.\n\n'
        'Run `python3 -I -S replay.py --expected-protocol '+digest(auditor.run.load(run_root/'manifest.json'))+'`. '
        'Exit zero means the saved requests, actions, outcomes, costs and declared source hashes replay; '
        'it does not mean the scientific hypothesis passed. Review `integrity_errors` and all assigned profiles.\n\n'
        'This executes bundled research code, not an arbitrary-code security sandbox. '
        'The replay blocks network and subprocess calls and should be run in a clean environment. '
        'Manifests remain byte-for-byte original, including original local source path labels. '
        'Source-path resolution is adapted, and analysis is a namespace package: '
        'the unrelated plotting/aggregation initializer is not imported. No frozen '
        'game, scoring or replay source bytes are changed.\n\n'
        'Transitive import dependencies absent from the original source list are included as '
        'post-freeze supplements with separate committed-HEAD checks. They are not retroactively '
        'pre-registered. Model weights, provider internals and raw provider authenticity cannot '
        'be verified here. Frozen test source files are provenance, not an advertised standalone '
        'pytest distribution. Twelve selected profiles are not a population reliability estimate.\n'
    ).encode()
    for data in content.values():
        check_credentials(data, secret)
    metadata = dict(format='paper3-disclosure-validation-portable-v1',
                    coordinator_protocol=digest(auditor.run.load(run_root/'manifest.json')),
                    adapter='Resolve original absolute source keys against bundled files; '
                            'use analysis namespace package without unrelated plotting initializer.',
                    files={p:hashlib.sha256(b).hexdigest() for p,b in sorted(content.items())},
                    supplemental_dependencies=supplemental)
    # Exclusive destination creation; failures leave an inspectable incomplete
    # bundle, never an overwritten archive or a falsely successful package.
    target.mkdir(parents=True, exist_ok=False)
    for p,data in content.items():
        dest = safe_path(target, p)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as f:
            f.write(data)
    with (target/'bundle.json').open('x') as f:
        json.dump(metadata, f, indent=2, sort_keys=True)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_root', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    # Exact-secret scan is optional when no local key exists; it is never copied
    # or printed, and the archive/replay itself has no credential dependency.
    secret = None
    if (ROOT/'.env.local').is_file():
        from experiments.paper3_disclosure_validation import base
        secret = base.read_key()
    metadata = build(args.run_root, args.target, secret)
    print(json.dumps(dict(target=str(args.target), protocol=metadata['coordinator_protocol'],
                          files=len(metadata['files']), supplemental_dependencies=len(metadata['supplemental_dependencies']))))


if __name__ == '__main__':
    main()
