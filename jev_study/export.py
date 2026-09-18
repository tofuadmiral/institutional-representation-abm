"""Export audited synthetic data only; no environment, headers, or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jev_study.audit import audit
from jev_study.analyze_replication import analyze


def export(root, destination, replication=False):
    report = analyze(root) if replication else audit(root)
    if report['not_run']:
        raise ValueError('Refusing to archive incomplete data as a complete study')
    paths = [root / 'manifest.json', root / 'sources.json']
    for folder in ('calls', 'sessions', 'attempts'):
        paths.extend(sorted((root / folder).glob('*.json')))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects the archival snapshot against accidental overwrite.
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as z:
        for path in paths:
            z.write(path, arcname=f'{root.name}/{path.relative_to(root)}')
        z.writestr(f'{root.name}/analysis.json', json.dumps(report, indent=2))
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(paths) + 1
    return dict(path=str(destination), files=len(paths)+1,
                sha256=hashlib.sha256(destination.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--replication', action='store_true')
    args = parser.parse_args()
    print(json.dumps(export(args.root, args.destination, args.replication), indent=2))
