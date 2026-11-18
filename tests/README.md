# Running the tests

Install `requirements.txt`, then run `pytest tests/ -ra`. The default suite runs
the self-contained unit, simulation, transport, budget and recovery tests without
provider credentials or paid calls. CI also runs the two simulation smoke tests
in `.github/workflows/ci.yml` and saves the pytest report as a workflow artifact.

Some historical Paper 3 regression tests require local provider records, budget
ledgers or full replay archives that are not distributed in a Git checkout.
`local_artifacts.json` declares these dependencies **per test**, including tests
whose simulated runs still depend on a real historical source manifest. When a
declared input is absent, pytest reports an explicit skip naming that path.
Other tests in the same module still run. No exception or assertion failure is
converted into a skip: existing but invalid or incomplete artifacts still fail
their original checks. Frozen experiment sources and validators are unchanged.

To require the full historical suite in an appropriately provisioned checkout:

```sh
pytest tests/ --require-local-artifacts
```

That option fails collection if a selected test lacks declared local inputs.
`-m local_artifacts` selects historical tests; `-m 'not local_artifacts'` selects
the independent tests. A green public CI run does **not** certify a historical
experiment or its private ledger. Historical audits remain separate.

When adding tests, prefer synthetic fixtures. For an intentional historical
regression, declare the exact required inputs with
`@pytest.mark.local_artifacts("results/paper3/.../record.json")` or add its test
name and prerequisites to the registry. Never register a missing implementation
file or an ordinary regression just to make CI pass.
