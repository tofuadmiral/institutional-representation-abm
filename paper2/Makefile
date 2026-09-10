PYTHON ?= ../.venv/bin/python

.PHONY: all artifacts arxiv-package clean

all: main.pdf

artifacts:
	MPLBACKEND=Agg MPLCONFIGDIR=/private/tmp/matplotlib-paper2 XDG_CACHE_HOME=/private/tmp/fontconfig-paper2 $(PYTHON) scripts/build_artifacts.py

main.pdf: main.tex references.bib tables/state_effects.tex tables/natural_results.tex figures/state_conditional_effects.pdf figures/prevalence_frontiers.pdf figures/natural_proposal_outcomes.pdf
	pdflatex -interaction=nonstopmode -halt-on-error main.tex
	bibtex main
	pdflatex -interaction=nonstopmode -halt-on-error main.tex
	pdflatex -interaction=nonstopmode -halt-on-error main.tex

arxiv-package: main.pdf
	./scripts/build_arxiv_package.sh

clean:
	rm -f main.aux main.bbl main.blg main.log main.out main.pdf arxiv-submission.tar.gz
