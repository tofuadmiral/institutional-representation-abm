"""Exercise the public/local test boundary, including failure visibility."""
import ast
import json
from pathlib import Path

import pytest

from tests import local_artifacts

pytest_plugins = ["pytester"]


def project(pytester):
    pytester.makepyfile(artifact_plugin=Path(local_artifacts.__file__).read_text())
    pytester.makeconftest('pytest_plugins = ["artifact_plugin"]')
    (pytester.path / "artifact_plugin.json").write_text(json.dumps({
        "test_example.py": {"local/record.json": ["test_history"]},
    }))
    pytester.makepyfile(test_example='''
import json
from pathlib import Path
import pytest

@pytest.mark.parametrize("case", [0, 1])
def test_history(case):
    assert json.loads(Path("local/record.json").read_text()) == {"valid": True}

def test_public():
    assert True
''')


def test_missing_inputs_skip_only_declared_tests(pytester):
    project(pytester)
    result = pytester.runpytest_subprocess("-q", "-rs")
    result.assert_outcomes(passed=1, skipped=2)
    result.stdout.fnmatch_lines(["*Local research artifact unavailable: local/record.json*"])


def test_strict_mode_requires_selected_inputs(pytester):
    project(pytester)
    result = pytester.runpytest_subprocess("--require-local-artifacts", "-q")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*Selected tests require local research artifacts:*"])
    result = pytester.runpytest_subprocess("--require-local-artifacts", "-m", "not local_artifacts", "-q")
    result.assert_outcomes(passed=1, deselected=2)


def test_available_inputs_run_and_corruption_still_fails(pytester):
    project(pytester)
    path = pytester.path / "local/record.json"
    path.parent.mkdir()
    path.write_text('{"valid": true}')
    pytester.runpytest_subprocess("--require-local-artifacts", "-q").assert_outcomes(passed=3)
    path.write_text('{"valid": false}')
    pytester.runpytest_subprocess("-q").assert_outcomes(failed=2, passed=1)


def test_undeclared_missing_file_remains_a_failure(pytester):
    project(pytester)
    pytester.makepyfile(test_regression='''
from pathlib import Path
def test_unexpected_missing_file():
    Path("unexpected.json").read_text()
''')
    pytester.runpytest_subprocess("-q").assert_outcomes(failed=1, passed=1, skipped=2)


def test_registry_rejects_paths_outside_checkout(tmp_path):
    path = tmp_path / "registry.json"
    for bad in ("../secret", "/outside"):
        path.write_text(json.dumps({"test_example.py": {bad: ["test_history"]}}))
        with pytest.raises(ValueError, match="repository-relative"):
            local_artifacts.read_registry(path)


def test_registry_names_existing_tests_and_only_local_artifacts():
    root = Path(__file__).resolve().parents[1]
    modules = {}

    def names(tree, prefix=""):
        found = set()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                found.add(prefix + node.name)
            elif isinstance(node, ast.ClassDef):
                found.update(names(node, prefix + node.name + "::"))
        return found

    for nodeid, paths in local_artifacts.read_registry().items():
        module, name = nodeid.split("::", 1)
        if module not in modules:
            tree = ast.parse((root / module).read_text())
            modules[module] = names(tree)
        assert name in modules[module], f"Stale dependency declaration: {nodeid}"
        assert all(path.startswith(("results/paper3", "paper3/data/")) for path in paths)
