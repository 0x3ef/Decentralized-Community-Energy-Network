"""One local Docker lifecycle. Never removes a volume or replaces PostgreSQL.

All commands use the same Compose project/files. Recovery means a new LOCAL chain
on the SAME database, with old financial records retained and explicitly archived.
"""

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def update(path, values):
    lines = path.read_text().splitlines() if path.exists() else []
    retained = [line for line in lines if line.split("=", 1)[0] not in values]
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(
            "\n".join(retained + [f"{k}={v}" for k, v in values.items()]) + "\n"
        )
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


class Stack:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.env = self.root / "infrastructure/docker/.env"
        self.directory = self.root / ".run/demo"

    @property
    def project(self):
        value = dotenv_values(self.env).get("COMPOSE_PROJECT_NAME", "solar-prototype")
        shell = os.environ.get("COMPOSE_PROJECT_NAME")
        if shell and shell != value:
            raise ValueError(
                "Unset shell COMPOSE_PROJECT_NAME; the original private env file selects the database project"
            )
        return value

    @property
    def base(self):
        return [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--env-file",
            str(self.env),
            "-f",
            str(self.root / "infrastructure/docker/compose.prototype.yml"),
            "-f",
            str(self.root / "infrastructure/docker/compose.iot.yml"),
            "--profile",
            "simulation",
        ]

    def run(self, args, capture=False, **kwargs):
        return subprocess.run(
            args, cwd=self.root, check=True, capture_output=capture, text=True, **kwargs
        )

    def compose(self, *args, capture=False):
        return self.run([*self.base, *args], capture=capture)

    def ensure(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.env.exists():
            exists = subprocess.run(
                ["docker", "volume", "inspect", "solar-prototype_postgres"],
                capture_output=True,
            )
            if exists.returncode == 0:
                raise ValueError(
                    "Existing PostgreSQL volume found: restore the original infrastructure/docker/.env; credentials will not be regenerated"
                )
            self.run([sys.executable, "scripts/init_local_env.py"])
        values = dotenv_values(self.env)
        if (
            values.get("ENVIRONMENT", "development") != "development"
            or values.get("CHAIN_ID", "31337") != "31337"
        ):
            raise ValueError(
                "This lifecycle is only for local development chain 31337; use the separate Sepolia deployment workflow"
            )
        if any(
            not values.get(key)
            for key in (
                "JWT_SECRET",
                "BACKEND_PRIVATE_KEY",
                "SEED_PASSWORD",
                "SEED_DEVICE_KEY",
            )
        ):
            raise ValueError(
                "Restore the original private credentials in infrastructure/docker/.env; no existing values will be replaced"
            )

    def build(self, *services):
        self.ensure()
        for service in services or ("api", "anvil", "frontend", "simulator"):
            # Serial builds avoid rebuilding the same backend once per dependent service.
            self.compose("build", service)

    def start(self, services, dependencies=True):
        args = ["up", "-d", "--no-build", "--wait", "--wait-timeout", "180"]
        if not dependencies:
            args += ["--no-deps"]
        try:
            result = self.compose(*args, *services, capture=True)
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
        except subprocess.CalledProcessError as error:
            message = (error.stdout or "") + (error.stderr or "")
            if "network" not in message.lower() or "not found" not in message.lower():
                print(message, file=sys.stderr)
                raise
            print(
                "Recreating containers with stale network references; named volumes are retained.",
                flush=True,
            )
            self.compose(*args, "--force-recreate", *services)

    def stop_writers(self):
        self.compose("stop", "simulator", "api", "worker", "subscriber")

    def running(self, service):
        return bool(
            self.compose(
                "ps", "--status", "running", "--quiet", service, capture=True
            ).stdout.strip()
        )

    def backend(self, module, capture=False):
        artifacts = self.root / "contracts/out"
        return self.compose(
            "run",
            "--rm",
            "--no-deps",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-T",
            "-v",
            f"{artifacts}:/artifacts:ro",
            "-v",
            f"{self.directory}:/run/demo",
            "api",
            "python",
            "-m",
            module,
            capture=capture,
        )

    def status(self):
        result = self.backend("src.protocol.local_status", capture=True)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def backup(self):
        self.ensure()
        self.start(["timescaledb"])
        directory = (
            self.root / ".run/backups" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        )
        directory.mkdir(parents=True, mode=0o700)
        dump = directory / "database.dump"
        fd = os.open(dump, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as output:
            subprocess.run(
                [
                    *self.base,
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
                cwd=self.root,
                stdout=output,
                check=True,
            )
        if not dump.stat().st_size:
            raise RuntimeError("Empty SQL backup; recovery will not continue")
        with dump.open("rb") as source:
            subprocess.run(
                [*self.base, "exec", "-T", "timescaledb", "pg_restore", "--list"],
                cwd=self.root,
                stdin=source,
                stdout=subprocess.DEVNULL,
                check=True,
            )
        shutil.copy2(self.env, directory / "backend.env")
        metadata = directory / "demo"
        metadata.mkdir(mode=0o700)
        for name in (
            "demo.json",
            "deployment.json",
            "scenario.json",
            "scenario-report.json",
            "simulator.env",
            "registry.json",
            "home-catalogue.json",
            "compose.env",
            "wallets",
            "last-recovery.json",
            "recovery-in-progress.json",
            "scenario-baseline.json",
        ):
            source = self.directory / name
            if source.is_dir():
                shutil.copytree(source, metadata / name)
            elif source.is_file():
                shutil.copy2(source, metadata / name)
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "project": self.project,
                    "notice": "Same PostgreSQL database and named volumes retained",
                },
                indent=2,
            )
        )
        print(f"Private verified SQL archive: {dump}", flush=True)
        return directory

    def migrate(self):
        self.compose("run", "--rm", "--no-deps", "migrate")

    def artifacts(self):
        if not (
            self.root / "contracts/out/CommunityRegistry.sol/CommunityRegistry.json"
        ).exists():
            self.run(["make", "contracts-build"])

    def configure(self):
        data = json.loads((self.directory / "demo.json").read_text())
        update(
            self.env,
            {
                "COMMUNITY_REGISTRY_ADDRESS": data["registry"],
                "GOVERNANCE_TIMELOCK_ADDRESS": data["timelock"],
                "CHAIN_ID": "31337",
            },
        )
        update(
            self.root / "apps/frontend/.env.local",
            {
                "VITE_API_URL": "/api/v1",
                "VITE_REGISTRY_ADDRESS": data["registry"],
                "VITE_TIMELOCK_ADDRESS": data["timelock"],
                "VITE_CHAIN_ID": "31337",
            },
        )
        # Compatibility with old manually typed Compose commands; lifecycle does not depend on it.
        update(
            self.directory / "compose.env",
            {
                "SIMULATOR_ENV_FILE": str(self.directory / "simulator.env"),
                "SIMULATOR_REGISTRY_FILE": str(self.directory / "registry.json"),
                "SIMULATOR_CATALOGUE_FILE": str(self.directory / "home-catalogue.json"),
            },
        )

    def ready(self):
        self.build("frontend")
        self.start(["api", "worker", "subscriber", "frontend"], dependencies=False)
        print(
            "Application started. http://127.0.0.1:8080 | readiness: http://127.0.0.1:8000/ready",
            flush=True,
        )

    def checkpoint(self):
        self.compose(
            "exec", "-T", "anvil", "python", "/opt/anvil_supervisor.py", "checkpoint"
        )

    def up(self, simulate=False):
        self.ensure()
        simulate = simulate or self.running("simulator")
        self.artifacts()
        self.build("api", "anvil")
        self.stop_writers()
        self.start(["timescaledb", "redis", "mosquitto", "anvil"])
        self.migrate()
        state = self.status()["state"]
        if state not in ("READY", "EMPTY"):
            raise ValueError(
                f"Local deployment is {state}. PostgreSQL is retained. Run make recover to archive lost-chain history and recommission on the same database"
            )
        if state == "READY" and not (self.directory / "deployment.json").is_file():
            raise ValueError(
                "Existing contracts found but the deployment journal is missing. Restore the original .run/demo/deployment.json; existing contracts and balances will not be replaced"
            )
        self.backend("src.protocol.bootstrap")
        self.configure()
        self.checkpoint()
        self.ready()
        if simulate:
            self.build("simulator")
            self.start(["simulator"], dependencies=False)

    def recover(self):
        self.ensure()
        self.artifacts()
        self.build("api", "anvil")
        self.stop_writers()
        self.start(["timescaledb", "redis", "mosquitto"])
        self.migrate()
        state = self.status()
        if state["state"] == "EMPTY":
            raise ValueError(
                "No governed deployment exists in this database; use make setup"
            )
        if state["state"] == "RPC_UNAVAILABLE":
            inspection = self.compose(
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "python",
                "anvil",
                "/opt/anvil_supervisor.py",
                "inspect",
                capture=True,
            )
            if json.loads(inspection.stdout)["state"] == "valid":
                # A stopped or disconnected node is not a lost chain. Restore
                # its existing checkpoint before considering a replacement.
                self.start(["anvil"])
                state = self.status()
        marker = self.directory / "recovery-in-progress.json"
        resume = (
            bool(state.get("genesis"))
            and marker.exists()
            and json.loads(marker.read_text()).get("genesis") == state.get("genesis")
        )
        if state["state"] == "READY" and not resume:
            print(
                "Existing contracts are deployed. No chain reset performed; use make up or make simulate."
            )
            self.up(simulate=True)
            return
        if not resume:
            archive = self.backup()
            self.compose("stop", "anvil")
            self.compose(
                "run",
                "--rm",
                "--no-deps",
                "--entrypoint",
                "python",
                "anvil",
                "/opt/anvil_supervisor.py",
                "reset",
            )
            for name in (
                "deployment.json",
                "scenario.json",
                "scenario-report.json",
                "scenario-baseline.json",
            ):
                source = self.directory / name
                if source.exists():
                    source.rename(archive / name)
            self.start(["anvil"])
            state = self.status()
            update_marker = {"genesis": state["genesis"], "backup": str(archive)}
            update_path = marker.with_suffix(".tmp")
            update_path.write_text(json.dumps(update_marker))
            update_path.chmod(0o600)
            os.replace(update_path, marker)
        self.backend("src.protocol.local_recovery")
        self.configure()
        # Force a durable checkpoint before accepting application writes.
        self.checkpoint()
        self.ready()
        self.build("simulator")
        self.start(["simulator"], dependencies=False)
        marker.unlink(missing_ok=True)
        print(
            "Recovery complete on the SAME PostgreSQL database. Old financial records remain archived; balances were not recreated."
        )

    def doctor(self):
        self.compose("ps", "-a")
        usage = shutil.disk_usage(self.root)
        print(
            f"Workspace free: {usage.free // (1024**3)} GiB. Original Compose project: {self.project}"
        )
        try:
            print("Deployment:", self.status())
        except Exception:
            print(
                "Deployment inspection unavailable; build updated images and inspect anvil logs."
            )
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8000/ready", timeout=10
            ) as response:
                print(response.read().decode())
        except urllib.error.HTTPError as error:
            print(error.read().decode())
        except OSError:
            print(
                "API is not reachable. Use make up; use make recover for lost/corrupt local-chain state."
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "setup",
            "build",
            "up",
            "simulate",
            "recover",
            "backup",
            "doctor",
            "down",
            "logs",
            "ps",
            "clean",
        ],
    )
    args = parser.parse_args()
    stack = Stack()
    (ROOT / ".run").mkdir(exist_ok=True, mode=0o700)
    with (ROOT / ".run/stack.lock").open("a") as lock:
        if args.command not in ("logs", "ps", "doctor"):
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit(
                    "Another lifecycle command is running; wait for it to finish"
                ) from None
        if args.command in ("setup", "up", "simulate"):
            stack.up(simulate=args.command == "simulate")
        elif args.command == "build":
            stack.build()
        elif args.command == "recover":
            stack.recover()
        elif args.command == "backup":
            stack.backup()
        elif args.command == "doctor":
            stack.doctor()
        elif args.command == "down":
            stack.compose("down", "--timeout", "60")
        elif args.command == "logs":
            stack.compose("logs", "--tail", "100", "-f")
        elif args.command == "ps":
            stack.compose("ps", "-a")
        elif args.command == "clean":
            for directory in (
                "contracts/out",
                "contracts/cache",
            ):
                shutil.rmtree(ROOT / directory, ignore_errors=True)
            print(
                "Build artifacts removed. No containers, volumes, SQL records or private configuration were removed."
            )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
    except subprocess.CalledProcessError:
        raise SystemExit(
            "Lifecycle command failed; retained all database volumes and records. Run make doctor and inspect the failed service logs."
        ) from None
