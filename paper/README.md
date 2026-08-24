# Paper

JASSS-targeted manuscript: *Why parliamentary systems collapse under
fragmentation: Opposition cohesion, not government formation failure*.

## Files

- `main.tex` — the paper.
- `references.bib` — bibliography (all entries verified against publisher
  records; see `docs/PHASE_H_NOTES.md` for the audit trail).
- `poster.tex` — A0 conference poster (tikzposter).
- `Makefile` — build helpers.

Figures live in `../docs/figures/` and are included via `\graphicspath`.

## Build

```bash
brew install tectonic        # single binary, auto-fetches packages
cd paper && tectonic main.tex && tectonic poster.tex
```

or with a classic TeX distribution: `make` (`pdflatex` + `bibtex`).

The arXiv submission bundle is built separately: figures copied alongside
`main.tex`, `\graphicspath` flattened, date frozen — see
`arxiv_submission/` (gitignored) and `../arxiv_submission.tar.gz`.

## Status

Preprint-ready. Phase H reworked the fragmentation-collapse attribution
(hung-parliament decomposition); reviewer feedback added the clustered-init
robustness check and preference-variation citations. Remaining before JASSS:
domain review of §6's aggregation framing and an ODD appendix embedded in
the paper body.
