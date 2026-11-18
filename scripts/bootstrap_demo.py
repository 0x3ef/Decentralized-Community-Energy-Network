"""Compatibility entrypoint; the lifecycle is implemented once in stack.py."""

import argparse
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def validate_repair_environment(path):
    if not path.is_file():
        raise SystemExit(
            "Restore the original infrastructure/docker/.env before repair; no services were stopped"
        )
    values = dotenv_values(path)
    if values.get("ENVIRONMENT", "development") != "development":
        raise SystemExit(
            "Repair requires ENVIRONMENT=development in infrastructure/docker/.env; no services were stopped"
        )
    if values.get("CHAIN_ID", "31337") not in ("31337", "1337"):
        raise SystemExit(
            "Repair requires local CHAIN_ID=31337 or 1337 in infrastructure/docker/.env; no services were stopped"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recommission", action="store_true")
    args = parser.parse_args()
    if args.recommission:
        validate_repair_environment(ROOT / "infrastructure/docker/.env")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/stack.py"),
            "recover" if args.recommission else "up",
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
