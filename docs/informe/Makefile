.PHONY: pdf clean
pdf:
	latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build informe.tex
clean:
	latexmk -C -outdir=build informe.tex
