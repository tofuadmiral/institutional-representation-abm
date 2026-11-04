"""Small private packaging checks, never experimental observations."""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("_office_archive_tests",
    REPO / "analysis/paper3_office_sacrifice_archive_v1.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def test_exact_and_generic_credentials_and_real_isolation_required(tmp_path):
    h = a.helper(REPO)
    for value, secret in ((b'private-test-key', 'private-test-key'),
                           (b'Bearer ' + b'x'*40, None),
                           (b'sk-or-v1-' + b'x'*40, None)):
        with pytest.raises(ValueError):
            h.credentials(value, secret)
    h.credentials(b'ordinary research data')
    with pytest.raises(ValueError, match='actual fresh Python'):
        a.replay('not-an-experiment')
    for event in ('socket.connect', 'urllib.Request', 'subprocess.Popen', 'os.system'):
        with pytest.raises(RuntimeError):
            h.offline_guard(event, ())


def test_actual_zip_extract_hashes_paths_symlinks_and_duplicate_rejection(tmp_path):
    h = a.helper(REPO)
    for index, kind in enumerate(('valid', 'traversal', 'symlink', 'duplicate', 'changed')):
        directory = tmp_path / str(index)
        directory.mkdir()
        name = '../escape.json' if kind == 'traversal' else 'repo/record.json'
        data = b'{"private_fixture":true}'
        metadata = dict(files={name: h.sha(data)})
        bundle = directory / 'bundle.json'
        bundle.write_text(json.dumps(metadata))
        archive = directory / 'private.zip'
        with zipfile.ZipFile(archive, 'x') as z:
            z.write(bundle, 'bundle.json')
            info = zipfile.ZipInfo(name)
            if kind == 'symlink':
                info.external_attr = (0o120777 << 16)
            z.writestr(info, b'changed' if kind == 'changed' else data)
            if kind == 'duplicate':
                with pytest.warns(UserWarning, match='Duplicate name'):
                    z.writestr(name, data)
        output = directory / 'fresh'
        output.mkdir()
        if kind == 'valid':
            a.extract(archive, output, metadata, bundle, h)
            assert (output / name).read_bytes() == data
        else:
            with pytest.raises(ValueError):
                a.extract(archive, output, metadata, bundle, h)
        assert not (directory / 'escape.json').exists()
