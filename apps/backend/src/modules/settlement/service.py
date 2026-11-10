"""Verified intervals -> immutable policy snapshot -> allocation and commitment."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import select
from src.modules.community.allocation import allocate
from src.modules.community.chain import CommunityChain
from src.modules.community.models import (
    CommunityNode,
    EnergyCommunity,
    MeterAuthorization,
    NativeDeployment,
)
from src.modules.community.service import CommunityService
from src.modules.device.models import Device, TelemetryMessage
from src.modules.energy.models import EnergyCredit, EnergyInterval
from src.modules.home.models import Home
from src.modules.settlement.engine import (
    allocation_leaf,
    distribute,
    energy_leaf,
    hashed,
    key,
    merkle,
    obligation,
)
from src.modules.settlement.models import (
    IntervalAllocation,
    SettlementBatch,
    SettlementClaim,
    SettlementPolicy,
)
from src.modules.settlement.repository import SettlementRepository
from web3 import Web3


class CommunitySettlementService:
    def __init__(self, chain=None):
        self.chain = chain or CommunityChain()
        self.repository = SettlementRepository()
        self.communities = CommunityService()

    async def contracts(self, session, community_id):
        community = await session.get(EnergyCommunity, community_id)
        deployment = await session.get(NativeDeployment, community_id)
        if not community or not community.registry_address or not deployment:
            raise ValueError("Governed native deployment required")
        if self.chain.web3.eth.chain_id != deployment.chain_id:
            raise ValueError("Configured RPC chain differs from deployment")
        registry = self.chain.contract("CommunityRegistry", community.registry_address)
        approved = registry.functions.protocols(key(community_id)).call()
        if [x.lower() for x in approved] != [
            deployment.settlement_address.lower(),
            deployment.vault_address.lower(),
            deployment.sun_address.lower(),
        ]:
            raise ValueError("Deployment no longer matches governance approval")
        return (
            community,
            deployment,
            registry,
            self.chain.contract("CommunitySettlement", deployment.settlement_address),
            self.chain.contract("NativeSettlementVault", deployment.vault_address),
        )

    async def policy(self, session, community_id):
        community, _deployment, registry, _settlement, _vault = await self.contracts(
            session, community_id
        )
        cid = key(community_id)
        state = registry.functions.communities(cid).call()
        if not registry.functions.isActive(cid).call() or community.status != "ACTIVE":
            raise PermissionError("Active governed community required")
        policy_hash = Web3.to_hex(state[4])
        price = registry.functions.priceWeiPerKwh(cid).call()
        if (
            price <= 0
            or policy_hash != community.policy_hash
            or state[5] != community.interval_seconds
        ):
            raise ValueError("Policy must match confirmed governance")
        await self.repository.lock(session, f"native-policy:{community_id}")
        row = (
            await session.exec(
                select(SettlementPolicy).where(
                    SettlementPolicy.community_id == community_id,
                    SettlementPolicy.policy_hash == policy_hash,
                )
            )
        ).first()
        if row:
            if int(row.price_wei_per_kwh) != price or row.interval_seconds != state[5]:
                raise ValueError(
                    "Immutable policy snapshot changed; explicit correction required"
                )
            return row
        row = SettlementPolicy(
            community_id=community_id,
            policy_hash=policy_hash,
            price_wei_per_kwh=Decimal(price),
            interval_seconds=state[5],
            governance_reference=community.governance_transaction or "",
            rules={
                "algorithm": "proportional-largest-remainder-v1",
                "node_types": ["smart_meter"],
                "measurement": "finalized-net-grid-counters-with-boundary-coverage",
                "loss_factor": str(community.loss_factor),
                "funding": "ETH-and-SUN-reserved-before-execute",
                "rounding": "ceil-per-producer-consumer-edge-wei",
                "unallocated": "retained-producer-SUN-no-payment",
                "underfunded": "UNFUNDED-retry-no-financial-completion",
                "correction": "immutable-no-automatic-reversal",
                "delivery": "producer-escrow-SUN-atomic-pull-earnings",
                "retirement": "complete-delivered-node-cap-user-burn-no-second-payment",
            },
        )
        session.add(row)
        await session.flush()
        return row

    async def calculate_interval(self, session, community_id: UUID, start: datetime):
        if start.tzinfo is None:
            raise ValueError("UTC-aware interval required")
        start = start.astimezone(UTC)
        await self.repository.lock(
            session, f"interval:{community_id}:{start.isoformat()}"
        )
        policy = await self.policy(session, community_id)
        if start.microsecond or int(start.timestamp()) % policy.interval_seconds:
            raise ValueError("Start must align with the governed interval")
        end = start + timedelta(seconds=policy.interval_seconds)
        if end > datetime.now(UTC) - timedelta(minutes=2):
            raise ValueError("Interval is not closed beyond the telemetry grace period")
        existing = await self.repository.interval(session, community_id, start, end)
        if existing:
            return existing
        _community, deployment, registry, _settlement, _vault = await self.contracts(
            session, community_id
        )
        intervals = (
            await session.exec(
                select(EnergyInterval, CommunityNode, Home)
                .join(CommunityNode, CommunityNode.home_id == EnergyInterval.home_id)
                .join(Home, Home.id == EnergyInterval.home_id)
                .where(
                    CommunityNode.community_id == community_id,
                    CommunityNode.authorized.is_(True),
                    EnergyInterval.interval_start == start,
                    EnergyInterval.interval_end == end,
                    EnergyInterval.quality_status == "FINALIZED",
                )
            )
        ).all()
        participants = {}
        evidence = []
        for interval, node, home in intervals:
            try:
                await self.communities.membership(session, community_id, home.owner_id)
            except (PermissionError, LookupError):
                continue
            wallet = await self.communities.wallet(session, home.owner_id)
            if (
                registry.functions.nodes(key(community_id), key(node.id)).call().lower()
                != wallet.lower()
            ):
                continue
            meters = (
                await session.exec(
                    select(Device)
                    .join(MeterAuthorization, MeterAuthorization.device_id == Device.id)
                    .where(
                        MeterAuthorization.node_id == node.id,
                        MeterAuthorization.active.is_(True),
                        Device.status == "ACTIVE",
                        Device.device_type == "smart_meter",
                    )
                )
            ).all()
            if len(meters) != 1:
                continue
            device = meters[0]
            if registry.functions.meters(
                key(community_id), key(device.device_id)
            ).call() != key(node.id):
                continue
            messages = (
                await session.exec(
                    select(TelemetryMessage)
                    .where(
                        TelemetryMessage.device_id == device.id,
                        TelemetryMessage.measured_at >= start,
                        TelemetryMessage.measured_at <= end,
                        TelemetryMessage.quality_status == "PROCESSED",
                    )
                    .order_by(TelemetryMessage.measured_at)
                )
            ).all()
            # Conservative: missing either boundary establishes no full-interval eligibility.
            if (
                len(messages) < 2
                or messages[0].measured_at != start
                or messages[-1].measured_at != end
            ):
                continue
            export = max(
                0,
                min(interval.eligible_export_wh, interval.grid_export_wh)
                - interval.grid_import_wh,
            )
            supply = int(Decimal(export) * (1 - Decimal(policy.rules["loss_factor"])))
            demand = max(0, interval.grid_import_wh - interval.grid_export_wh)
            participants[str(node.id)] = {
                "interval": interval,
                "node": node,
                "device": device,
                "user": home.owner_id,
                "wallet": wallet,
                "supply": supply,
                "demand": demand,
            }
            evidence.append(
                {
                    "interval_id": str(interval.id),
                    "node_id": str(node.id),
                    "meter_id": str(device.device_id),
                    "telemetry_ids": [str(m.id) for m in messages],
                    "telemetry_hashes": [
                        hashed(
                            __import__("json").dumps(
                                m.payload, sort_keys=True, separators=(",", ":")
                            )
                        )
                        for m in messages
                    ],
                    "injection_wh": supply,
                    "demand_wh": demand,
                    "calculation_version": interval.calculation_version,
                }
            )
        # Net self-supplied energy across a wallet's multiple physical nodes.
        # This prevents economically meaningless payments from a wallet to itself.
        for wallet in sorted({p["wallet"] for p in participants.values()}):
            owned = {n: p for n, p in participants.items() if p["wallet"] == wallet}
            total_supply = sum(p["supply"] for p in owned.values())
            total_demand = sum(p["demand"] for p in owned.values())
            net_supply = allocate(
                max(0, total_supply - total_demand),
                {n: p["supply"] for n, p in owned.items()},
            )
            net_demand = allocate(
                max(0, total_demand - total_supply),
                {n: p["demand"] for n, p in owned.items()},
            )
            for n, p in owned.items():
                p["supply"], p["demand"] = net_supply[n], net_demand[n]
        supply = {n: p["supply"] for n, p in participants.items() if p["supply"]}
        demand = {n: p["demand"] for n, p in participants.items() if p["demand"]}
        if not supply:
            raise ValueError("No fully observed verified injection")
        pairs = distribute(supply, demand)
        batch_id = uuid4()
        chain_batch = hashed(
            f"native-batch:{deployment.chain_id}:{deployment.settlement_address}:{community_id}:{start.isoformat()}:{policy.policy_hash}"
        )
        batch = SettlementBatch(
            id=batch_id,
            community_id=community_id,
            policy_id=policy.id,
            interval_start=start,
            interval_end=end,
            chain_batch_id=chain_batch,
            root="",
            injection_wh=sum(supply.values()),
            consumption_wh=sum(demand.values()),
            allocated_wh=sum(p[2] for p in pairs),
            total_due_wei=Decimal(
                sum(obligation(p[2], int(policy.price_wei_per_kwh)) for p in pairs)
            ),
            evidence={
                "measurements": evidence,
                "netted_nodes": {
                    n: {"injection_wh": p["supply"], "demand_wh": p["demand"]}
                    for n, p in sorted(participants.items())
                },
                "netting": "per-wallet-interval-distributed-to-physical-nodes",
                "network_constraints": "no-topology-flow-model",
                "policy": policy.rules,
            },
        )
        session.add(batch)
        await session.flush()
        rows, leaves = [], []
        caps = {}
        for _, consumer, _wh, cap in pairs:
            caps[consumer] = cap
        for kind, quantities in ((0, supply), (1, caps)):
            for node_id, wh in sorted(quantities.items()):
                p = participants[node_id]
                claim = SettlementClaim(
                    batch_id=batch.id,
                    user_id=p["user"],
                    node_id=p["node"].id,
                    meter_id=p["device"].id,
                    interval_id=p["interval"].id,
                    kind=kind,
                    chain_claim_id=hashed(f"{chain_batch}:{kind}:{node_id}"),
                    wallet=p["wallet"],
                    energy_wh=wh,
                )
                if kind == 0:
                    credit = (
                        await session.exec(
                            select(EnergyCredit)
                            .where(
                                EnergyCredit.interval_id == p["interval"].id,
                                EnergyCredit.owner_id == p["user"],
                            )
                            .with_for_update()
                        )
                    ).first()
                    if credit and credit.status in ("ISSUED", "ISSUANCE_PENDING"):
                        raise ValueError(
                            "Physical interval already has an issued or pending legacy credit"
                        )
                    if not credit:
                        credit = EnergyCredit(
                            interval_id=p["interval"].id,
                            owner_id=p["user"],
                            energy_wh=wh,
                            token_amount=Decimal(wh) / 1000,
                            status="APPROVED",
                        )
                        session.add(credit)
                        await session.flush()
                    else:
                        credit.energy_wh = wh
                        credit.token_amount = Decimal(wh) / 1000
                        credit.status = "APPROVED"
                    claim.energy_credit_id = credit.id
                rows.append(claim)
                leaves.append(
                    energy_leaf(
                        kind,
                        Web3.to_bytes(hexstr=chain_batch),
                        Web3.to_bytes(hexstr=claim.chain_claim_id),
                        key(p["node"].id),
                        key(p["device"].device_id),
                        p["wallet"],
                        wh,
                    )
                )
        for producer, consumer, wh, cap in pairs:
            p, c = participants[producer], participants[consumer]
            row = IntervalAllocation(
                batch_id=batch.id,
                producer_id=p["user"],
                consumer_id=c["user"],
                producer_node_id=p["node"].id,
                consumer_node_id=c["node"].id,
                injection_interval_id=p["interval"].id,
                consumption_interval_id=c["interval"].id,
                producer_wallet=p["wallet"],
                consumer_wallet=c["wallet"],
                chain_allocation_id=hashed(
                    f"{chain_batch}:allocation:{producer}:{consumer}"
                ),
                energy_wh=wh,
                consumer_cap_wh=cap,
                due_wei=Decimal(obligation(wh, int(policy.price_wei_per_kwh))),
            )
            rows.append(row)
            leaves.append(
                allocation_leaf(
                    Web3.to_bytes(hexstr=chain_batch),
                    Web3.to_bytes(hexstr=row.chain_allocation_id),
                    p["wallet"],
                    c["wallet"],
                    key(c["node"].id),
                    wh,
                    cap,
                    int(policy.price_wei_per_kwh),
                )
            )
        batch.root, proofs = merkle(leaves)
        for row, proof in zip(rows, proofs, strict=True):
            row.proof = proof
            session.add(row)
        await session.flush()
        await self.repository.enqueue(session, "submit", batch)
        return batch

    async def verify_funding(self, session, allocation, block="latest"):
        batch = await session.get(SettlementBatch, allocation.batch_id)
        _, _, _, _, vault = await self.contracts(session, batch.community_id)
        state = vault.functions.allocations(
            Web3.to_bytes(hexstr=allocation.chain_allocation_id)
        ).call(block_identifier=block)
        if state[6] == 1:
            return "FUNDED"
        if state[6] == 2:
            return "SETTLED"
        if state[6] == 3:
            return "CANCELLED"
        policy = await session.get(SettlementPolicy, batch.policy_id)
        funded = vault.functions.available(allocation.consumer_wallet).call(
            block_identifier=block
        ) >= int(allocation.due_wei) and vault.functions.priceLimit(
            allocation.consumer_wallet
        ).call(block_identifier=block) >= int(policy.price_wei_per_kwh)
        escrowed = (
            vault.functions.sunAvailable(allocation.producer_wallet).call(
                block_identifier=block
            )
            >= allocation.energy_wh * 10**15
        )
        return (
            "FUNDED"
            if funded and escrowed
            else "UNFUNDED"
            if not funded
            else "SUN_UNAVAILABLE"
        )
