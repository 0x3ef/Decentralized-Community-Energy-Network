"""Real Anvil timelock activation and unsigned native ETH wallet operations."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from eth_account import Account
from httpx import ASGITransport, AsyncClient
from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.main import app
from src.modules.auth.models import User
from src.modules.auth.utils import create_access_token
from src.modules.wallet.models import Wallet
from web3 import Web3


@pytest.mark.asyncio
async def test_governance_activation_native_deposit_and_suspended_withdrawal(
    monkeypatch,
):
    root = Path(__file__).resolve().parents[3]
    w3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL))
    assert w3.eth.chain_id == 31337
    governor = w3.eth.accounts[0]
    operator = Account.create().address
    w3.provider.make_request("anvil_impersonateAccount", [operator])
    w3.provider.make_request("anvil_setBalance", [operator, hex(10**19)])

    def send(fn, sender=governor):
        receipt = w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
        assert receipt.status == 1
        return receipt

    def deploy(name, *args):
        artifact = json.loads(
            (root / "contracts/out" / f"{name}.sol" / f"{name}.json").read_text()
        )
        receipt = send(
            w3.eth.contract(
                abi=artifact["abi"], bytecode=artifact["bytecode"]["object"]
            ).constructor(*args)
        )
        return w3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"])

    timelock = deploy("TimelockController", 0, [governor], [governor], "0x" + "0" * 40)
    registry = deploy("CommunityRegistry", timelock.address)
    monkeypatch.setattr(Config, "COMMUNITY_REGISTRY_ADDRESS", registry.address)
    monkeypatch.setattr(Config, "BLOCKCHAIN_CONFIRMATION_BLOCKS", 1)
    sequence = 0

    def govern(fn):
        nonlocal sequence
        sequence += 1
        salt = Web3.keccak(text=f"governance-{sequence}")
        send(
            timelock.functions.schedule(
                fn.address, 0, fn._encode_transaction_data(), bytes(32), salt, 0
            )
        )
        return send(
            timelock.functions.execute(
                fn.address, 0, fn._encode_transaction_data(), bytes(32), salt
            )
        )

    async with AsyncSessionFactory() as db:
        suffix = uuid4().hex
        user = User(
            username=suffix,
            email=suffix + "@example.com",
            first_name="Governed",
            last_name="Operator",
            password_hash="not-a-login",
        )
        db.add(user)
        await db.flush()
        db.add(Wallet(user_id=user.uid, address=operator, is_verified=True))
        await db.commit()
        token = create_access_token(
            {"email": user.email, "user_uid": str(user.uid), "role": "user"}
        )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        created = await client.post(
            "/api/v1/communities",
            json={
                "name": "Governed physical boundary",
                "boundary_description": "Simulated Cali grid boundary",
                "interval_seconds": 900,
            },
        )
        assert created.status_code == 201, created.text
        community = created.json()
        cid = community["id"]
        key = __import__("uuid").UUID(cid).bytes.rjust(32, b"\0")
        assert community["status"] == "DRAFT"
        proposal = await client.post(f"/api/v1/communities/{cid}/propose")
        assert proposal.status_code == 200, proposal.text
        proposed = proposal.json()["community"]
        send(
            registry.functions.propose(
                key,
                Web3.to_bytes(hexstr=proposed["boundary_hash"]),
                Web3.to_bytes(hexstr=proposed["policy_hash"]),
                900,
            ),
            operator,
        )
        govern(registry.functions.transition(key, 2, "0x" + "0" * 40))
        govern(registry.functions.transition(key, 3, "0x" + "0" * 40))
        govern(registry.functions.configurePrice(key, 10**15))
        activated = govern(registry.functions.transition(key, 4, operator))
        synced = await client.post(
            f"/api/v1/communities/{cid}/governance/sync",
            json={"transaction_hash": Web3.to_hex(activated.transactionHash)},
        )
        assert synced.status_code == 200, synced.text
        assert synced.json()["status"] == "ACTIVE"
        send(registry.functions.applyMembership(key), operator)
        govern(registry.functions.setMembership(key, operator, 2))
        govern(registry.functions.setMembership(key, operator, 3))
        sun = deploy("SUNToken", timelock.address, timelock.address)
        settlement = deploy(
            "CommunitySettlement",
            registry.address,
            sun.address,
            timelock.address,
            60,
            key,
        )
        vault = deploy(
            "NativeSettlementVault", registry.address, settlement.address, sun.address
        )
        govern(settlement.functions.bindVault(vault.address))
        unapproved = await client.post(
            f"/api/v1/communities/{cid}/native-deployment",
            json={
                "chain_id": 31337,
                "sun_address": sun.address,
                "settlement_address": settlement.address,
                "vault_address": vault.address,
            },
        )
        assert unapproved.status_code == 403, unapproved.text
        govern(
            registry.functions.bindProtocol(
                key, settlement.address, vault.address, sun.address
            )
        )
        registered = await client.post(
            f"/api/v1/communities/{cid}/native-deployment",
            json={
                "chain_id": 31337,
                "sun_address": sun.address,
                "settlement_address": settlement.address,
                "vault_address": vault.address,
            },
        )
        assert registered.status_code == 201, registered.text
        prepared = await client.post(
            f"/api/v1/communities/{cid}/native/prepare",
            json={"action": "deposit", "amount_base_units": str(10**16)},
        )
        assert prepared.status_code == 200, prepared.text
        tx = prepared.json()
        assert tx["status"] == "AWAITING_USER_SIGNATURE"
        receipt = w3.eth.wait_for_transaction_receipt(
            w3.eth.send_transaction(
                {
                    "from": operator,
                    "to": tx["to"],
                    "data": tx["data"],
                    "value": int(tx["value"]),
                }
            )
        )
        assert receipt.status == 1
        balances = await client.get(f"/api/v1/communities/{cid}/native-wallet")
        assert balances.status_code == 200, balances.text
        assert balances.json()["available_wei"] == str(10**16)
        govern(registry.functions.transition(key, 5, "0x" + "0" * 40))
        blocked = await client.post(
            f"/api/v1/communities/{cid}/native/prepare",
            json={"action": "deposit", "amount_base_units": "1"},
        )
        assert blocked.status_code == 403, blocked.text
        exit_tx = await client.post(
            f"/api/v1/communities/{cid}/native/prepare",
            json={"action": "withdraw", "amount_base_units": str(10**16)},
        )
        assert exit_tx.status_code == 200, exit_tx.text
        tx = exit_tx.json()
        w3.eth.wait_for_transaction_receipt(
            w3.eth.send_transaction(
                {"from": operator, "to": tx["to"], "data": tx["data"]}
            )
        )
        assert vault.functions.totalLiabilities().call() == 0
