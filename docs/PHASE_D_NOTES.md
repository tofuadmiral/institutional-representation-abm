# Phase D: Streamlit UI

## What this adds

A Streamlit app that exposes **every** tunable config parameter as a sidebar
slider and lets readers interactively compare scenarios, sweep parameters,
and run ablations without editing code or CSVs.

## Launch

```bash
pip install -r requirements.txt
streamlit run streamlit_app/app.py
```

The app opens at `http://localhost:8501`.

## Layout

**Sidebar (top to bottom):**

- **Simulation controls**: seeds per cell (10–200), base seed, institution
  multi-select.
- **Institution configs**: one collapsible expander per institution
  (parliamentary, republican, premier-presidential, president-parliamentary).
  Each expander has a slider for every tunable field in that institution's
  `Config` dataclass, seeded with the default value. Parliamentary has
  6 sliders; republican 8; premier-presidential 11; president-parliamentary
  12 (extra: `presidential_dismissal_rate`).

**Main area — three tabs:**

### Tab 1 — Scenario Comparison
Pick scenarios and institutions; a "Run comparison" button executes N seeds
per (scenario × institution) cell using the sidebar-tuned configs. Shows:
- Summary table with 95% bootstrap CIs per cell.
- Violin plot across institutions per scenario.
- Pairwise Welch/Cohen's-d table for every institution pair.

### Tab 2 — Parameter Sweep
Pick one institution, one parameter, set min/max/steps. The app builds the
sweep using the *sidebar-tuned* base config as the anchor, so the user can
"set a scenario" via sliders, then turn one of them into a sweep axis. Shows
a passage-rate curve with 95% bootstrap CI and the underlying table.

Scenario-level parameters (`num_parties`, `num_constituencies`, `num_bills`)
are also sweepable — they're coerced to integers automatically.

### Tab 3 — Mechanism Ablations
Run the full ablation harness (no_committees / no_discipline / no_veto) for
the selected institutions across the selected scenarios. Shows the Δ table
and the ablation forest plot.

## Caching

All three tabs use `@st.cache_data` keyed on the full parameter set. Dragging
a slider that isn't in the current computation path doesn't re-execute;
pressing the same "Run" button twice with identical inputs is free.

## Why this shape

The user's ask was *sliders over all config*. We combined that with both
interaction modes the sidebar actually supports:

- **Scenario comparison** is the "hypothesis test" workflow: fix the sliders,
  pick scenarios, compare. Good for "does changing X break parliamentary
  passage under fragmentation?" questions.
- **Parameter sweep** is the "exploration" workflow: lock the scenario, turn
  one slider into a variable, watch the curve. Good for "how much does Y
  matter?" questions.
- **Ablations** is the "mechanism attribution" workflow. Separated because
  the thing being varied (which mechanism is disabled) is structurally
  different from a slider knob.

## Files

- `streamlit_app/__init__.py` — package marker.
- `streamlit_app/configs.py` — `SLIDER_SPECS` (min/max/step/default per field),
  `build_configs_from_sidebar()`.
- `streamlit_app/runners.py` — `run_custom_multiseed`, `run_custom_sweep` that
  accept user-supplied configs.
- `streamlit_app/app.py` — main entry point.
- `experiments/parameter_sweep.py` — reusable sweep primitive (used by both
  the app and by CLI experiments).
- `tests/test_streamlit_app.py` — import smoke test, slider-spec sanity,
  sweep monotonicity, custom-config round-trip.

## What changes for later phases

Phase E (paper): the Streamlit app is reproducibility infrastructure. Every
figure in the paper will be reproducible from the CLI runners, but a reader
who wants to dial the knobs themselves can use the app without writing
Python. Both links go in the paper's "Reproducibility" section.
