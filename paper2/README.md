# Paper 2: Evidence-Gated Authority in LLM Review Institutions

Working manuscript for *Who May Overrule the Agent? Evidence-Gated Authority
in LLM Review Institutions*.

The paper studies a two-agent decision pipeline: an upstream language-model
agent proposes a binding action and a second language-model agent reviews it.
The experimental treatment changes only the reviewer's jurisdiction:

- **Broad override:** the reviewer may replace any proposal.
- **Evidence gate:** the reviewer may replace a proposal only after producing a
  valid record that demonstrates a binding-constraint violation and names a
  compliant repair.

The central result is a correction–corruption tradeoff. Broader review can
repair more suboptimal decisions, but it also changes correct decisions.
Evidence-gated authority protects correct and compliant proposals, while its
exact-welfare advantage depends on the upstream mix of correct, violating, and
compliant-but-suboptimal proposals.

## Reproduce the paper from frozen outputs

From the repository root:

```bash
python paper2/scripts/build_artifacts.py
cd paper2 && make
```

The first command regenerates every manuscript table and figure from
`paper2/data/processed/`; it does not call a language model. The second command
builds the PDF with `pdflatex` and `bibtex`.

## Rerun model experiments

The model runs use an OpenAI-compatible local endpoint. See the command
examples in the top-level README. Rerunning requires the two named open-weight
models and enough memory for the selected model. The checked-in completion
cache makes model inference unnecessary for auditing the published numbers.

## Layout

- `main.tex`: manuscript
- `references.bib`: bibliography
- `data/`: frozen parsed results and raw request/response archive
- `scripts/build_artifacts.py`: deterministic figure/table builder
- `figures/`: generated figures
- `tables/`: generated LaTeX tables
