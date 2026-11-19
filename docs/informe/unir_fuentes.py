"""Exportar el informe a un unico .tex sin archivos de entrada externos."""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = re.compile(r"\\input\{([^}]+)\}")


def expand(path, parents=()):
    path = path.resolve()
    if not path.is_relative_to(ROOT) or path in parents:
        raise ValueError("Ruta de entrada no permitida o circular")
    source = path.read_text(encoding="utf-8")

    def include(match):
        child = ROOT / match.group(1)
        if not child.suffix:
            child = child.with_suffix(".tex")
        return "\n" + expand(child, (*parents, path)) + "\n"

    return INPUT.sub(include, source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output", nargs="?", default=str(ROOT / "build/informe_texmaker.tex")
    )
    args = parser.parse_args()
    output = Path(args.output)
    source = expand(ROOT / "informe.tex")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(source, encoding="utf-8")
    print(f"Archivo independiente creado: {output}")


if __name__ == "__main__":
    main()
