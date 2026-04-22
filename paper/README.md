# Paper draft

**Status:** first-pass LaTeX scaffold. Sections 1 (Introduction) and 6
(Discussion) are best-guess prose that needs editing; Sections 3–5 are
extracted mechanically from the phase notes and figures.

## Files

- `main.tex` — the paper.
- `references.bib` — BibTeX bibliography.
- `Makefile` — build helpers.

Figures live in `../docs/figures/` and are included via `\graphicspath`.

## Build

Requires a LaTeX distribution (`pdflatex` + `bibtex`). On macOS:

```bash
brew install --cask mactex-no-gui   # or tectonic
cd paper && make                    # produces main.pdf
open main.pdf                       # or: make view
```

With `tectonic` (single command, faster, no bibtex shuffling):

```bash
tectonic main.tex
```

## What to edit first

In rough order of priority for a human pass:

1. **§1 Introduction.** The four paragraphs frame the paper as
   (a) cross-national variation in productivity, (b) three competing
   mechanistic accounts, (c) ABM as attribution method,
   (d) contributions. Push back on the framing if a political-science
   reader would prefer a different organising metaphor —
   "discipline-mediated majority-rule cost" vs. "veto-gate count" vs.
   "formation-rule hierarchy."
2. **§6 Discussion.** §6.1 argues discipline is a *universal aggregation
   mechanism* whose sign flips with scenario. This is one reading of the
   ablation sign-flip between fragmented and polarised; if a domain
   reviewer finds it overreaching, the weaker "discipline-mediated
   majority-rule cost" framing from the original outline is a fallback.
3. **§6.3 Policy implications.** The "discipline reform" suggestion is
   my own and may not be defensible without more careful treatment of
   representation effects. Consider whether to scope this down.
4. **Abstract.** Currently 220 words. JASSS wants 200; trim as needed.

## Reviewer-ready checklist (not yet done)

- [ ] Page limit check for target venue (JASSS is flexible; Political
      Analysis is stricter).
- [ ] Figure captions polished; axis labels checked for units.
- [ ] References spot-checked for correct year/DOI.
- [ ] `\citep` vs `\citet` style audit.
- [ ] Add an Acknowledgements section if relevant.
- [ ] Verify all numeric claims in prose match the CSV fixtures in
      `results/phase_*/` (Phase A–G).
