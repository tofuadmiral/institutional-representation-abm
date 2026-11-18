from pathlib import Path

import pytest

from tests import ci_shards

pytest_plugins = ["pytester"]


def test_every_case_assigned_once_and_modules_stay_together():
    nodes = [f"tests/test_{module}.py::TestCases::test_value[{case}]"
             for module in range(17) for case in range(3)]
    partitions = [ci_shards.partition(nodes, shard, 4) for shard in range(4)]
    assert all(sum(mask[index] for mask in partitions) == 1 for index in range(len(nodes)))
    for mask in partitions:
        assert all(len(set(mask[index:index + 3])) == 1 for index in range(0, len(nodes), 3))
    # Assignment depends on module names, not collection or parameter ordering.
    assert ci_shards.partition(nodes[::-1], 2, 4)[::-1] == partitions[2]


@pytest.mark.parametrize("shard,count", [(-1, 4), (4, 4), (0, 0)])
def test_invalid_partition_fails(shard, count):
    with pytest.raises(pytest.UsageError):
        ci_shards.partition([], shard, count)


def test_pytest_runs_every_module_once_across_shards(pytester):
    pytester.makepyfile(shard_plugin=Path(ci_shards.__file__).read_text())
    pytester.makeconftest('pytest_plugins = ["shard_plugin"]')
    pytester.makepyfile(test_a="def test_a(): assert True", test_b="def test_b(): assert True")
    pytester.runpytest_subprocess("-q").assert_outcomes(passed=2)
    for shard in (0, 1):
        pytester.runpytest_subprocess("-q", "--ci-shard", str(shard), "--ci-shards", "2").assert_outcomes(
            passed=1, deselected=1,
        )
