"""Initialize a NEW local installation; never rewrite existing credentials."""

import os
import secrets
import subprocess
from pathlib import Path

from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "infrastructure/docker/.env"


def main():
    if TARGET.exists():
        print("Retained the existing private infrastructure/docker/.env unchanged")
        return
    exists = subprocess.run(
        ["docker", "volume", "inspect", "solar-prototype_postgres"], capture_output=True
    )
    if exists.returncode == 0:
        raise SystemExit(
            "Existing PostgreSQL volume: restore the original private .env; no credentials were generated"
        )
    values = {
        "JWT_SECRET": secrets.token_urlsafe(48),
        "BACKEND_PRIVATE_KEY": Account.create().key.hex(),
        "SEED_PASSWORD": secrets.token_urlsafe(24),
        "SEED_DEVICE_KEY": secrets.token_urlsafe(48),
    }
    lines = (ROOT / ".env.example").read_text().splitlines()
    body = [line for line in lines if line.split("=", 1)[0] not in values]
    fd = os.open(TARGET, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(
            "\n".join(body + [f"{key}={value}" for key, value in values.items()]) + "\n"
        )
        output.flush()
        os.fsync(output.fileno())
    print("Created private local configuration at infrastructure/docker/.env")


if __name__ == "__main__":
    main()
