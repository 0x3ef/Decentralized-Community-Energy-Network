"""Authenticated community API; transaction signatures remain in user wallets."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID
import secrets
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, SecretStr
from sqlmodel import select
from src.core.db import get_session
from src.modules.auth.dependencies import get_current_user
from src.modules.community.models import (
    CommunityMembership,
    EnergyCommunity,
    CommunityNode,
    ChainDeployment,
    CompensationRequest,
    CommunityEnergyLedger,
)
from src.modules.community.service import CommunityService
from src.modules.community.chain import CommunityChain
from src.modules.wallet.models import Wallet, WalletNonce
from eth_account.messages import encode_defunct
from eth_account import Account
from web3 import Web3

router = APIRouter()
service = CommunityService()


class CommunityCreate(BaseModel):
    boundary_description: str = Field(default="", max_length=1000)
    topology: str = Field(
        default="SIMULATED_GRID_CONNECTED",
        pattern="^(SIMULATED_GRID_CONNECTED|PARTIAL_MICROGRID|INDEPENDENT_MICROGRID)$",
    )
    interval_seconds: int = Field(default=900, gt=0, le=86400)
    name: str = Field(min_length=1, max_length=150)
    sun_per_kwh: Decimal = Field(
        default=Decimal(1), gt=0, max_digits=24, decimal_places=8
    )
    loss_factor: Decimal = Field(
        default=Decimal(0), ge=0, lt=1, max_digits=12, decimal_places=8
    )


class MemberCreate(BaseModel):
    user_id: UUID
    role: str = Field(default="member", pattern="^(member|operator)$")


class NodeCreate(BaseModel):
    home_id: UUID


class MeterCreate(BaseModel):
    device_id: UUID
    credential: SecretStr


class CompensationCreate(BaseModel):
    injection_interval_id: UUID
    withdrawal_interval_id: UUID
    energy_wh: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=128)


class TransactionInput(BaseModel):
    transaction_hash: str = Field(pattern="^0x[0-9a-fA-F]{64}$")


class WalletChallenge(BaseModel):
    address: str


class WalletProof(WalletChallenge):
    nonce: str
    signature: str


@router.post("", status_code=201)
async def create(
    payload: CommunityCreate,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    community = await service.create(session, actor, payload.name)
    if payload.sun_per_kwh != 1:
        raise ValueError("Governed SUN v2 uses exactly 1 SUN per eligible kWh")
    community.boundary_description = payload.boundary_description
    community.topology = payload.topology
    community.interval_seconds = payload.interval_seconds
    community.sun_per_kwh = payload.sun_per_kwh
    community.loss_factor = payload.loss_factor
    await session.commit()
    return community


@router.post("/{community_id}/members", status_code=201)
async def member(
    community_id: UUID,
    payload: MemberCreate,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    await service.membership(session, community_id, actor.uid, operator=True)
    row = CommunityMembership(
        community_id=community_id, user_id=payload.user_id, role=payload.role
    )
    session.add(row)
    await session.commit()
    return row


@router.post("/{community_id}/nodes", status_code=201)
async def node(
    community_id: UUID,
    payload: NodeCreate,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    result = await service.register_node(session, actor, community_id, payload.home_id)
    await session.commit()
    return result


@router.post("/nodes/{node_id}/meters", status_code=201)
async def meter(
    node_id: UUID,
    payload: MeterCreate,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    result = await service.authorize_meter(
        session,
        actor,
        node_id,
        payload.device_id,
        payload.credential.get_secret_value(),
    )
    await session.commit()
    return {
        "device_id": result.device_id,
        "node_id": result.node_id,
        "active": result.active,
    }


@router.post("/wallet/challenge")
async def wallet_challenge(
    payload: WalletChallenge,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    address = Web3.to_checksum_address(payload.address)
    nonce = WalletNonce(
        user_id=actor.uid,
        address=address,
        nonce=secrets.token_hex(32),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    session.add(nonce)
    await session.commit()
    return {
        "nonce": nonce.nonce,
        "message": f"Solar Energy Market wallet link\nUser: {actor.uid}\nAddress: {address}\nNonce: {nonce.nonce}",
    }


@router.post("/wallet/verify")
async def wallet_verify(
    payload: WalletProof, actor=Depends(get_current_user), session=Depends(get_session)
):
    nonce = (
        await session.exec(
            select(WalletNonce)
            .where(WalletNonce.nonce == payload.nonce)
            .with_for_update()
        )
    ).first()
    address = Web3.to_checksum_address(payload.address)
    if (
        not nonce
        or nonce.user_id != actor.uid
        or nonce.address != address
        or nonce.used_at
        or nonce.expires_at <= datetime.now(timezone.utc)
    ):
        raise ValueError("Invalid or expired wallet challenge")
    message = f"Solar Energy Market wallet link\nUser: {actor.uid}\nAddress: {address}\nNonce: {nonce.nonce}"
    if (
        Account.recover_message(
            encode_defunct(text=message), signature=payload.signature
        ).lower()
        != address.lower()
    ):
        raise PermissionError("Wallet signature invalid")
    existing = (
        await session.exec(select(Wallet).where(Wallet.address == address))
    ).first()
    if existing and existing.user_id != actor.uid:
        raise PermissionError("Wallet already linked")
    row = existing or Wallet(user_id=actor.uid, address=address)
    row.is_verified = True
    nonce.used_at = datetime.now(timezone.utc)
    session.add(row)
    await session.commit()
    return row


@router.post("/{community_id}/compensations", status_code=201)
async def compensate(
    community_id: UUID,
    payload: CompensationCreate,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    result = await service.reserve_compensation(
        session,
        actor,
        community_id,
        payload.injection_interval_id,
        payload.withdrawal_interval_id,
        payload.energy_wh,
        payload.idempotency_key,
    )
    deployment = await CommunityChain().deployment(session, community_id)
    token = CommunityChain().contract("SUNToken", deployment.sun_address)
    if token.functions.balanceOf(result.wallet).call() < int(result.token_units):
        raise ValueError("Insufficient SUN balance")
    await session.commit()
    return result


@router.post("/compensations/{request_id}/confirm")
async def confirm(
    request_id: UUID,
    payload: TransactionInput,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    result = await CommunityChain().confirm_retirement(
        session, actor, request_id, payload.transaction_hash
    )
    await session.commit()
    return result


@router.get("/{community_id}/compensations")
async def retirements(
    community_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    await service.membership(session, community_id, actor.uid)
    return (
        await session.exec(
            select(CompensationRequest)
            .where(
                CompensationRequest.community_id == community_id,
                CompensationRequest.user_id == actor.uid,
            )
            .order_by(CompensationRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()


@router.post("/{community_id}/trades/reconcile")
async def reconcile(
    community_id: UUID,
    payload: TransactionInput,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    result = await CommunityChain().reconcile_trade(
        session, actor, community_id, payload.transaction_hash
    )
    await session.commit()
    return result


@router.get("/{community_id}/statement")
async def statement(
    community_id: UUID, actor=Depends(get_current_user), session=Depends(get_session)
):
    return await service.statement(session, actor, community_id)


@router.get("/{community_id}/ledger")
async def ledger(
    community_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    await service.membership(session, community_id, actor.uid)
    return (
        await session.exec(
            select(CommunityEnergyLedger)
            .where(CommunityEnergyLedger.community_id == community_id)
            .order_by(CommunityEnergyLedger.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()


@router.get("/{community_id}/wallet")
async def balances(
    community_id: UUID, actor=Depends(get_current_user), session=Depends(get_session)
):
    await service.membership(session, community_id, actor.uid)
    address = await service.wallet(session, actor.uid)
    chain = CommunityChain()
    deployment = await chain.deployment(session, community_id)
    sun = chain.contract("SUNToken", deployment.sun_address)
    payment = chain.contract("MockUSD", deployment.payment_address)
    return {
        "address": address,
        "sun_base_units": str(sun.functions.balanceOf(address).call()),
        "sun_decimals": sun.functions.decimals().call(),
        "usdx_base_units": str(payment.functions.balanceOf(address).call()),
        "usdx_decimals": payment.functions.decimals().call(),
        "sun_marketplace_allowance": str(
            sun.functions.allowance(address, deployment.marketplace_address).call()
        ),
        "usdx_marketplace_allowance": str(
            payment.functions.allowance(address, deployment.marketplace_address).call()
        ),
        "sun_compensation_allowance": str(
            sun.functions.allowance(address, deployment.compensation_address).call()
        ),
        "contracts": deployment,
        "payment_notice": (
            "Unbacked simulated US dollars"
            if payment.functions.name().call().startswith("Simulated US Dollar")
            else "Legacy simulated peso units; not USDx v2"
        ),
    }


@router.get("/{community_id}/orders/{order_id}")
async def order(
    community_id: UUID,
    order_id: int,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    await service.membership(session, community_id, actor.uid)
    chain = CommunityChain()
    deployment = await chain.deployment(session, community_id)
    return {
        "order": chain.contract("EnergyMarketplace", deployment.marketplace_address)
        .functions.getOrder(order_id)
        .call()
    }


class DeploymentCreate(BaseModel):
    chain_id: int
    sun_address: str
    payment_address: str
    marketplace_address: str
    compensation_address: str


@router.post("/{community_id}/deployment", status_code=201)
async def register_deployment(
    community_id: UUID,
    payload: DeploymentCreate,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    await service.membership(session, community_id, actor.uid, operator=True)
    community = await session.get(EnergyCommunity, community_id)
    if community.registry_address:
        raise ValueError("Governed communities require native ETH deployment")
    chain = CommunityChain()
    if payload.chain_id != chain.web3.eth.chain_id or payload.chain_id not in (
        31337,
        1337,
    ):
        raise ValueError(
            "MockUSD deployments are restricted to local development chains"
        )
    if await session.get(ChainDeployment, community_id):
        raise ValueError(
            "Deployment is already registered; migration requires accounting review"
        )
    market = chain.contract("EnergyMarketplace", payload.marketplace_address)
    retirement = chain.contract("EnergyCompensation", payload.compensation_address)
    reference = community_id.bytes.rjust(32, b"\0")
    for contract in (market, retirement):
        if (
            contract.functions.communityId().call() != reference
            or contract.functions.sunToken().call().lower()
            != payload.sun_address.lower()
        ):
            raise ValueError(
                "Contract deployment does not match community or SUN token"
            )
    if (
        market.functions.paymentToken().call().lower()
        != payload.payment_address.lower()
    ):
        raise ValueError("Payment token mismatch")
    if (
        chain.contract("MockUSD", payload.payment_address).functions.decimals().call()
        != 6
        or chain.contract("SUNToken", payload.sun_address).functions.decimals().call()
        != 18
    ):
        raise ValueError("Unsupported token decimals")
    row = ChainDeployment(community_id=community_id, **payload.model_dump())
    session.add(row)
    await session.commit()
    return row


@router.post("/{community_id}/members/{user_id}/sync")
async def sync_member(
    community_id: UUID,
    user_id: UUID,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    await service.membership(session, community_id, actor.uid, operator=True)
    await service.membership(session, community_id, user_id)
    from src.modules.energy.models import OutboxEvent

    row = OutboxEvent(
        event_type="community.member.authorize",
        aggregate_type="MEMBERSHIP",
        aggregate_id=user_id,
        payload={"community_id": str(community_id), "user_id": str(user_id)},
    )
    session.add(row)
    await session.commit()
    return {"operation_id": row.id, "status": row.status}


@router.get("/{community_id}/transactions/{transaction_hash}")
async def transaction_status(
    community_id: UUID,
    transaction_hash: str,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    await service.membership(session, community_id, actor.uid)
    chain = CommunityChain()
    await chain.deployment(session, community_id)
    receipt = chain.canonical_receipt(transaction_hash)
    return {
        "transaction_hash": transaction_hash,
        "status": "CONFIRMED",
        "block_hash": Web3.to_hex(receipt.blockHash),
        "block_number": receipt.blockNumber,
    }


@router.get("/meters/{device_id}/telemetry")
async def telemetry_history(
    device_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    from src.modules.device.service import DeviceService
    from src.modules.device.models import TelemetryMessage

    await DeviceService().get_device_by_id(actor, device_id, session)
    return (
        await session.exec(
            select(TelemetryMessage)
            .where(TelemetryMessage.device_id == device_id)
            .order_by(TelemetryMessage.measured_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()


class MembershipUpdate(BaseModel):
    status: str = Field(pattern="^(ACTIVE|SUSPENDED)$")


@router.patch("/{community_id}/members/{user_id}")
async def update_membership(
    community_id: UUID,
    user_id: UUID,
    payload: MembershipUpdate,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    await service.membership(session, community_id, actor.uid, operator=True)
    row = (
        await session.exec(
            select(CommunityMembership)
            .where(
                CommunityMembership.community_id == community_id,
                CommunityMembership.user_id == user_id,
            )
            .with_for_update()
        )
    ).first()
    if not row:
        raise LookupError("Membership not found")
    if row.user_id == actor.uid and row.role == "operator":
        raise ValueError("Cannot suspend your own operator membership")
    row.status = payload.status
    from src.modules.energy.models import OutboxEvent

    session.add(
        OutboxEvent(
            event_type="community.member.authorize",
            aggregate_type="MEMBERSHIP",
            aggregate_id=user_id,
            payload={"community_id": str(community_id), "user_id": str(user_id)},
        )
    )
    await session.commit()
    return row


@router.get("/credits/{credit_id}/issuance")
async def issuance_status(
    credit_id: UUID, actor=Depends(get_current_user), session=Depends(get_session)
):
    from src.modules.energy.models import EnergyCredit, OutboxEvent
    from src.modules.community.models import ChainOperation

    credit = await session.get(EnergyCredit, credit_id)
    if not credit or credit.owner_id != actor.uid:
        raise PermissionError("Credit belongs to another member")
    events = (
        await session.exec(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == credit_id)
        )
    ).all()
    operations = (
        (
            await session.exec(
                select(ChainOperation).where(
                    ChainOperation.outbox_id.in_([e.id for e in events])
                )
            )
        ).all()
        if events
        else []
    )
    return {
        "credit_id": credit_id,
        "status": credit.status,
        "operations": [
            {
                "id": o.id,
                "transaction_hash": o.transaction_hash,
                "status": o.status,
                "block_hash": o.block_hash,
            }
            for o in operations
        ],
        "outbox": [
            {
                "event_type": e.event_type,
                "status": e.status,
                "attempts": e.attempts,
                "error": e.last_error,
                "accounting_hash": e.payload.get("evidence_hash"),
            }
            for e in events
        ],
    }


@router.get("/{community_id}/orderbook")
async def community_orderbook(
    community_id: UUID, actor=Depends(get_current_user), session=Depends(get_session)
):
    await service.membership(session, community_id, actor.uid)
    chain = CommunityChain()
    deployment = await chain.deployment(session, community_id)
    market = chain.contract("EnergyMarketplace", deployment.marketplace_address)
    orders = [
        market.functions.getOrder(i).call()
        for i in market.functions.activeOrderIds().call()
        if market.functions.isActive(i).call()
    ]
    orders.sort(key=lambda order: (order[3], order[0]))
    return {
        "orders": orders,
        "price_unit": "USDx base units per whole SUN",
        "maximum_active_orders": 128,
    }


@router.post("/{community_id}/operations/{operation_id}/replace")
async def replace_transaction(
    community_id: UUID,
    operation_id: UUID,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    from src.modules.community.models import ChainOperation
    from src.modules.energy.models import OutboxEvent

    await service.membership(session, community_id, actor.uid, operator=True)
    operation = await session.get(ChainOperation, operation_id)
    if operation is None:
        raise LookupError("Operation not found")
    event = await session.get(OutboxEvent, operation.outbox_id)
    if event.payload.get("community_id") != str(community_id):
        raise PermissionError("Operation belongs to another community")
    operation = await CommunityChain().replace_pending(session, operation_id)
    await session.commit()
    return {
        "operation_id": operation.id,
        "transaction_hash": operation.transaction_hash,
        "nonce": operation.nonce,
        "status": operation.status,
    }


@router.get("")
async def my_communities(actor=Depends(get_current_user), session=Depends(get_session)):
    from src.modules.community.models import EnergyCommunity

    return (
        await session.exec(
            select(EnergyCommunity)
            .join(
                CommunityMembership,
                CommunityMembership.community_id == EnergyCommunity.id,
            )
            .where(
                CommunityMembership.user_id == actor.uid,
                (CommunityMembership.status == "ACTIVE")
                | (EnergyCommunity.proposer_id == actor.uid),
            )
        )
    ).all()


@router.get("/{community_id}/nodes")
async def community_nodes(
    community_id: UUID, actor=Depends(get_current_user), session=Depends(get_session)
):
    await service.membership(session, community_id, actor.uid)
    return (
        await session.exec(
            select(CommunityNode).where(CommunityNode.community_id == community_id)
        )
    ).all()


@router.post("/{community_id}/governance/sync")
async def synchronize_governance(
    community_id: UUID,
    payload: TransactionInput,
    actor=Depends(get_current_user),
    session=Depends(get_session),
):
    """Relay verified registry evidence; being a relayer confers no authority."""
    from src.core.config import Config
    from src.modules.community.models import EnergyCommunity

    if not Config.COMMUNITY_REGISTRY_ADDRESS:
        raise ValueError("A governed CommunityRegistry deployment must be configured")
    community = (
        await session.exec(
            select(EnergyCommunity)
            .where(EnergyCommunity.id == community_id)
            .with_for_update()
        )
    ).first()
    if community is None:
        raise LookupError("Community proposal not found")
    chain = CommunityChain()
    registry = chain.contract("CommunityRegistry", Config.COMMUNITY_REGISTRY_ADDRESS)
    receipt = chain.canonical_receipt(payload.transaction_hash)
    logs = chain.event(registry, "CommunityTransition", receipt)
    key = community_id.bytes.rjust(32, b"\0")
    matching = [event for event in logs if event.args.communityId == key]
    if len(matching) != 1:
        raise ValueError("Receipt does not establish this community transition")
    current = registry.functions.communities(key).call()
    event = matching[0].args
    if int(current[2]) != int(event.status):
        raise ValueError(
            "Registry has a newer state; synchronize the current transition"
        )
    statuses = (
        "DRAFT",
        "PROPOSED",
        "UNDER_REVIEW",
        "APPROVED",
        "ACTIVE",
        "SUSPENDED",
        "REJECTED",
        "ARCHIVED",
    )
    if community.boundary_hash and community.boundary_hash != Web3.to_hex(
        event.boundary
    ):
        raise ValueError("Boundary commitment differs from submitted proposal")
    if community.policy_hash and community.policy_hash != Web3.to_hex(event.policy):
        raise ValueError("Policy commitment differs from submitted proposal")
    if community.sun_per_kwh != 1:
        raise ValueError(
            "Legacy conversion requires explicit migration before activation"
        )
    community.status = statuses[int(event.status)]
    community.registry_address = registry.address
    community.governance_transaction = payload.transaction_hash
    community.boundary_hash = Web3.to_hex(event.boundary)
    community.policy_hash = Web3.to_hex(event.policy)
    community.interval_seconds = int(event.intervalSeconds)
    if community.status == "ACTIVE":
        if not registry.functions.isActive(key).call():
            raise ValueError("Registry is paused")
        wallet = (
            await session.exec(
                select(Wallet).where(
                    Wallet.address == Web3.to_checksum_address(event.operator),
                    Wallet.is_verified.is_(True),
                )
            )
        ).first()
        if wallet is None:
            raise ValueError(
                "Governance-appointed operator must link their wallet first"
            )
        membership = (
            await session.exec(
                select(CommunityMembership).where(
                    CommunityMembership.community_id == community_id,
                    CommunityMembership.user_id == wallet.user_id,
                )
            )
        ).first()
        if membership is None:
            membership = CommunityMembership(
                community_id=community_id, user_id=wallet.user_id
            )
            session.add(membership)
        membership.role = "operator"
        membership.status = "ACTIVE"
    await session.commit()
    return community


@router.post("/{community_id}/propose")
async def propose_boundary(
    community_id: UUID, actor=Depends(get_current_user), session=Depends(get_session)
):
    import json
    from src.core.config import Config
    from src.modules.community.models import EnergyCommunity

    row = (
        await session.exec(
            select(EnergyCommunity)
            .where(EnergyCommunity.id == community_id)
            .with_for_update()
        )
    ).first()
    if row is None or row.proposer_id != actor.uid:
        raise PermissionError("Only the draft author may submit it")
    if row.status != "DRAFT" or not row.boundary_description:
        raise ValueError("A described physical boundary in DRAFT state is required")
    row.boundary_hash = Web3.to_hex(
        Web3.keccak(
            text=json.dumps(
                {"description": row.boundary_description, "topology": row.topology},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    )
    row.policy_hash = Web3.to_hex(
        Web3.keccak(
            text=json.dumps(
                {
                    "interval_seconds": row.interval_seconds,
                    "sun_per_kwh": "1",
                    "loss_factor": str(row.loss_factor),
                    "temporal_policy": row.temporal_policy,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    )
    row.status = "PROPOSED"
    transaction = None
    if Config.COMMUNITY_REGISTRY_ADDRESS:
        registry = CommunityChain().contract(
            "CommunityRegistry", Config.COMMUNITY_REGISTRY_ADDRESS
        )
        transaction = {
            "to": registry.address,
            "data": registry.functions.propose(
                row.id.bytes.rjust(32, b"\0"),
                Web3.to_bytes(hexstr=row.boundary_hash),
                Web3.to_bytes(hexstr=row.policy_hash),
                row.interval_seconds,
            )._encode_transaction_data(),
        }
    await session.commit()
    return {
        "community": row,
        "transaction": transaction,
        "notice": "Proposal grants no authority; only governance may approve and activate.",
    }


@router.post("/nodes/{node_id}/governance/sync")
async def synchronize_node(
    node_id: UUID, actor=Depends(get_current_user), session=Depends(get_session)
):
    from src.modules.community.models import CommunityNode, EnergyCommunity
    from src.modules.home.models import Home

    node = await session.get(CommunityNode, node_id)
    if node is None:
        raise LookupError("Node proposal not found")
    await service.membership(session, node.community_id, actor.uid, operator=True)
    community = await session.get(EnergyCommunity, node.community_id)
    if not community.registry_address:
        raise ValueError("Governed registry required")
    home = await session.get(Home, node.home_id)
    wallet = await service.wallet(session, home.owner_id)
    registry = CommunityChain().contract(
        "CommunityRegistry", community.registry_address
    )
    registered = registry.functions.nodes(
        node.community_id.bytes.rjust(32, b"\0"), node.id.bytes.rjust(32, b"\0")
    ).call()
    if registered.lower() != wallet.lower():
        raise ValueError("Node registrar has not approved this owner and physical node")
    node.authorized = True
    await session.commit()
    return node
