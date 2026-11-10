"""Native ETH protocol reads and unsigned user-wallet transaction preparation."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from src.core.db import get_session
from src.modules.auth.dependencies import get_current_user
from src.modules.community.chain import CommunityChain
from src.modules.community.models import EnergyCommunity, NativeDeployment
from src.modules.community.service import CommunityService
from web3 import Web3
from web3.exceptions import ContractLogicError

router = APIRouter()
service = CommunityService()


class Deployment(BaseModel):
    chain_id: Literal[31337, 1337, 11155111]
    sun_address: str
    settlement_address: str
    vault_address: str


class Transaction(BaseModel):
    action: Literal[
        "deposit",
        "withdraw",
        "withdraw_earnings",
        "escrow_sun",
        "withdraw_sun",
        "approve_sun",
        "approve_retirement",
        "execute",
        "cancel",
        "retire",
    ]
    amount_base_units: str = Field(default="0", pattern=r"^\d+$", max_length=78)
    batch_id: str = Field(default="0x" + "0" * 64, pattern=r"^0x[0-9a-fA-F]{64}$")
    claim_id: str = Field(default="0x" + "0" * 64, pattern=r"^0x[0-9a-fA-F]{64}$")
    node_id: str = Field(default="0x" + "0" * 64, pattern=r"^0x[0-9a-fA-F]{64}$")
    meter_id: str = Field(default="0x" + "0" * 64, pattern=r"^0x[0-9a-fA-F]{64}$")
    proof: list[str] = Field(default_factory=list, max_length=64)


@router.post("/{community_id}/native-deployment", status_code=201)
async def register(
    community_id: UUID,
    payload: Deployment,
    user: Annotated[Any, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_session)],
):
    await service.membership(session, community_id, user.uid, operator=True)
    chain = CommunityChain()
    community = await session.get(EnergyCommunity, community_id)
    if not community.registry_address or chain.web3.eth.chain_id != payload.chain_id:
        raise ValueError("Governed registry and matching chain required")
    if await session.get(NativeDeployment, community_id):
        raise ValueError(
            "Native deployment already registered; explicit migration required"
        )
    registry = chain.contract("CommunityRegistry", community.registry_address)
    approved = registry.functions.protocols(community_id.bytes.rjust(32, b"\0")).call()
    requested = (payload.settlement_address, payload.vault_address, payload.sun_address)
    if [address.lower() for address in approved] != [
        address.lower() for address in requested
    ]:
        raise PermissionError(
            "Governance must approve the exact settlement, vault and SUN deployment"
        )
    vault = chain.contract("NativeSettlementVault", payload.vault_address)
    settlement = chain.contract("CommunitySettlement", payload.settlement_address)
    key = community_id.bytes.rjust(32, b"\0")
    if (
        vault.functions.communityId().call() != key
        or settlement.functions.communityId().call() != key
    ):
        raise ValueError("Community mismatch")
    if (
        vault.functions.registry().call().lower() != community.registry_address.lower()
        or settlement.functions.registry().call().lower()
        != community.registry_address.lower()
    ):
        raise ValueError("Registry mismatch")
    if (
        vault.functions.sun().call().lower() != payload.sun_address.lower()
        or settlement.functions.sun().call().lower() != payload.sun_address.lower()
    ):
        raise ValueError("SUN mismatch")
    if (
        vault.functions.settlement().call().lower()
        != payload.settlement_address.lower()
        or settlement.functions.vault().call().lower() != payload.vault_address.lower()
    ):
        raise ValueError("Settlement/vault binding incomplete")
    row = NativeDeployment(community_id=community_id, **payload.model_dump())
    session.add(row)
    await session.commit()
    return row


async def context(session, community_id, user, allow_exit=False):
    if not allow_exit:
        await service.membership(session, community_id, user.uid)
    deployment = await session.get(NativeDeployment, community_id)
    if not deployment:
        raise ValueError("Native settlement deployment is not registered")
    chain = CommunityChain()
    if chain.web3.eth.chain_id != deployment.chain_id:
        raise ValueError("Wrong RPC chain")
    wallet = await service.wallet(session, user.uid)
    return (
        chain,
        deployment,
        wallet,
        chain.contract("NativeSettlementVault", deployment.vault_address),
        chain.contract("CommunitySettlement", deployment.settlement_address),
    )


@router.get("/{community_id}/native-wallet")
async def balances(
    community_id: UUID,
    user: Annotated[Any, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_session)],
):
    chain, deployment, wallet, vault, _settlement = await context(
        session, community_id, user, allow_exit=True
    )
    from src.core.config import Config

    height = max(
        0,
        chain.web3.eth.block_number - max(1, Config.BLOCKCHAIN_CONFIRMATION_BLOCKS) + 1,
    )
    community = await session.get(EnergyCommunity, community_id)
    registry = chain.contract("CommunityRegistry", community.registry_address)
    sun = chain.contract("SUNToken", deployment.sun_address)
    return {
        "address": wallet,
        "block_number": height,
        "chain_id": deployment.chain_id,
        "contracts": deployment,
        "wallet_wei": str(chain.web3.eth.get_balance(wallet, height)),
        "available_wei": str(
            vault.functions.available(wallet).call(block_identifier=height)
        ),
        "reserved_wei": str(
            vault.functions.reserved(wallet).call(block_identifier=height)
        ),
        "earnings_wei": str(
            vault.functions.earnings(wallet).call(block_identifier=height)
        ),
        "sun_units": str(sun.functions.balanceOf(wallet).call(block_identifier=height)),
        "escrow_sun_units": str(
            vault.functions.sunAvailable(wallet).call(block_identifier=height)
        ),
        "reserved_sun_units": str(
            vault.functions.sunReserved(wallet).call(block_identifier=height)
        ),
        "price_wei_per_kwh": str(
            registry.functions.priceWeiPerKwh(community_id.bytes.rjust(32, b"\0")).call(
                block_identifier=height
            )
        ),
        "asset": "Sepolia ETH" if deployment.chain_id == 11155111 else "Anvil ETH",
        "notice": "Test ETH; no fiat conversion or guaranteed real monetary value.",
    }


@router.post("/{community_id}/native/prepare")
async def prepare(
    community_id: UUID,
    payload: Transaction,
    user: Annotated[Any, Depends(get_current_user)],
    session: Annotated[Any, Depends(get_session)],
):
    chain, deployment, wallet, vault, settlement = await context(
        session,
        community_id,
        user,
        allow_exit=payload.action
        in ("withdraw", "withdraw_earnings", "withdraw_sun", "cancel"),
    )
    amount = int(payload.amount_base_units)
    if amount >= 2**256:
        raise ValueError("Amount exceeds uint256")
    if payload.action not in ("execute", "retire", "cancel") and amount == 0:
        raise ValueError("Positive amount required")
    value = 0
    if payload.action == "deposit":
        community = await session.get(EnergyCommunity, community_id)
        registry = chain.contract("CommunityRegistry", community.registry_address)
        price = registry.functions.priceWeiPerKwh(
            community_id.bytes.rjust(32, b"\0")
        ).call()
        function = vault.functions.deposit(price)
        value = amount
    elif payload.action == "withdraw":
        function = vault.functions.withdraw(amount, wallet)
    elif payload.action == "withdraw_earnings":
        function = vault.functions.withdrawEarnings(amount, wallet)
    elif payload.action == "escrow_sun":
        function = vault.functions.depositSUN(amount)
    elif payload.action == "withdraw_sun":
        function = vault.functions.withdrawSUN(amount)
    elif payload.action in ("approve_sun", "approve_retirement"):
        function = chain.contract("SUNToken", deployment.sun_address).functions.approve(
            settlement.address
            if payload.action == "approve_retirement"
            else vault.address,
            amount,
        )
    elif payload.action == "cancel":
        function = vault.functions.cancel(Web3.to_bytes(hexstr=payload.claim_id))
    elif payload.action == "execute":
        function = vault.functions.execute(Web3.to_bytes(hexstr=payload.claim_id))
    else:
        proof = [Web3.to_bytes(hexstr=node) for node in payload.proof]
        if any(len(node) != 32 for node in proof):
            raise ValueError("Proof nodes must be bytes32")
        function = settlement.functions.retire(
            Web3.to_bytes(hexstr=payload.batch_id),
            Web3.to_bytes(hexstr=payload.claim_id),
            Web3.to_bytes(hexstr=payload.node_id),
            Web3.to_bytes(hexstr=payload.meter_id),
            amount,
            proof,
        )
    # Simulate only: no custody, transaction submission, or false success record.
    try:
        function.call({"from": wallet, "value": value})
    except ContractLogicError as exc:
        raise ValueError("Contract rejected the requested operation") from exc
    return {
        "chain_id": deployment.chain_id,
        "from": wallet,
        "to": function.address,
        "data": function._encode_transaction_data(),
        "value": str(value),
        "status": "AWAITING_USER_SIGNATURE",
    }
