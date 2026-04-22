TEX = pdflatex
BIB = bibtex
MAIN = main

.PHONY: all clean view

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex references.bib
	$(TEX) -interaction=nonstopmode $(MAIN).tex
	$(BIB) $(MAIN)
	$(TEX) -interaction=nonstopmode $(MAIN).tex
	$(TEX) -interaction=nonstopmode $(MAIN).tex

view: $(MAIN).pdf
	open $(MAIN).pdf

clean:
	rm -f $(MAIN).aux $(MAIN).bbl $(MAIN).blg $(MAIN).log $(MAIN).out \
	      $(MAIN).toc $(MAIN).lof $(MAIN).lot $(MAIN).fls \
	      $(MAIN).fdb_latexmk $(MAIN).synctex.gz

distclean: clean
	rm -f $(MAIN).pdf
