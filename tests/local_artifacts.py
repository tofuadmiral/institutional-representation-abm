"""Declare historical-data dependencies without hiding ordinary test failures."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest


REGISTRY = Path(__file__).with_suffix(".json")


def read_registry(path=REGISTRY):
    dependencies = {}
    for module, groups in json.loads(Path(path).read_text()).items():
        for artifact, names in groups.items():
            relative = PurePosixPath(artifact)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Artifact must be repository-relative: {artifact}")
            for name in names:
                dependencies.setdefault(f"{module}::{name}", set()).add(artifact)
    return dependencies


def missing_artifacts(root, paths):
    return tuple(sorted(path for path in paths if not (Path(root) / path).exists()))


def pytest_addoption(parser):
    parser.addoption(
        "--require-local-artifacts", action="store_true",
        help="Fail collection if a selected historical test lacks its local research artifacts.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "local_artifacts(*paths): requires the named local research records or archives",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    dependencies = read_registry()
    for item in items:
        # All parameter cases of a test have the same declared input dependency.
        paths = dependencies.get(item.nodeid.split("[", 1)[0], ())
        if paths:
            item.add_marker(pytest.mark.local_artifacts(*sorted(paths)))
        paths = set(paths)
        for marker in item.iter_markers("local_artifacts"):
            paths.update(marker.args)
        missing = missing_artifacts(config.rootpath, paths)
        if missing and not config.getoption("--require-local-artifacts"):
            item.add_marker(pytest.mark.skip(reason="Local research artifact unavailable: " + ", ".join(missing)))


def pytest_collection_finish(session):
    # Run after -m/-k selection, so strict mode only requires selected inputs.
    if not session.config.getoption("--require-local-artifacts"):
        return
    missing = set()
    for item in session.items:
        for marker in item.iter_markers("local_artifacts"):
            missing.update(missing_artifacts(session.config.rootpath, marker.args))
    if missing:
        raise pytest.UsageError("Selected tests require local research artifacts:\n" + "\n".join(sorted(missing)))
