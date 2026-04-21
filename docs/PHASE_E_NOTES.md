# Phase E: Paper Scaffold

## What this adds

Paper-ready documentation:

- `docs/ODD_PROTOCOL.md` — formal ODD description per Grimm et al. (2020),
  suitable as a JASSS appendix.
- `docs/PAPER_OUTLINE.md` — JASSS submission skeleton with the lead finding,
  experimental design, candidate figures, and reference list.
- `docs/COMSES_METADATA.md` — deposit card for the CoMSES Computational
  Model Library.
- Updated top-level `README.md` with a documentation index.

The lead finding is reproducible from `docs/figures/ablation_forest.png`
and the table in `PAPER_OUTLINE.md` §5.4. Every paper figure is generated
by the CLI runners documented in the other phase notes.

## Lead finding

> The parliamentary passage collapse under fragmentation is caused by the
> *interaction* between failed coalition formation and strict party
> discipline, not by the coalition rule alone. The `no_discipline` ablation
> restores parliamentary passage from 0.05% to 46.7% under fragmentation,
> and the rescue magnitude falls monotonically across the four institutions
> as their dependence on parliamentary-majority government formation
> decreases (parl +0.466 → premier-pres +0.312 → president-parl +0.233 →
> republican −0.242).

## What's intentionally *not* in this PR

- The paper text itself. Scaffolding is where the roadmap ended; full
  drafting is a separate writing project that benefits from more focused
  review than a PR can give.
- CoMSES *submission*. The metadata card is ready; the actual deposit
  requires an account, a DOI reservation, and a version-pinned release —
  all lightweight but out of scope for the autonomous run.
- Paper figures as PDF. Current PNGs at 150 DPI are fine for web/JASSS;
  the publisher template may want PDFs with specific font embedding, which
  is best handled at submission time.

## What's next

Writing up the paper is a deliberate, reviewed process. The recommended
sequence after waking up:

1. Read `docs/PAPER_OUTLINE.md` end to end. The lead finding's framing is
   my best reading; a political-science reader may want to re-frame it as
   "discipline-mediated majority-rule cost" or similar.
2. Draft §2 (Introduction) and §6 (Discussion) — these are the parts that
   most need a human hand; §4 and §5 mostly paraphrase existing phase notes.
3. Extend sensitivity to the fragmented scenario as a robustness check
   (Phase B only covered baseline for cost reasons).
4. Decide whether to add a fifth institution (e.g., directorial — Switzerland)
   as a robustness point. Not in current scope.
