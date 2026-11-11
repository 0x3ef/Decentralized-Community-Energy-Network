"""Commission the local demo using the running Compose database and Anvil.

Artifacts and a private output directory are mounted only for this one-off task.
Existing user settings and unrelated data are preserved.
"""

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / "infrastructure/docker/.env"),
    "-f",
    str(ROOT / "infrastructure/docker/compose.prototype.yml"),
]


def update(path, values):
    lines = path.read_text().splitlines() if path.exists() else []
    keep = [line for line in lines if line.split("=", 1)[0] not in values]
    path.write_text(
        "\n".join(keep + [f"{key}={value}" for key, value in values.items()]) + "\n"
    )
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recommission",
        action="store_true",
        help="Replace missing unused local contracts on the SAME database",
    )
    args = parser.parse_args()
    if args.recommission:
        values = dotenv_values(ROOT / "infrastructure/docker/.env")
        if values.get("ENVIRONMENT") != "development" or values.get("CHAIN_ID") not in (
            "31337",
            "1337",
        ):
            raise SystemExit(
                "Repair requires the original local-development env file; no services were stopped"
            )
    directory = ROOT / ".run/demo"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    artifacts = ROOT / "contracts/out"
    if not (artifacts / "CommunityRegistry.sol/CommunityRegistry.json").exists():
        raise SystemExit("Compile contracts first: make contracts-build")
    services = ["worker", "subscriber", *(["api"] if args.recommission else [])]
    subprocess.run([*COMPOSE, "stop", *services], check=True, cwd=ROOT)
    try:
        if args.recommission:
            backup = directory / (
                "sql-backup-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S%f") + ".dump"
            )
            fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                subprocess.run(
                    [
                        *COMPOSE,
                        "exec",
                        "-T",
                        "timescaledb",
                        "pg_dump",
                        "-U",
                        "solar",
                        "-d",
                        "solar",
                        "-Fc",
                    ],
                    stdout=output,
                    check=True,
                    cwd=ROOT,
                )
            print(f"Private database backup created: {backup}", flush=True)
        subprocess.run(
            [
                *COMPOSE,
                "run",
                "--rm",
                "--no-deps",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "-T",
                "-v",
                f"{artifacts}:/artifacts:ro",
                "-v",
                f"{directory}:/run/demo",
                "api",
                "python",
                "-m",
                "src.protocol.recommission"
                if args.recommission
                else "src.protocol.bootstrap",
            ],
            check=True,
            cwd=ROOT,
        )
        data = json.loads((directory / "demo.json").read_text())
        update(
            ROOT / "infrastructure/docker/.env",
            {
                "COMMUNITY_REGISTRY_ADDRESS": data["registry"],
                "GOVERNANCE_TIMELOCK_ADDRESS": data["timelock"],
                "CHAIN_ID": str(data["chain_id"]),
            },
        )
        update(
            ROOT / "apps/frontend/.env.local",
            {
                "VITE_API_URL": "/api/v1",
                "VITE_REGISTRY_ADDRESS": data["registry"],
                "VITE_TIMELOCK_ADDRESS": data["timelock"],
                "VITE_CHAIN_ID": str(data["chain_id"]),
            },
        )
        # Host interpolation settings for the optional simulator overlay.
        update(
            directory / "compose.env",
            {
                "SIMULATOR_ENV_FILE": str(directory / "simulator.env"),
                "SIMULATOR_REGISTRY_FILE": str(directory / "registry.json"),
                "SIMULATOR_CATALOGUE_FILE": str(directory / "home-catalogue.json"),
            },
        )
    finally:
        subprocess.run(
            [
                *COMPOSE,
                "up",
                "-d",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                "90",
                "api",
                "worker",
                "subscriber",
            ],
            check=True,
            cwd=ROOT,
        )
    subprocess.run(
        [*COMPOSE, "up", "-d", "--build", "--no-deps", "frontend"], check=True, cwd=ROOT
    )
    print(
        "Local governed demo ready. Log in as govdemo1@solar.local (operator) or govdemo2@solar.local (consumer)."
    )
    print(
        "Read SEED_PASSWORD from the private infrastructure/docker/.env. Public deployment: .run/demo/demo.json"
    )


if __name__ == "__main__":
    main()
