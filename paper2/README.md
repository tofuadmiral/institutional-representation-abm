# Paper 2: Evidence-Gated Authority in LLM Review Institutions

Working manuscript for *Who May Overrule the Agent? Evidence-Gated Authority
in LLM Review Institutions*.

The paper studies a two-agent decision pipeline: an upstream language-model
agent proposes a binding action and a second language-model agent reviews it.
The primary controlled treatment changes only the reviewer's jurisdiction:

- **Broad override:** the reviewer may replace any proposal.
- **Evidence gate:** the reviewer may replace a proposal only after producing a
  valid record that demonstrates a binding-constraint violation and names a
  compliant repair.

The central result is a correction–corruption tradeoff shaped by two separate
institutional choices: the action interface that induces a reviewer policy and
the jurisdiction rule that determines which actions bind. The authorization
rule mechanically preserves some proposal states, while the empirical
contribution measures reviewer transition rates and tests an explicit
retain/replace/escalate interface. That interface eliminates correct-proposal
corruption for Qwen but not for Mistral, and it makes Qwen decline useful
welfare-only repairs. No tested interface or authority rule universally
maximizes exact welfare.

## Reproduce the paper from frozen outputs

From the repository root:

```bash
python paper2/scripts/build_artifacts.py
cd paper2 && make
```

The first command regenerates every manuscript table and figure from
`paper2/data/processed/`; it does not call a language model. The second command
builds the PDF with `pdflatex` and `bibtex`.

The cross-model action-aware summaries can be rebuilt from the frozen row-level
tables with `experiments/analyze_action_aware_validation.py`; the checked-in
summary CSVs are the direct inputs to the manuscript table builder.

## Build the arXiv submission package

From the repository root:

```bash
make -C paper2 arxiv-package
```

This creates `paper2/arxiv-submission.tar.gz` containing only the manuscript
source, generated bibliography, bibliography database and style, tables, and
PDF figures needed by arXiv. The package excludes experiment data, raw model
responses, PNG previews, and repository code. To validate it independently,
extract it in an empty directory and run `pdflatex main.tex` twice; the included
`main.bbl` means BibTeX is not required by arXiv's build step.

## Rerun model experiments

The model runs use an OpenAI-compatible local endpoint. See the command
examples in the top-level README. Rerunning requires the two named open-weight
models and enough memory for the selected model. The checked-in completion
cache makes model inference unnecessary for auditing the published numbers.

### Frozen action-aware reviewer validation

The prospective comparator validation uses the first 16 multi-eligible tasks
from each spatial conflict scenario at base seed 95,000. Each task is evaluated
with exact-correct, constraint-violating, and compliant-suboptimal proposals.
The reviewer must explicitly choose `retain`, `replace`, or `escalate`; the run
uses temperature zero, a 160-token response limit, and the existing
deterministic option order. These constants are fixed in
`experiments/action_aware_reviewer_validation.py`.

Run each model separately against a local OpenAI-compatible endpoint:

```bash
# Start Qwen in the answer-only mode used by the Paper 2 experiments.
mlx_lm.server --model mlx-community/Qwen3-8B-4bit \
  --chat-template-args '{"enable_thinking":false}' \
  --host 127.0.0.1 --port 8000

python -m experiments.action_aware_reviewer_validation \
  --model mlx-community/Qwen3-8B-4bit --workers 8 \
  --output results/paper2/action_aware_qwen

# Restart the server with Mistral before the second command.
mlx_lm.server \
  --model mlx-community/Mistral-Small-24B-Instruct-2501-4bit \
  --decode-concurrency 4 --prompt-concurrency 4 --prompt-cache-size 4 \
  --host 127.0.0.1 --port 8000

python -m experiments.action_aware_reviewer_validation \
  --model mlx-community/Mistral-Small-24B-Instruct-2501-4bit --workers 4 \
  --output results/paper2/action_aware_mistral
```

## Layout

- `main.tex`: manuscript
- `main.pdf`: locally compiled manuscript
- `references.bib`: bibliography
- `arxiv-submission.tar.gz`: minimal upload-ready arXiv source bundle
- `data/`: frozen parsed results and raw request/response archive
- `scripts/build_artifacts.py`: deterministic figure/table builder
- `figures/`: generated figures
- `tables/`: generated LaTeX tables
