"""Package only a terminal paired-presentation run, preserving frozen sources verbatim.

This exporter and the portable replay adapter are post-freeze tooling, not changes
to the experimental protocol. No model calls. Refuse live data, source changes,
credential content, symlinks, partial writes and existing output paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.paper3_presentation_portable_replay import digest, require, safe_path


def check_credentials(data, secret=None):
    require(not secret or secret.encode() not in data, 'credential found; bundle refused')
    require(not re.search(rb'sk-or-v1-[A-Za-z0-9_-]{24,}', data), 'possible API credential; bundle refused')
    require(not re.search(rb'Bearer\s+[A-Za-z0-9_-]{24,}', data), 'possible bearer credential; bundle refused')


def build(run_root, target, secret=None):
    from analysis import paper3_disclosure_presentation_audit as auditor
    run_root, target = Path(run_root).resolve(), Path(target).absolute()
    require((run_root/'sessions/terminal.json').is_file(), 'run is not terminal; do not package live data')
    require(not target.exists(), 'destination exists; never overwrite a bundle')
    require(not list(run_root.rglob('*.partial')), 'partial writes remain')
    report = auditor.audit(run_root)
    require(not report['integrity_errors'], 'terminal integrity audit failed; do not package')
    frozen = json.loads((run_root/'sources.json').read_text())
    # The current experiment already froze its full local import closure, unlike
    # the earlier validation. Never quietly add imports to its frozen snapshot.
    content = {'code/'+p:text.encode() for p,text in frozen.items()}
    for p in run_root.rglob('*'):
        require(not p.is_symlink(), 'run contains symlink')
        if p.is_file() and p.suffix in ('.json', '.log'):
            content['run/'+str(p.relative_to(run_root))] = p.read_bytes()
    content['replay.py'] = (ROOT/'analysis/paper3_presentation_portable_replay.py').read_bytes()
    content['tools/paper3_presentation_bundle.py'] = Path(__file__).read_bytes()
    content['tools/test_paper3_presentation_bundle.py'] = (ROOT/'tests/test_paper3_presentation_bundle.py').read_bytes()
    protocol = digest(auditor.run.load(run_root/'manifest.json'))
    content['README.md'] = (
        '# Paper 3 paired-presentation check: offline replay\n\n'
        'Original and fixed mapped forms of one selected game, four paired seeds, two balanced waves. '
        'Not eight independent games, a population reliability estimate, or a finished paper. '
        'All eight assigned blocks, four pairs, failures and missing-outcome bounds remain in the readout. '
        'Balanced randomized form order does not establish a pure label-only effect.\n\n'
        'Requires Python 3.11+ on macOS/Linux, standard library only. No original '
        'checkout, site packages, key, network, model weights or inference calls. Run:\n\n'
        '`python3 -I -S replay.py --expected-protocol '+protocol+'`\n\n'
        'Exit zero means saved wire requests, raw-stream accounting, actions, outcomes '
        'and source hashes replay. It does not establish the scientific hypothesis, '
        'provider authenticity, reproducibility of fresh model samples or equilibrium.\n\n'
        'The fresh eight-call gate and all institutional attempts are included in the batch accounting. '
        'An unsuccessful scientific reproduction is not an archive integrity failure.\n\n'
        'All original manifests/snapshots remain byte-for-byte, including historical '
        'absolute path labels. The path adapter resolves those labels against bundled '
        'files. The analysis package initializer is included and hash-checked but is '
        'not executed: an explicit namespace package bypasses unrelated plotting imports. '
        'No experiment, scoring or original audit source is edited.\n\n'
        'The exporter, source-path adapter and packaging tests were developed after '
        'the experiment freeze and are labeled separately, not retroactively preregistered. '
        'The presentation auditor, paired readout and null-usage aggregation were frozen before inference. '
        'Integrity is separate from presentation_diagnostic: instability, contrasts or incomplete '
        'evidence are retained, not repaired or excluded from export.\n\n'
        'All experiment/audit local import dependencies were captured before inference. '
        'Bundled tests are source provenance, not a standalone pytest distribution.\n\n'
        'This executes trusted bundled research code, not an arbitrary-code sandbox. '
        'Read it before executing; the replay blocks network/child-process calls and '
        'should be used in a clean environment.\n'
    ).encode()
    for data in content.values():
        check_credentials(data, secret)
    metadata = dict(format='paper3-disclosure-presentation-portable-v1',
        coordinator_protocol=protocol,
        adapter='Resolve absolute source keys for the frozen presentation auditor; inject analysis namespace package, '
                'retaining but not executing its unrelated plotting initializer.',
        post_freeze_tools=['replay.py', 'tools/paper3_presentation_bundle.py',
                           'tools/test_paper3_presentation_bundle.py'],
        files={p:hashlib.sha256(b).hexdigest() for p,b in sorted(content.items())})
    # Validate all paths before creating anything. No secret is printed or copied.
    for name in content:
        safe_path(target,name)
    target.mkdir(parents=True, exist_ok=False)
    for name,data in content.items():
        destination=safe_path(target,name)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with destination.open('xb') as f:
            f.write(data)
    with (target/'bundle.json').open('x') as f:
        json.dump(metadata,f,indent=2,sort_keys=True)
    return metadata


def archive(target, destination):
    from analysis.paper3_presentation_portable_replay import verify_inventory
    target,destination=Path(target).resolve(),Path(destination).absolute()
    metadata=verify_inventory(target)
    require(not destination.exists(), 'archive exists; never overwrite')
    require(not destination.is_relative_to(target), 'archive cannot be inside its bundle')
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for relative in sorted([*metadata['files'],'bundle.json']):
            z.write(safe_path(target,relative),relative)
    with zipfile.ZipFile(destination) as z:
        require(z.testzip() is None,'archive checksum failure')
        require(set(z.namelist())==set(metadata['files'])|{'bundle.json'},'archive inventory mismatch')
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_root',type=Path)
    parser.add_argument('target',type=Path)
    parser.add_argument('--archive',type=Path)
    args=parser.parse_args()
    secret=None
    if (ROOT/'.env.local').is_file():
        from experiments.paper3_disclosure_presentation import base
        secret=base.read_key()
    metadata=build(args.run_root,args.target,secret)
    sha=archive(args.target,args.archive) if args.archive else None
    print(json.dumps(dict(target=str(args.target),protocol=metadata['coordinator_protocol'],
        files=len(metadata['files']),archive=str(args.archive) if args.archive else None,sha256=sha)))


if __name__=='__main__':
    main()
