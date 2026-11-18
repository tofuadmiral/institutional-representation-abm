"""Optional CI partitioning by test module; fixtures and parameter cases stay together."""
import pytest


def pytest_addoption(parser):
    parser.addoption("--ci-shard", type=int, default=None, help="Zero-based CI shard to run.")
    parser.addoption("--ci-shards", type=int, default=4, help="Number of CI shards.")


def partition(nodeids, shard, count):
    if count < 1 or not 0 <= shard < count:
        raise pytest.UsageError("Require --ci-shards >= 1 and 0 <= --ci-shard < --ci-shards")
    modules = sorted({nodeid.split("::", 1)[0] for nodeid in nodeids})
    selected = set(modules[shard::count])
    return [nodeid.split("::", 1)[0] in selected for nodeid in nodeids]


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    shard = config.getoption("--ci-shard")
    if shard is None:
        return
    mask = partition([item.nodeid for item in items], shard, config.getoption("--ci-shards"))
    selected = [item for item, keep in zip(items, mask) if keep]
    deselected = [item for item, keep in zip(items, mask) if not keep]
    items[:] = selected
    config.hook.pytest_deselected(items=deselected)
