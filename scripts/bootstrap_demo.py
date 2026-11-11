"""Commission the local demo using the running Compose database and Anvil.

Artifacts and a private output directory are mounted only for this one-off task.
Existing user settings and unrelated data are preserved.
"""

import json
import os
import subprocess
from pathlib import Path

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
    directory = ROOT / ".run/demo"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    artifacts = ROOT / "contracts/out"
    if not (artifacts / "CommunityRegistry.sol/CommunityRegistry.json").exists():
        raise SystemExit("Compile contracts first: make contracts-build")
    subprocess.run([*COMPOSE, "stop", "worker", "subscriber"], check=True, cwd=ROOT)
    try:
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
                "src.protocol.bootstrap",
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
