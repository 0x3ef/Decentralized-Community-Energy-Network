# Usa pdfLaTeX cuando existe; en otro caso, el comando latex de TeX Live.
# informe.tex selecciona salida PDF al ejecutarse con pdfTeX.
COMPILADOR ?= $(shell command -v pdflatex 2>/dev/null || command -v latex 2>/dev/null)
LATEX_FLAGS := -interaction=nonstopmode -halt-on-error -output-directory=build

.PHONY: pdf clean
pdf:
	@test -n "$(COMPILADOR)" || { echo "Instala una distribucion LaTeX con latex o pdflatex."; exit 1; }
	mkdir -p build
	$(COMPILADOR) $(LATEX_FLAGS) informe.tex
	$(COMPILADOR) $(LATEX_FLAGS) informe.tex
	$(COMPILADOR) $(LATEX_FLAGS) informe.tex

clean:
	rm -rf build

.PHONY: archivo-unico
archivo-unico:
	python unir_fuentes.py
