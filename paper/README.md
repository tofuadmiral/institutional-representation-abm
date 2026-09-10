# Paper 1

JASSS-targeted manuscript: *Why fragmented parliaments stop passing
legislation: Opposition discipline and representation across four
democratic institutions*.

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

Published as [arXiv:2608.24554](https://arxiv.org/abs/2608.24554). The exact
Paper 1 software and manuscript state is frozen at repository release tag
`v1.0.2`, which is archived at DOI
[10.5281/zenodo.22119501](https://doi.org/10.5281/zenodo.22119501). The current
repository also contains Paper 2 in a separate `paper2/` directory; those later
changes are not part of the Paper 1 release artifact.
