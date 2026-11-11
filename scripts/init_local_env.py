"""Create local credentials without printing or overwriting existing values."""

from pathlib import Path
import secrets
import os
from eth_account import Account

root = Path(__file__).resolve().parents[1]
target = root / "infrastructure" / "docker" / ".env"
body = (
    (root / ".env.example")
    .read_text()
    .replace("JWT_SECRET=\n", "JWT_SECRET=" + secrets.token_urlsafe(48) + "\n")
    .replace(
        "BACKEND_PRIVATE_KEY=\n",
        "BACKEND_PRIVATE_KEY=" + Account.create().key.hex() + "\n",
    )
)
if target.exists():
    body = target.read_text()
else:
    # Existing settings are never replaced. New seed credentials are local-only.
    pass
for name, length in (("SEED_PASSWORD",24),("SEED_DEVICE_KEY",48)):
    if not any(line.startswith(name+"=") and line.split("=",1)[1] for line in body.splitlines()):
        body += f"\n{name}={secrets.token_urlsafe(length)}\n"
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write(body)
target.chmod(0o600)
print("Prepared private local configuration at infrastructure/docker/.env")
