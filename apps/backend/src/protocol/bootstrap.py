"""Idempotent SQLModel + real timelock commissioning, restricted to local Anvil."""

import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from eth_account import Account
from sqlalchemy import text
from sqlmodel import select
from web3 import Web3

from src.core.config import Config
from src.core.db import AsyncSessionFactory, dispose_engine
from src.modules.auth.models import User
from src.modules.auth.utils import generate_passwd_hash, verify_password
from src.modules.community.models import (
    CommunityMembership,
    CommunityNode,
    EnergyCommunity,
    MeterAuthorization,
    NativeDeployment,
)
from src.modules.device.models import Device
from src.modules.energy import models as energy_models  # noqa: F401 - registers SQLModel relations
from src.modules.home.models import Home
from src.modules.wallet.models import Wallet
from src.protocol.deployment import ZERO, Deployment, artifacts_at, save_json
from src.seed import CATALOGUE, write_private


def identifier(value):
    return uuid5(NAMESPACE_URL, "solar-governed-demo:v1:" + value)


async def bootstrap(factory, web3, artifacts, output, password, device_key):
    if Config.ENVIRONMENT != "development" or web3.eth.chain_id not in (31337, 1337):
        raise ValueError("Demo bootstrap is restricted to development Anvil")
    if (
        len(password) < 12
        or len(password.encode()) > 72
        or len(device_key) < 32
        or not Config.BACKEND_PRIVATE_KEY
    ):
        raise ValueError(
            "Set SEED_PASSWORD (12+), SEED_DEVICE_KEY (32+) and the dedicated backend oracle key"
        )
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Derive isolated local fixtures without embedding or logging a private key.
    # Existing linked Anvil accounts are never claimed or overwritten.
    local_accounts = [
        Account.from_key(
            hmac.new(
                device_key.encode(), f"local-wallet:{role}".encode(), hashlib.sha256
            ).digest()
        )
        for role in ("governor", "1", "2", "3", "4", "5")
    ]
    governor = local_accounts[0].address
    owners = [account.address for account in local_accounts[1:]]
    oracle = Account.from_key(Config.BACKEND_PRIVATE_KEY).address
    if oracle.lower() in {x.address.lower() for x in local_accounts}:
        raise ValueError(
            "Backend oracle must be separate from governance and participants"
        )
    fresh = not (output / "deployment.json").exists()
    for account in local_accounts:
        web3.provider.make_request("anvil_impersonateAccount", [account.address])
        if fresh:
            web3.provider.make_request(
                "anvil_setBalance", [account.address, hex(10**20)]
            )
        keyfile = output / "wallets" / f"{account.address}.json"
        if not keyfile.exists():
            save_json(keyfile, Account.encrypt(account.key, password))
    web3.provider.make_request("anvil_setBalance", [oracle, hex(10**20)])
    cid = identifier("community")
    deployment = Deployment(
        web3,
        artifacts,
        output / "deployment.json",
        cid,
        governor,
        governor,
        governor,
        oracle,
    )
    c = deployment.deploy()
    registry, sun, settlement, vault = [
        c[x]
        for x in (
            "CommunityRegistry",
            "SUNToken",
            "CommunitySettlement",
            "NativeSettlementVault",
        )
    ]
    policy = Web3.to_hex(
        Web3.keccak(text="solar-governed-demo:v1:900s:1SUN/kWh:0.001ETH/kWh:simulated")
    )
    boundary = Web3.to_hex(Web3.keccak(text="Cali local demonstration boundary"))
    current = registry.functions.communities(deployment.cid).call()
    if current[0] == ZERO:
        deployment.send(
            registry.functions.propose(
                deployment.cid,
                Web3.to_bytes(hexstr=boundary),
                Web3.to_bytes(hexstr=policy),
                900,
            ),
            owners[0],
        )
    state = registry.functions.communities(deployment.cid).call()[2]
    if state == 1:
        deployment.govern(registry.functions.transition(deployment.cid, 2, ZERO))
        state = 2
    if state == 2:
        deployment.govern(registry.functions.transition(deployment.cid, 3, ZERO))
        state = 3
    if state == 3:
        deployment.govern(registry.functions.configurePrice(deployment.cid, 10**15))
    if state not in (3, 4):
        raise ValueError("Demo lifecycle was changed; refusing to override governance")
    for fn in deployment.setup_calls():
        deployment.govern(fn)
    if state == 3:
        deployment.govern(registry.functions.transition(deployment.cid, 4, owners[0]))
    members, device_registry, bindings = [], {}, {}
    async with factory() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(707031502)"))
        community = await db.get(EnergyCommunity, cid)
        if community is None:
            community = EnergyCommunity(
                id=cid,
                name="Cali governed energy demonstration",
                boundary_description="Local simulated community; no commercial or regulatory authorization",
                topology="SIMULATED_GRID_CONNECTED",
                allow_simulated_telemetry=True,
            )
            db.add(community)
        if (
            community.registry_address
            and community.registry_address.lower() != registry.address.lower()
        ):
            raise ValueError(
                "Existing demo registry differs; refusing to overwrite accounting"
            )
        community.status = "ACTIVE"
        community.registry_address = registry.address
        community.policy_hash = policy
        community.boundary_hash = boundary
        # The proposer FK is assigned after users are inserted.
        if community.proposer_id is None:
            community.proposer_id = None
        await db.flush()
        for number, ((solar, battery), owner) in enumerate(
            zip(CATALOGUE, owners, strict=True), 1
        ):
            uid, hid, nid = [
                identifier(f"{kind}:{number}") for kind in ("user", "home", "node")
            ]
            user = await db.get(User, uid)
            if user is None:
                user = User(
                    uid=uid,
                    username=f"govdemo{number}",
                    email=f"govdemo{number}@solar.local",
                    first_name="Solar",
                    last_name=f"Member {number}",
                    password_hash=generate_passwd_hash(password),
                )
                db.add(user)
                await db.flush()
            elif user.email != f"govdemo{number}@solar.local" or not verify_password(
                password, user.password_hash
            ):
                raise ValueError("Existing demo user differs")
            wallet = await db.get(Wallet, identifier(f"wallet:{number}"))
            if wallet is None:
                if (
                    await db.exec(select(Wallet).where(Wallet.address == owner))
                ).first():
                    raise ValueError(
                        "A local fixture wallet is already linked to a different user"
                    )
                db.add(
                    Wallet(
                        id=identifier(f"wallet:{number}"),
                        user_id=uid,
                        address=owner,
                        is_verified=True,
                    )
                )
            elif wallet.address.lower() != owner.lower() or not wallet.is_verified:
                raise ValueError(
                    "Existing demo wallet differs; no ownership is overwritten"
                )
            membership = await db.get(
                CommunityMembership, identifier(f"membership:{number}")
            )
            if membership is None:
                db.add(
                    CommunityMembership(
                        id=identifier(f"membership:{number}"),
                        community_id=cid,
                        user_id=uid,
                        status="ACTIVE",
                        role="operator" if number == 1 else "member",
                    )
                )
            elif membership.status != "ACTIVE":
                raise ValueError(
                    "Demo membership was changed; refusing to reactivate it silently"
                )
            home = await db.get(Home, hid)
            if home is None:
                db.add(
                    Home(
                        id=hid,
                        owner_id=uid,
                        name=f"HOME-MS-{number:03d}",
                        address=f"Demonstration metered point {number}",
                        city="Cali",
                        installed_capacity_w=solar * 1000,
                        has_battery=battery > 0,
                    )
                )
                await db.flush()
            elif home.owner_id != uid:
                raise ValueError("Existing demo home ownership differs")
            node = await db.get(CommunityNode, nid)
            if node is None:
                db.add(
                    CommunityNode(
                        id=nid, community_id=cid, home_id=hid, authorized=True
                    )
                )
                await db.flush()
            member = registry.functions.memberships(deployment.cid, owner).call()
            if member == 0:
                deployment.send(
                    registry.functions.applyMembership(deployment.cid), owner
                )
                member = 1
            for status in (2, 3):
                if member == status - 1:
                    deployment.govern(
                        registry.functions.setMembership(deployment.cid, owner, status)
                    )
                    member = status
            if member != 3:
                raise ValueError(
                    "On-chain membership no longer active; governance review required"
                )
            node_key = nid.bytes.rjust(32, b"\0")
            if registry.functions.nodes(deployment.cid, node_key).call() == ZERO:
                deployment.govern(
                    registry.functions.registerNode(deployment.cid, node_key, owner)
                )
            for index, kind, prefix in (
                (1, "smart_meter", "SM"),
                (2, "solar_inverter", "INV"),
                (3, "weather_sensor", "WS"),
                (4, "battery_monitor", "BM"),
            ):
                if (index == 2 and not solar) or (index == 4 and not battery):
                    continue
                code = f"{prefix}-MS-{number:03d}-{index:03d}"
                did, public = identifier("device:" + code), identifier("wire:" + code)
                device = await db.get(Device, did)
                if device is None:
                    db.add(
                        Device(
                            id=did,
                            home_id=hid,
                            device_id=public,
                            device_code="GOV-" + code,
                            device_type=kind,
                            telemetry_source="SIMULATED",
                            mqtt_client_id="gov-demo-" + code,
                            status="ACTIVE",
                        )
                    )
                    await db.flush()
                elif device.home_id != hid or device.status != "ACTIVE":
                    raise ValueError(
                        "Existing meter changed; no authorization is overwritten"
                    )
                credential = hmac.new(
                    device_key.encode(), code.encode(), hashlib.sha256
                ).hexdigest()
                digest = hashlib.sha256(credential.encode()).hexdigest()
                authorization = await db.get(MeterAuthorization, did)
                if authorization is None:
                    db.add(
                        MeterAuthorization(
                            device_id=did, node_id=nid, credential_hash=digest
                        )
                    )
                elif (
                    authorization.credential_hash != digest or not authorization.active
                ):
                    raise ValueError(
                        "Explicit meter credential rotation/review required"
                    )
                deployment.govern(
                    registry.functions.authorizeMeter(
                        deployment.cid, node_key, public.bytes.rjust(32, b"\0"), True
                    )
                )
                binding = "METER_" + code.replace("-", "_") + "_CREDENTIAL"
                bindings[binding] = credential
                device_registry[code] = {
                    "community_id": str(cid),
                    "node_id": str(nid),
                    "home_id": str(hid),
                    "device_id": str(public),
                    "credential_env": binding,
                }
            members.append(
                {
                    "user_id": str(uid),
                    "email": user.email,
                    "address": owner,
                    "home_id": str(hid),
                    "node_id": str(nid),
                }
            )
        admin_id = identifier("governor")
        if await db.get(User, admin_id) is None:
            db.add(
                User(
                    uid=admin_id,
                    username="govadmin",
                    email="govadmin@solar.local",
                    first_name="Governance",
                    last_name="Local fixture",
                    password_hash=generate_passwd_hash(password),
                )
            )
            await db.flush()
            db.add(
                Wallet(
                    id=identifier("wallet:governor"),
                    user_id=admin_id,
                    address=governor,
                    is_verified=True,
                )
            )
            db.add(
                CommunityMembership(
                    id=identifier("membership:governor"),
                    community_id=cid,
                    user_id=admin_id,
                    status="ACTIVE",
                    role="member",
                )
            )
        admin_state = registry.functions.memberships(deployment.cid, governor).call()
        if admin_state == 0:
            deployment.send(
                registry.functions.applyMembership(deployment.cid), governor
            )
            admin_state = 1
        for status in (2, 3):
            if admin_state == status - 1:
                deployment.govern(
                    registry.functions.setMembership(deployment.cid, governor, status)
                )
                admin_state = status
        if admin_state != 3:
            raise ValueError("Governor fixture membership was changed; review required")
        community.proposer_id = identifier("user:1")
        native = await db.get(NativeDeployment, cid)
        if native is None:
            db.add(
                NativeDeployment(
                    community_id=cid,
                    chain_id=web3.eth.chain_id,
                    sun_address=sun.address,
                    settlement_address=settlement.address,
                    vault_address=vault.address,
                )
            )
        elif native.sun_address.lower() != sun.address.lower():
            raise ValueError("Existing native deployment differs")
        await db.commit()
    # Reserve homes 1/2 for the finite financial fixture. Continuous simulation
    # uses distinct meter identities/counters on homes 3..5, avoiding resets.
    catalogue = [
        {
            "home_id": f"HOME-MS-{number:03d}",
            "city": "Cali",
            "solar_kw": solar,
            "battery_kwh": battery,
            "profile": "consumer"
            if not solar and not battery
            else "battery_prosumer"
            if battery
            else "solar_producer",
        }
        for number, (solar, battery) in enumerate(CATALOGUE, 1)
        if number >= 3
    ]
    write_private(
        output / "home-catalogue.json", json.dumps(catalogue, indent=2) + "\n"
    )
    write_private(
        output / "registry.json", json.dumps(device_registry, indent=2) + "\n"
    )
    write_private(
        output / "simulator.env",
        "".join(f"{key}={value}\n" for key, value in sorted(bindings.items())),
    )
    public = {
        "community_id": str(cid),
        "chain_id": web3.eth.chain_id,
        "registry": registry.address,
        "timelock": c["TimelockController"].address,
        "sun": sun.address,
        "settlement": settlement.address,
        "vault": vault.address,
        "members": members,
        "governance": {"address": governor, "email": "govadmin@solar.local"},
        "price_wei_per_kwh": str(10**15),
        "notice": "Local test wallets and simulated meters. No energy credits or financial balances were fabricated.",
    }
    save_json(output / "demo.json", public)
    return public


async def main():
    directory = Path(os.environ.get("DEMO_OUTPUT_DIR", "/run/demo"))
    await bootstrap(
        AsyncSessionFactory,
        Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL)),
        artifacts_at(os.environ.get("CONTRACT_ARTIFACT_DIR", "/artifacts")),
        directory,
        os.environ.get("SEED_PASSWORD", ""),
        os.environ.get("SEED_DEVICE_KEY", ""),
    )
    await dispose_engine()
    print(
        "Governed local community commissioned; public metadata: "
        + str(directory / "demo.json")
    )


if __name__ == "__main__":
    asyncio.run(main())
