"""Create local credentials without printing or overwriting existing values."""

from pathlib import Path
import secrets
import os
from eth_account import Account

root = Path(__file__).resolve().parents[1]
target = root / "infrastructure" / "docker" / ".env"
if target.exists():
    raise SystemExit("Existing .env preserved; configure it explicitly if needed")
body = (
    (root / ".env.example")
    .read_text()
    .replace("JWT_SECRET=\n", "JWT_SECRET=" + secrets.token_urlsafe(48) + "\n")
    .replace(
        "BACKEND_PRIVATE_KEY=\n",
        "BACKEND_PRIVATE_KEY=" + Account.create().key.hex() + "\n",
    )
)
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write(body)
print("Created private local configuration at infrastructure/docker/.env")
