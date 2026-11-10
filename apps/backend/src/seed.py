"""Idempotent development data using the canonical SQLModel entities.

No telemetry, energy credits, token balances or verified wallet ownership are
fabricated. Call inside one caller-owned transaction after Alembic migrations.
"""

from __future__ import annotations
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession
from src.core.config import Config
from src.core.db import AsyncSessionFactory
import src.modules.energy.models  # noqa: F401 - registers Home.intervals relationships
from src.modules.auth.models import User
from src.modules.auth.utils import generate_passwd_hash
from src.modules.home.models import Home
from src.modules.device.models import Device
from src.modules.wallet.models import Wallet
from src.modules.community.models import (
    EnergyCommunity,
    CommunityMembership,
    CommunityNode,
    MeterAuthorization,
)

# Stable IDs retained from the old demo SQL; device_id is a separate public UUID.
CATALOGUE = ((4, 10), (6, 0), (0, 0), (0, 5), (3, 0))


def identifier(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, "solar-market-demo:" + name)


async def seed_demo(
    session: AsyncSession, password: str, device_key: str | None = None
) -> dict:
    if Config.ENVIRONMENT != "development":
        raise ValueError("Demo seed is restricted to development")
    if len(password) < 12:
        raise ValueError("Supply a SEED_PASSWORD of at least 12 characters")
    if device_key is not None and len(device_key) < 32:
        raise ValueError("SEED_DEVICE_KEY requires at least 32 characters")
    await session.execute(text("SELECT pg_advisory_xact_lock(707031401)"))
    community_id = identifier("community")
    community = await session.get(EnergyCommunity, community_id)
    if community is None:
        session.add(
            EnergyCommunity(id=community_id, name="Cali demonstration community")
        )
        await session.flush()
    registry = {}
    bindings = {}
    for number, (solar, battery) in enumerate(CATALOGUE, start=1):
        digit = str(number)
        user_id = UUID(
            digit * 8
            + "-"
            + digit * 4
            + "-"
            + digit * 4
            + "-"
            + digit * 4
            + "-"
            + digit * 12
        )
        letter = "abcde"[number - 1]
        home_id = UUID(
            letter * 8
            + "-"
            + letter * 4
            + "-"
            + letter * 4
            + "-"
            + letter * 4
            + "-"
            + letter * 12
        )
        code = f"HOME-MS-{number:03d}"
        user = await session.get(User, user_id)
        if user is None:
            session.add(
                User(
                    uid=user_id,
                    username=f"demo{number}",
                    email=f"demo{number}@solar.local",
                    first_name="Demo",
                    last_name=f"Member {number}",
                    password_hash=generate_passwd_hash(password),
                )
            )
            await session.flush()
        membership_id = identifier("membership:" + code)
        if await session.get(CommunityMembership, membership_id) is None:
            session.add(
                CommunityMembership(
                    id=membership_id,
                    community_id=community_id,
                    user_id=user_id,
                    role="operator" if number == 1 else "member",
                )
            )
        home = await session.get(Home, home_id)
        if home is None:
            session.add(
                Home(
                    id=home_id,
                    owner_id=user_id,
                    name=code,
                    address=f"Demo metered point {number}",
                    city="Cali",
                    country="Colombia",
                    timezone="America/Bogota",
                    installed_capacity_w=solar * 1000,
                    has_battery=battery > 0,
                )
            )
            await session.flush()
        elif home.owner_id != user_id:
            raise ValueError(
                "Existing demo home has another owner; refusing to overwrite"
            )
        node_id = identifier("node:" + code)
        node = await session.get(CommunityNode, node_id)
        if node is None:
            session.add(
                CommunityNode(
                    id=node_id,
                    community_id=community_id,
                    home_id=home_id,
                    authorized=device_key is not None,
                )
            )
            await session.flush()
        wallet_id = identifier("wallet:" + code)
        if await session.get(Wallet, wallet_id) is None:
            session.add(
                Wallet(
                    id=wallet_id,
                    user_id=user_id,
                    address="0x" + digit * 40,
                    is_verified=False,
                )
            )
        for index, kind, prefix in (
            (1, "smart_meter", "SM"),
            (2, "solar_inverter", "INV"),
            (3, "weather_sensor", "WS"),
            (4, "battery_monitor", "BM"),
        ):
            if (index == 2 and not solar) or (index == 4 and not battery):
                continue
            device_code = f"{prefix}-MS-{number:03d}-{index:03d}"
            pk = UUID(f"{letter}0000000-0000-0000-0000-{index:012d}")
            device = await session.get(Device, pk)
            public_id = identifier("public-device:" + device_code)
            if device is None:
                device = Device(
                    id=pk,
                    device_id=public_id,
                    home_id=home_id,
                    device_code=device_code,
                    device_type=kind,
                    mqtt_client_id="demo-" + device_code,
                    status="ACTIVE" if device_key else "PENDING",
                )
                session.add(device)
                await session.flush()
            elif device.home_id != home_id or device.device_type != kind:
                raise ValueError(
                    "Existing demo device identity differs; refusing to overwrite"
                )
            binding = "METER_" + device_code.replace("-", "_") + "_CREDENTIAL"
            registry[device_code] = {
                "device_id": str(device.device_id),
                "home_id": str(home_id),
                "credential_env": binding,
            }
            if device_key:
                credential = hmac.new(
                    device_key.encode(), device_code.encode(), hashlib.sha256
                ).hexdigest()
                digest = hashlib.sha256(credential.encode()).hexdigest()
                authorization = await session.get(MeterAuthorization, pk)
                if authorization is None:
                    session.add(
                        MeterAuthorization(
                            device_id=pk, node_id=node_id, credential_hash=digest
                        )
                    )
                elif authorization.credential_hash != digest:
                    raise ValueError(
                        "Existing credential differs; explicit rotation required"
                    )
                bindings[binding] = credential
    await session.flush()
    return {
        "community_id": str(community_id),
        "registry": registry,
        "bindings": bindings,
    }


def write_private(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text() != content:
            raise ValueError(f"Existing seed output differs: {path}; preserved")
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)


async def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise ValueError("Set DATABASE_URL explicitly before running the seed")
    directory = Path(os.environ.get("SEED_OUTPUT_DIR", "/tmp/solar-market-demo"))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    async with AsyncSessionFactory() as session:
        async with session.begin():
            result = await seed_demo(
                session,
                os.environ.get("SEED_PASSWORD", ""),
                os.environ.get("SEED_DEVICE_KEY"),
            )
            write_private(
                directory / "registry.json",
                json.dumps(result["registry"], indent=2) + "\n",
            )
            if result["bindings"]:
                write_private(
                    directory / "simulator.env",
                    "\n".join(
                        f"{name}={value}"
                        for name, value in sorted(result["bindings"].items())
                    )
                    + "\n",
                )
    print(
        f"Seed complete: community {result['community_id']}; 5 homes; {len(result['registry'])} devices. Output: {directory}. Wallets remain unverified."
    )


if __name__ == "__main__":
    asyncio.run(main())
