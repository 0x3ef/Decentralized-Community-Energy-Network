"""Atomic authorization, allocation and append-only community accounting."""

from uuid import UUID
from sqlmodel.ext.asyncio.session import AsyncSession
from src.modules.auth.models import User

from decimal import Decimal
import hashlib
import json
from sqlalchemy import func
from sqlmodel import select
from src.modules.community.models import (
    EnergyCommunity,
    CommunityMembership,
    CommunityNode,
    MeterAuthorization,
    CommunityEnergyAllocation,
    CompensationRequest,
    CommunityEnergyLedger,
    SettlementObligation,
)
from src.modules.energy.models import EnergyInterval, EnergyCredit, OutboxEvent
from src.modules.home.models import Home
from src.modules.device.models import Device
from src.modules.wallet.models import Wallet


class CommunityService:
    async def membership(
        self,
        session: AsyncSession,
        community_id: UUID,
        user_id: UUID,
        *,
        operator: bool = False,
    ) -> CommunityMembership:
        community = await session.get(EnergyCommunity, community_id)
        if community is None or community.status != "ACTIVE":
            raise PermissionError("Community requires verified governance activation")
        if community.registry_address:
            from src.modules.community.chain import CommunityChain

            chain = CommunityChain()
            registry = chain.contract("CommunityRegistry", community.registry_address)
            if not registry.functions.isActive(
                community_id.bytes.rjust(32, b"\0")
            ).call():
                raise PermissionError("Community is suspended or paused on chain")
        result = await session.exec(
            select(CommunityMembership).where(
                CommunityMembership.community_id == community_id,
                CommunityMembership.user_id == user_id,
                CommunityMembership.status == "ACTIVE",
            )
        )
        membership = result.first()
        if not membership or (operator and membership.role != "operator"):
            raise PermissionError(
                "Active community membership with the required role is required"
            )
        if community.registry_address:
            wallet = await self.wallet(session, user_id)
            if operator:
                assigned = registry.functions.communities(
                    community_id.bytes.rjust(32, b"\0")
                ).call()[1]
                if assigned.lower() != wallet.lower():
                    raise PermissionError("Operator must be appointed by governance")
            elif not registry.functions.isMember(
                community_id.bytes.rjust(32, b"\0"), wallet
            ).call():
                raise PermissionError("Active on-chain membership required")
        return membership

    async def create(
        self, session: AsyncSession, actor: User, name: str
    ) -> EnergyCommunity:
        community = EnergyCommunity(name=name, proposer_id=actor.uid)
        session.add(community)
        await session.flush()
        session.add(
            CommunityMembership(
                community_id=community.id,
                user_id=actor.uid,
                role="member",
                status="PENDING",
            )
        )
        return community

    async def register_node(
        self, session: AsyncSession, actor: User, community_id: UUID, home_id: UUID
    ) -> CommunityNode:
        await self.membership(session, community_id, actor.uid, operator=True)
        home = await session.get(Home, home_id)
        if not home:
            raise LookupError("Home not found")
        await self.membership(session, community_id, home.owner_id)
        node = CommunityNode(
            community_id=community_id,
            home_id=home_id,
            authorized=(
                await session.get(EnergyCommunity, community_id)
            ).registry_address
            is None,
        )
        session.add(node)
        await session.flush()
        return node

    async def authorize_meter(
        self,
        session: AsyncSession,
        actor: User,
        node_id: UUID,
        device_id: UUID,
        credential: str,
    ) -> MeterAuthorization:
        node = (
            await session.exec(
                select(CommunityNode)
                .where(CommunityNode.id == node_id)
                .with_for_update()
            )
        ).first()
        if not node or not node.authorized:
            raise ValueError("Authorized node required")
        await self.membership(session, node.community_id, actor.uid, operator=True)
        device = await session.get(Device, device_id)
        if not device or device.home_id != node.home_id:
            raise ValueError("Meter must belong to the registered node home")
        if len(credential) < 32:
            raise ValueError("Meter credential must have at least 32 characters")
        existing_channel = (
            await session.exec(
                select(MeterAuthorization)
                .join(Device, Device.id == MeterAuthorization.device_id)
                .where(
                    MeterAuthorization.node_id == node.id,
                    MeterAuthorization.active.is_(True),
                    Device.device_type == device.device_type,
                )
            )
        ).first()
        if existing_channel:
            raise ValueError(
                "An authoritative meter is already registered for this node channel"
            )
        governed = await session.get(EnergyCommunity, node.community_id)
        if governed.registry_address:
            from src.modules.community.chain import CommunityChain

            registry = CommunityChain().contract(
                "CommunityRegistry", governed.registry_address
            )
            if registry.functions.meters(
                node.community_id.bytes.rjust(32, b"\0"),
                device.device_id.bytes.rjust(32, b"\0"),
            ).call() != node.id.bytes.rjust(32, b"\0"):
                raise PermissionError(
                    "Meter registrar must authorize this node/device on chain first"
                )
        authorization = MeterAuthorization(
            device_id=device.id,
            node_id=node.id,
            credential_hash=hashlib.sha256(credential.encode()).hexdigest(),
        )
        device.status = "ACTIVE"
        session.add(authorization)
        return authorization

    async def wallet(self, session: AsyncSession, user_id: UUID) -> str:
        result = await session.exec(
            select(Wallet).where(
                Wallet.user_id == user_id, Wallet.is_verified.is_(True)
            )
        )
        wallet = result.first()
        if not wallet:
            raise ValueError("Verified user-controlled wallet required")
        return wallet.address

    async def interval_node(
        self, session: AsyncSession, interval: EnergyInterval
    ) -> CommunityNode:
        result = await session.exec(
            select(CommunityNode).where(
                CommunityNode.home_id == interval.home_id,
                CommunityNode.authorized.is_(True),
            )
        )
        node = result.first()
        if not node:
            raise ValueError("Interval does not belong to an authorized community node")
        return node

    async def approve_credit(
        self, session: AsyncSession, actor: User, credit_id: UUID
    ) -> EnergyCredit:
        result = await session.exec(
            select(EnergyCredit).where(EnergyCredit.id == credit_id).with_for_update()
        )
        credit = result.first()
        if not credit:
            raise LookupError("Credit not found")
        interval = await session.get(EnergyInterval, credit.interval_id)
        node = await self.interval_node(session, interval)
        await self.membership(session, node.community_id, actor.uid, operator=True)
        await self.membership(session, node.community_id, credit.owner_id)
        community = await session.get(EnergyCommunity, node.community_id)
        home = await session.get(Home, interval.home_id)
        if home.owner_id != credit.owner_id:
            raise ValueError("Credit beneficiary must own the source node")
        expected = Decimal(credit.energy_wh) / 1000 * community.sun_per_kwh
        if (
            interval.quality_status != "FINALIZED"
            or credit.energy_wh > interval.eligible_export_wh
            or credit.token_amount != expected
        ):
            raise ValueError(
                "Credit must be backed by finalized verified eligible injection"
            )
        if credit.status == "APPROVED":
            return credit
        if credit.status != "PENDING":
            raise ValueError("Credit cannot be approved in this state")
        await self.wallet(session, credit.owner_id)
        from src.modules.device.models import TelemetryMessage

        source_messages = (
            await session.exec(
                select(TelemetryMessage)
                .join(Device, Device.id == TelemetryMessage.device_id)
                .where(
                    Device.home_id == interval.home_id,
                    TelemetryMessage.measured_at >= interval.interval_start,
                    TelemetryMessage.measured_at <= interval.interval_end,
                    TelemetryMessage.quality_status == "PROCESSED",
                )
                .order_by(TelemetryMessage.id)
            )
        ).all()
        commitment = {
            "community": str(node.community_id),
            "credit": str(credit.id),
            "interval": str(interval.id),
            "start": interval.interval_start.isoformat(),
            "end": interval.interval_end.isoformat(),
            "eligible_wh": credit.energy_wh,
            "sun": str(credit.token_amount),
            "sources": [
                {"id": str(m.id), "payload": m.payload} for m in source_messages
            ],
        }
        evidence_hash = (
            "0x"
            + hashlib.sha256(
                json.dumps(commitment, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        credit.status = "APPROVED"
        session.add(
            OutboxEvent(
                event_type="community.credit.issue",
                aggregate_type="ENERGY_CREDIT",
                aggregate_id=credit.id,
                payload={
                    "community_id": str(node.community_id),
                    "credit_id": str(credit.id),
                    "evidence_hash": evidence_hash,
                },
            )
        )
        self.ledger(
            session, node.community_id, "CREDIT_APPROVED", credit.id, credit.energy_wh
        )
        return credit

    def ledger(
        self,
        session: AsyncSession,
        community_id: UUID,
        operation: str,
        source_id: UUID,
        energy_wh: int = 0,
        blockchain_hash: str | None = None,
    ) -> None:
        session.add(
            CommunityEnergyLedger(
                community_id=community_id,
                operation=operation,
                source_id=source_id,
                energy_wh=energy_wh,
                reference=f"{operation}:{source_id}",
                blockchain_hash=blockchain_hash,
            )
        )

    async def reserve_compensation(
        self,
        session: AsyncSession,
        actor: User,
        community_id: UUID,
        injection_id: UUID,
        withdrawal_id: UUID,
        energy_wh: int,
        key: str,
    ) -> CompensationRequest:
        await self.membership(session, community_id, actor.uid)
        # Lock a stable community row first to serialize competing reservations,
        # including creation of the first reservation for a pair of intervals.
        await session.exec(
            select(EnergyCommunity)
            .where(EnergyCommunity.id == community_id)
            .with_for_update(key_share=True)
        )
        result = await session.exec(
            select(CompensationRequest).where(
                CompensationRequest.idempotency_key == key
            )
        )
        existing = result.first()
        if existing:
            allocation = await session.get(
                CommunityEnergyAllocation, existing.allocation_id
            )
            if (
                existing.user_id != actor.uid
                or existing.community_id != community_id
                or existing.energy_wh != energy_wh
                or allocation.injection_interval_id != injection_id
                or allocation.withdrawal_interval_id != withdrawal_id
            ):
                raise ValueError("Idempotency key already used for another operation")
            return existing
        community = await session.get(EnergyCommunity, community_id)
        if not community or community.temporal_policy != "SAME_INTERVAL":
            raise ValueError(
                "Only explicit same-interval allocation policy is supported"
            )
        injection = await session.get(EnergyInterval, injection_id)
        withdrawal = await session.get(EnergyInterval, withdrawal_id)
        if (
            not injection
            or not withdrawal
            or injection_id == withdrawal_id
            or energy_wh <= 0
        ):
            raise ValueError(
                "Distinct source and consumer intervals with positive energy required"
            )
        for interval in (injection, withdrawal):
            node = await self.interval_node(session, interval)
            if (
                node.community_id != community_id
                or interval.quality_status != "FINALIZED"
            ):
                raise ValueError("Both intervals must be finalized in this community")
        home = await session.get(Home, withdrawal.home_id)
        if home.owner_id != actor.uid:
            raise PermissionError(
                "Only the withdrawal owner may compensate consumption"
            )
        if (injection.interval_start, injection.interval_end) != (
            withdrawal.interval_start,
            withdrawal.interval_end,
        ):
            raise ValueError("Temporal banking is disabled; intervals must match")
        issued = (
            await session.exec(
                select(EnergyCredit).where(
                    EnergyCredit.interval_id == injection_id,
                    EnergyCredit.status == "ISSUED",
                )
            )
        ).first()
        if not issued:
            raise ValueError("Source injection must have confirmed issued credits")

        async def allocated(column, interval_id):
            return (
                await session.exec(
                    select(
                        func.coalesce(func.sum(CommunityEnergyAllocation.energy_wh), 0)
                    ).where(column == interval_id)
                )
            ).one()

        available = int(
            Decimal(injection.eligible_export_wh) * (1 - community.loss_factor)
        )
        if (
            energy_wh
            + await allocated(
                CommunityEnergyAllocation.injection_interval_id, injection_id
            )
            > available
        ):
            raise ValueError("Allocation exceeds eligible injection")
        if (
            energy_wh
            + await allocated(
                CommunityEnergyAllocation.withdrawal_interval_id, withdrawal_id
            )
            > withdrawal.grid_import_wh
        ):
            raise ValueError("Compensation exceeds verified withdrawal")
        wallet = await self.wallet(session, actor.uid)
        units = Decimal(energy_wh) / 1000 * community.sun_per_kwh * 10**18
        if units != units.to_integral_value():
            raise ValueError("Quantity cannot be represented with SUN decimals")
        from src.modules.community.chain import CommunityChain

        chain = CommunityChain()
        deployment = await chain.deployment(session, community_id)
        token = chain.contract("SUNToken", deployment.sun_address)
        pending = (
            await session.exec(
                select(
                    func.coalesce(func.sum(CompensationRequest.token_units), 0)
                ).where(
                    CompensationRequest.community_id == community_id,
                    CompensationRequest.wallet == wallet,
                    CompensationRequest.status.in_(
                        ("RESERVED", "AUTHORIZED", "SUBMITTED", "RECONCILIATION")
                    ),
                )
            )
        ).one()
        if Decimal(token.functions.balanceOf(wallet).call()) - pending < units:
            raise ValueError("Insufficient unreserved SUN balance")
        allocation = CommunityEnergyAllocation(
            community_id=community_id,
            injection_interval_id=injection_id,
            withdrawal_interval_id=withdrawal_id,
            energy_wh=energy_wh,
        )
        session.add(allocation)
        await session.flush()
        evidence = hashlib.sha256(
            json.dumps(
                {
                    "allocation": str(allocation.id),
                    "injection": str(injection_id),
                    "withdrawal": str(withdrawal_id),
                    "wh": energy_wh,
                    "community": str(community_id),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        request = CompensationRequest(
            idempotency_key=key,
            community_id=community_id,
            user_id=actor.uid,
            allocation_id=allocation.id,
            energy_wh=energy_wh,
            token_units=units,
            wallet=wallet,
            evidence_hash="0x" + evidence,
        )
        session.add(request)
        await session.flush()
        session.add(
            OutboxEvent(
                event_type="community.retirement.authorize",
                aggregate_type="COMPENSATION",
                aggregate_id=request.id,
                payload={
                    "community_id": str(community_id),
                    "request_id": str(request.id),
                },
            )
        )
        self.ledger(session, community_id, "ALLOCATION_RESERVED", request.id, energy_wh)
        return request

    async def statement(
        self, session: AsyncSession, actor: User, community_id: UUID
    ) -> dict:
        await self.membership(session, community_id, actor.uid)
        intervals = (
            await session.exec(
                select(EnergyInterval)
                .join(CommunityNode, CommunityNode.home_id == EnergyInterval.home_id)
                .where(
                    CommunityNode.community_id == community_id,
                    EnergyInterval.quality_status == "FINALIZED",
                )
            )
        ).all()
        allocations = (
            await session.exec(
                select(CommunityEnergyAllocation).where(
                    CommunityEnergyAllocation.community_id == community_id
                )
            )
        ).all()
        requests = (
            await session.exec(
                select(CompensationRequest).where(
                    CompensationRequest.community_id == community_id
                )
            )
        ).all()
        payments = (
            await session.exec(
                select(SettlementObligation).where(
                    SettlementObligation.community_id == community_id
                )
            )
        ).all()
        return {
            "community_id": community_id,
            "verified_injection_wh": sum(i.eligible_export_wh for i in intervals),
            "verified_withdrawal_wh": sum(i.grid_import_wh for i in intervals),
            "allocated_wh": sum(a.energy_wh for a in allocations),
            "compensated_wh": sum(
                r.energy_wh for r in requests if r.status == "CONFIRMED"
            ),
            "unallocated_injection_wh": sum(i.eligible_export_wh for i in intervals)
            - sum(a.energy_wh for a in allocations),
            "uncompensated_withdrawal_wh": sum(i.grid_import_wh for i in intervals)
            - sum(r.energy_wh for r in requests if r.status == "CONFIRMED"),
            "retirements": requests,
            "simulated_payments": payments,
            "payment_notice": "Historical payments retain their explicit original asset units. New governed settlement uses native test ETH; no fiat conversion.",
        }
