"""Archive a local demo with a missing registry and commission an isolated one.

Never deletes volumes or reuses historical financial records. Private backups
include a transactional PostgreSQL dump and the old encrypted wallets/settings.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "infrastructure/docker/.env"
COMPOSE_FILE = ROOT / "infrastructure/docker/compose.prototype.yml"


class RecoveryGuardError(ValueError):
    """A fixed, safe-to-display preflight message."""


def call(args, *, capture=False, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=capture, **kwargs)


def private_json(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(data, file, indent=2)
        file.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--new-demo",
        action="store_true",
        help="Archive and replace the local demo after preflight",
    )
    args = parser.parse_args()
    if os.environ.get("COMPOSE_PROJECT_NAME"):
        raise RecoveryGuardError(
            "Unset the shell COMPOSE_PROJECT_NAME before recovery; the active project will be persisted in the private env file"
        )
    values = dotenv_values(ENV_FILE)
    if (
        values.get("ENVIRONMENT") != "development"
        or int(values.get("CHAIN_ID", "0")) != 31337
    ):
        raise RecoveryGuardError("Only the development Anvil demo can be replaced")
    if os.environ.get("ENVIRONMENT", "development") != "development":
        raise RecoveryGuardError("Public/testnet environment variables are not allowed")
    rpc = os.environ.get("DEMO_RPC_URL", "http://127.0.0.1:8545")
    if urlsplit(rpc).hostname not in ("localhost", "127.0.0.1"):
        raise RecoveryGuardError("Recovery requires the local loopback RPC")
    web3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 5}))
    if web3.eth.chain_id != 31337:
        raise RecoveryGuardError("RPC is not the local demo chain")
    demo = json.loads((ROOT / ".run/demo/demo.json").read_text())
    if web3.eth.get_code(demo["registry"]):
        raise RecoveryGuardError(
            "Registry still exists; do not replace canonical history without investigation"
        )
    if not (
        ROOT / "contracts/out/CommunityRegistry.sol/CommunityRegistry.json"
    ).exists():
        raise RecoveryGuardError("Compile contract artifacts before recovery")
    base = ["docker", "compose", "--env-file", str(ENV_FILE), "-f", str(COMPOSE_FILE)]
    configuration = json.loads(
        call([*base, "config", "--format", "json"], capture=True).stdout
    )
    source = configuration["name"]
    if not configuration["services"]["anvil"]["image"].startswith(
        "ghcr.io/foundry-rs/foundry:"
    ):
        raise RecoveryGuardError("Unexpected local node image")
    database_ids = (
        call([*base, "ps", "--all", "--quiet", "timescaledb"], capture=True)
        .stdout.decode()
        .split()
    )
    if len(database_ids) != 1:
        raise RecoveryGuardError(
            "Expected exactly one existing database container for backup"
        )
    print(
        "Preflight: missing local registry confirmed. Existing SQL data and volumes will be retained.",
        flush=True,
    )
    if not args.new_demo:
        print(
            "Run make recover-demo to commission a separate demonstration, not restore lost transactions."
        )
        return
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    target = "solar-recovery-" + stamp
    if call(
        [
            "docker",
            "volume",
            "ls",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={target}",
        ],
        capture=True,
    ).stdout.strip():
        raise RecoveryGuardError("Replacement project already owns volumes")
    backup = ROOT / ".run" / ("recovery-" + stamp)
    backup.mkdir(parents=True, mode=0o700)
    private_json(
        backup / "manifest.json",
        {
            "source_project": source,
            "replacement_project": target,
            "registry_without_code": demo["registry"],
            "observed_genesis": Web3.to_hex(web3.eth.get_block(0).hash),
            "notice": "Replacement local demo; original chain history has not been restored.",
        },
    )
    ids = (
        call(
            [
                "docker",
                "ps",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"label=com.docker.compose.project={source}",
            ],
            capture=True,
        )
        .stdout.decode()
        .split()
    )
    writers = [identifier for identifier in ids if identifier != database_ids[0]]
    if writers:
        print(
            "Stopping the old project writers and simulator; keeping all containers and volumes.",
            flush=True,
        )
        call(["docker", "stop", "--time", "60", *writers], capture=True)
    call(["docker", "start", database_ids[0]], capture=True)
    for _ in range(60):
        ready = subprocess.run(
            [
                "docker",
                "exec",
                database_ids[0],
                "pg_isready",
                "-U",
                "solar",
                "-d",
                "solar",
            ],
            capture_output=True,
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Old database did not become ready; no replacement started")
    print("Writing a private PostgreSQL archive before switching projects.", flush=True)
    dump = backup / "database.dump"
    fd = os.open(dump, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as output:
        call(
            [
                "docker",
                "exec",
                database_ids[0],
                "pg_dump",
                "-U",
                "solar",
                "-d",
                "solar",
                "-Fc",
            ],
            stdout=output,
            stderr=subprocess.DEVNULL,
        )
    if not dump.stat().st_size:
        raise RuntimeError("Database archive is empty; no replacement started")
    call(["docker", "stop", "--time", "60", database_ids[0]], capture=True)
    for old, name in [
        (ENV_FILE, "backend.env"),
        (ROOT / "apps/frontend/.env.local", "frontend.env.local"),
        (ROOT / "apps/frontend/e2e/.native-fixture.json", "browser-fixture.json"),
        (ROOT / ".run/demo", "demo"),
    ]:
        if old.exists():
            shutil.move(str(old), str(backup / name))
    print(
        "Original data retained. Creating fresh credentials, database, MQTT, simulation and chain volumes.",
        flush=True,
    )
    call([sys.executable, str(ROOT / "scripts/init_local_env.py")])
    with ENV_FILE.open("a") as file:
        file.write(f"\nCOMPOSE_PROJECT_NAME={target}\n")
    environment = dict(os.environ)
    environment.update(
        {
            key: value
            for key, value in dotenv_values(ENV_FILE).items()
            if value is not None
        }
    )
    call(
        [*base, "up", "-d", "--build", "--wait", "--wait-timeout", "180"],
        env=environment,
    )
    call([sys.executable, str(ROOT / "scripts/bootstrap_demo.py")], env=environment)
    restored = json.loads((ROOT / ".run/demo/demo.json").read_text())
    if not web3.eth.get_code(restored["registry"]):
        raise RuntimeError("Replacement registry deployment was not verified")
    genesis = Web3.to_hex(web3.eth.get_block(0).hash)
    print(
        "Checking actual named-volume persistence and contract recovery across an Anvil restart.",
        flush=True,
    )
    call([*base, "stop", "worker", "subscriber"], env=environment, capture=True)
    call(
        [
            *base,
            "exec",
            "-T",
            "anvil",
            "sh",
            "-c",
            "test -s /state/anvil.json && test -w /state",
        ],
        env=environment,
    )
    call([*base, "restart", "anvil"], env=environment)
    call(
        [*base, "up", "-d", "--no-deps", "--wait", "--wait-timeout", "90", "anvil"],
        env=environment,
    )
    if Web3.to_hex(web3.eth.get_block(0).hash) != genesis:
        raise RuntimeError(
            "Anvil genesis changed across restart; stop and inspect persistence"
        )
    for field in ("registry", "timelock", "sun", "settlement", "vault"):
        if not web3.eth.get_code(restored[field]):
            raise RuntimeError(
                "Contract missing after restart; no recovered-state claim is made"
            )
    # Re-unlock only the explicit local fixture accounts after node restart.
    call([sys.executable, str(ROOT / "scripts/bootstrap_demo.py")], env=environment)
    print(f"Replacement demo ready. Private backup: {backup}", flush=True)
    print(
        f"Active Compose project: {target}. Existing Make commands read it from the private env file."
    )
    print(
        "Use the NEW SEED_PASSWORD and encrypted wallets. Clear the old browser session and reconnect the new fixture wallet."
    )
    print(
        "Run make demo-scenario and make simulate next. Historical balances remain only in the archived environment."
    )


if __name__ == "__main__":
    try:
        main()
    except RecoveryGuardError as error:
        raise SystemExit(str(error)) from None
    except Exception as error:
        raise SystemExit(
            f"Recovery stopped ({type(error).__name__}). Original volumes are retained. Review .run/recovery-* manifests before resuming; do not delete them."
        ) from None
