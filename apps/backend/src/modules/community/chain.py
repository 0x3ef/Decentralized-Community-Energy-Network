"""Verified community contract operations; no user private keys are accepted."""

from uuid import UUID
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from src.modules.auth.models import User
from web3.contract import Contract
from web3.types import TxReceipt

from datetime import datetime, timezone, timedelta
import logging
import json
from pathlib import Path
from decimal import Decimal
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.logs import DISCARD
from sqlalchemy import text, func
from sqlmodel import select
from src.core.config import Config
from src.modules.community.models import (
    ChainDeployment,
    ChainOperation,
    CompensationRequest,
    SettlementObligation,
)
from src.modules.community.service import CommunityService
from src.modules.energy.models import EnergyCredit, OutboxEvent

ABI_ROOT = Path(__file__).resolve().parents[2] / "blockchain" / "abis"


class AwaitingConfirmations(ValueError):
    """Receipt exists but has not reached the configured confirmation depth."""


class CommunityChain:
    def __init__(self, web3: Web3 | None = None) -> None:
        self.web3 = web3 or Web3(
            Web3.HTTPProvider(Config.WEB3_PROVIDER_URL, request_kwargs={"timeout": 20})
        )

    def contract(self, name: str, address: str) -> Contract:
        return self.web3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=json.loads((ABI_ROOT / f"{name}.json").read_text()),
        )

    async def deployment(
        self, session: AsyncSession, community_id: UUID
    ) -> ChainDeployment:
        deployment = await session.get(ChainDeployment, community_id)
        if not deployment or deployment.chain_id != self.web3.eth.chain_id:
            raise ValueError(
                "Community contract deployment is missing or chain changed"
            )
        return deployment

    def canonical_receipt(self, tx_hash: str) -> TxReceipt:
        receipt = self.web3.eth.get_transaction_receipt(tx_hash)
        block = self.web3.eth.get_block(receipt.blockNumber)
        if block.hash != receipt.blockHash:
            raise ValueError("Receipt is not canonical; reconciliation required")
        if receipt.status != 1:
            raise ValueError("Transaction reverted")
        if (
            self.web3.eth.block_number - receipt.blockNumber + 1
            < Config.BLOCKCHAIN_CONFIRMATION_BLOCKS
        ):
            raise AwaitingConfirmations("Transaction awaits required confirmations")
        return receipt

    def event(self, contract, event_name, receipt) -> list:
        # Decode only events emitted by the expected contract, never a lookalike.
        events = getattr(contract.events, event_name)().process_receipt(
            receipt, errors=DISCARD
        )
        return [e for e in events if e.address.lower() == contract.address.lower()]

    async def prepare(
        self, session: AsyncSession, event: OutboxEvent
    ) -> ChainOperation:
        existing = (
            await session.exec(
                select(ChainOperation).where(ChainOperation.outbox_id == event.id)
            )
        ).first()
        if existing:
            return existing
        account = self.web3.eth.account.from_key(Config.BACKEND_PRIVATE_KEY)
        deployment = await self.deployment(session, UUID(event.payload["community_id"]))
        if event.event_type == "community.credit.issue":
            credit = await session.get(EnergyCredit, event.aggregate_id)
            if credit.status not in ("APPROVED", "ISSUANCE_PENDING"):
                raise ValueError("Credit not approved")
            await CommunityService().membership(
                session, deployment.community_id, credit.owner_id
            )
            wallet = await CommunityService().wallet(session, credit.owner_id)
            token = self.contract("SUNToken", deployment.sun_address)
            function = token.functions.mint(
                wallet,
                int(credit.token_amount * 10**18),
                Web3.keccak(text=str(credit.id)),
            )
            credit.status = "ISSUANCE_PENDING"
        elif event.event_type == "community.credit.anchor":
            function = self.contract(
                "SUNToken", deployment.sun_address
            ).functions.anchorAccounting(
                Web3.keccak(text=str(event.aggregate_id)),
                Web3.to_bytes(hexstr=event.payload["evidence_hash"]),
            )
        elif event.event_type == "community.retirement.authorize":
            request = await session.get(CompensationRequest, event.aggregate_id)
            token = self.contract("SUNToken", deployment.sun_address)
            if token.functions.balanceOf(request.wallet).call() < int(
                request.token_units
            ):
                raise ValueError("Consumer has insufficient SUN balance")
            contract = self.contract(
                "EnergyCompensation", deployment.compensation_address
            )
            function = contract.functions.authorize(
                Web3.keccak(text=str(request.id)),
                request.wallet,
                int(request.token_units),
                Web3.to_bytes(hexstr=request.evidence_hash),
            )
        elif event.event_type == "community.member.authorize":
            user_id = UUID(event.payload["user_id"])
            from src.modules.community.models import CommunityMembership

            membership = (
                await session.exec(
                    select(CommunityMembership).where(
                        CommunityMembership.community_id == deployment.community_id,
                        CommunityMembership.user_id == user_id,
                    )
                )
            ).one()
            wallet = await CommunityService().wallet(session, user_id)
            function = self.contract(
                "EnergyMarketplace", deployment.marketplace_address
            ).functions.setMember(wallet, membership.status == "ACTIVE")
        else:
            raise ValueError("Unsupported community outbox operation")
        # PostgreSQL transaction lock coordinates every worker sharing the signer.
        lock = int.from_bytes(
            Web3.keccak(text=f"{deployment.chain_id}:{account.address}")[:8],
            "big",
            signed=True,
        )
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        maximum = (
            await session.exec(
                select(func.max(ChainOperation.nonce)).where(
                    ChainOperation.chain_id == deployment.chain_id,
                    ChainOperation.sender == account.address,
                )
            )
        ).one()
        nonce = max(
            self.web3.eth.get_transaction_count(account.address, "pending"),
            (maximum + 1) if maximum is not None else 0,
        )
        base = self.web3.eth.get_block("latest").get("baseFeePerGas")
        fees = (
            {
                "maxFeePerGas": int(base) * 2 + 2_000_000_000,
                "maxPriorityFeePerGas": 2_000_000_000,
            }
            if base is not None
            else {"gasPrice": self.web3.eth.gas_price}
        )
        transaction = function.build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": deployment.chain_id,
                **fees,
            }
        )
        signed = account.sign_transaction(transaction)
        operation = ChainOperation(
            outbox_id=event.id,
            chain_id=deployment.chain_id,
            sender=account.address,
            nonce=nonce,
            transaction_hash=Web3.to_hex(signed.hash),
            raw_transaction=Web3.to_hex(signed.raw_transaction),
        )
        session.add(operation)
        return operation

    async def process_outbox(
        self, factory: async_sessionmaker[AsyncSession], limit: int = 20
    ) -> int:
        count = 0
        # A failure is isolated to one event; the signed transaction is committed
        # before any broadcast, so a timeout or crash cannot generate a new mint.
        async with factory() as session:
            ids = list(
                (
                    await session.exec(
                        select(OutboxEvent.id)
                        .where(
                            OutboxEvent.event_type.like("community.%"),
                            OutboxEvent.status.in_(("PENDING", "PROCESSING")),
                            OutboxEvent.available_at <= datetime.now(timezone.utc),
                        )
                        .order_by(OutboxEvent.available_at)
                        .limit(limit)
                    )
                ).all()
            )
        for event_id in ids:
            try:
                async with factory() as session:
                    async with session.begin():
                        event = (
                            await session.exec(
                                select(OutboxEvent)
                                .where(OutboxEvent.id == event_id)
                                .with_for_update()
                            )
                        ).one()
                        if event.status == "PROCESSED":
                            continue
                        operation = await self.prepare(session, event)
                        event.status = "PROCESSING"
                        await session.flush()
                        tx_hash, raw = (
                            operation.transaction_hash,
                            operation.raw_transaction,
                        )
                # A prior fee-bumped attempt may have mined first. Adopt its
                # durable bytes before confirming the shared domain operation.
                async with factory() as history_session:
                    stored = (
                        await history_session.exec(
                            select(ChainOperation).where(
                                ChainOperation.outbox_id == event_id
                            )
                        )
                    ).one()
                    for attempt in stored.previous_transactions:
                        try:
                            self.web3.eth.get_transaction_receipt(
                                attempt["hash"]
                            )
                        except TransactionNotFound:
                            continue
                        stored.transaction_hash = attempt["hash"]
                        stored.raw_transaction = attempt["raw"]
                        tx_hash, raw = stored.transaction_hash, stored.raw_transaction
                        await history_session.commit()
                        break
                try:
                    receipt = self.web3.eth.get_transaction_receipt(tx_hash)
                except TransactionNotFound:
                    try:
                        self.web3.eth.get_transaction(tx_hash)
                    except TransactionNotFound:
                        self.web3.eth.send_raw_transaction(Web3.to_bytes(hexstr=raw))
                    continue
                receipt = self.canonical_receipt(tx_hash)
                async with factory() as session:
                    async with session.begin():
                        event = (
                            await session.exec(
                                select(OutboxEvent)
                                .where(OutboxEvent.id == event_id)
                                .with_for_update()
                            )
                        ).one()
                        if event.status == "PROCESSED":
                            continue
                        deployment = await self.deployment(
                            session, UUID(event.payload["community_id"])
                        )
                        operation = (
                            await session.exec(
                                select(ChainOperation).where(
                                    ChainOperation.outbox_id == event.id
                                )
                            )
                        ).one()
                        if event.event_type == "community.credit.issue":
                            credit = await session.get(EnergyCredit, event.aggregate_id)
                            wallet = await CommunityService().wallet(
                                session, credit.owner_id
                            )
                            logs = self.event(
                                self.contract("SUNToken", deployment.sun_address),
                                "CreditIssued",
                                receipt,
                            )
                            if (
                                len(logs) != 1
                                or logs[0].args.creditId
                                != Web3.keccak(text=str(credit.id))
                                or logs[0].args.recipient.lower() != wallet.lower()
                                or logs[0].args.amount
                                != int(credit.token_amount * 10**18)
                            ):
                                raise ValueError(
                                    "Mint receipt does not match approved credit"
                                )
                            credit.status = "ISSUED"
                            session.add(
                                OutboxEvent(
                                    event_type="community.credit.anchor",
                                    aggregate_type="ENERGY_CREDIT",
                                    aggregate_id=credit.id,
                                    payload={**event.payload},
                                )
                            )
                            CommunityService().ledger(
                                session,
                                deployment.community_id,
                                "CREDIT_ISSUED",
                                credit.id,
                                credit.energy_wh,
                                tx_hash,
                            )
                        elif event.event_type == "community.credit.anchor":
                            logs = self.event(
                                self.contract("SUNToken", deployment.sun_address),
                                "AccountingAnchored",
                                receipt,
                            )
                            if (
                                len(logs) != 1
                                or logs[0].args.creditId
                                != Web3.keccak(text=str(event.aggregate_id))
                                or logs[0].args.evidenceHash
                                != Web3.to_bytes(hexstr=event.payload["evidence_hash"])
                            ):
                                raise ValueError("Accounting commitment event mismatch")
                            CommunityService().ledger(
                                session,
                                deployment.community_id,
                                "ACCOUNTING_ANCHORED",
                                event.aggregate_id,
                                blockchain_hash=tx_hash,
                            )
                        elif event.event_type == "community.member.authorize":
                            logs = self.event(
                                self.contract(
                                    "EnergyMarketplace", deployment.marketplace_address
                                ),
                                "MembershipUpdated",
                                receipt,
                            )
                            wallet = await CommunityService().wallet(
                                session, UUID(event.payload["user_id"])
                            )
                            if (
                                len(logs) != 1
                                or logs[0].args.member.lower() != wallet.lower()
                            ):
                                raise ValueError(
                                    "Membership authorization event mismatch"
                                )
                        else:
                            request = await session.get(
                                CompensationRequest, event.aggregate_id
                            )
                            logs = self.event(
                                self.contract(
                                    "EnergyCompensation",
                                    deployment.compensation_address,
                                ),
                                "RetirementAuthorized",
                                receipt,
                            )
                            if (
                                len(logs) != 1
                                or logs[0].args.retirementId
                                != Web3.keccak(text=str(request.id))
                                or logs[0].args.amount != int(request.token_units)
                                or logs[0].args.evidence
                                != Web3.to_bytes(hexstr=request.evidence_hash)
                            ):
                                raise ValueError(
                                    "Retirement authorization event mismatch"
                                )
                            request.status = "AUTHORIZED"
                        operation.status = "CONFIRMED"
                        operation.block_hash = Web3.to_hex(receipt.blockHash)
                        event.status = "PROCESSED"
                        count += 1
            except AwaitingConfirmations:
                continue
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Community outbox event %s: %s", event_id, exc
                )
                async with factory() as session:
                    event = await session.get(OutboxEvent, event_id)
                    event.attempts += 1
                    event.last_error = str(exc)[:1000]
                    event.available_at = datetime.now(timezone.utc) + timedelta(
                        seconds=min(2**event.attempts, 300)
                    )
                    if event.attempts >= 8:
                        event.status = "DEAD_LETTER"
                    await session.commit()
        return count

    async def confirm_retirement(
        self, session: AsyncSession, actor: User, request_id: UUID, tx_hash: str
    ) -> CompensationRequest:
        request = (
            await session.exec(
                select(CompensationRequest)
                .where(CompensationRequest.id == request_id)
                .with_for_update()
            )
        ).first()
        if not request or request.user_id != actor.uid:
            raise PermissionError("Retirement belongs to another user")
        if request.status == "CONFIRMED":
            if request.transaction_hash != tx_hash:
                raise ValueError(
                    "Retirement already confirmed with another transaction"
                )
            return request
        if request.status not in ("AUTHORIZED", "SUBMITTED", "RECONCILIATION"):
            raise ValueError("Retirement has not been authorized")
        deployment = await self.deployment(session, request.community_id)
        receipt = self.canonical_receipt(tx_hash)
        transaction = self.web3.eth.get_transaction(tx_hash)
        contract = self.contract("EnergyCompensation", deployment.compensation_address)
        logs = self.event(contract, "CreditRetired", receipt)
        if (
            transaction["from"].lower() != request.wallet.lower()
            or not transaction["to"]
            or transaction["to"].lower() != contract.address.lower()
        ):
            raise ValueError("Retirement must be signed by the authorized consumer")
        if len(logs) != 1:
            raise ValueError("Missing retirement event")
        args = logs[0].args
        if (
            args.retirementId != Web3.keccak(text=str(request.id))
            or args.consumer.lower() != request.wallet.lower()
            or args.amount != int(request.token_units)
            or args.evidence != Web3.to_bytes(hexstr=request.evidence_hash)
            or args.communityId != request.community_id.bytes.rjust(32, b"\0")
        ):
            raise ValueError("Retirement event does not match reserved allocation")
        burns = self.event(
            self.contract("SUNToken", deployment.sun_address), "Transfer", receipt
        )
        if not any(
            e.args["from"].lower() == request.wallet.lower()
            and int(e.args.value) == int(request.token_units)
            and e.args.to == "0x" + "0" * 40
            for e in burns
        ):
            raise ValueError("Receipt does not contain the corresponding SUN burn")
        request.status = "CONFIRMED"
        request.transaction_hash = tx_hash
        request.block_hash = Web3.to_hex(receipt.blockHash)
        CommunityService().ledger(
            session,
            request.community_id,
            "CONSUMPTION_COMPENSATED",
            request.id,
            request.energy_wh,
            tx_hash,
        )
        return request

    async def reconcile_trade(
        self, session: AsyncSession, actor: User, community_id: UUID, tx_hash: str
    ) -> list[SettlementObligation]:
        await CommunityService().membership(session, community_id, actor.uid)
        deployment = await self.deployment(session, community_id)
        receipt = self.canonical_receipt(tx_hash)
        contract = self.contract("EnergyMarketplace", deployment.marketplace_address)
        logs = self.event(contract, "OrderFilled", receipt)
        if not logs:
            raise ValueError("No marketplace settlement events")
        results = []
        for event in logs:
            previous = (
                await session.exec(
                    select(SettlementObligation).where(
                        SettlementObligation.transaction_hash == tx_hash,
                        SettlementObligation.log_index == event.logIndex,
                    )
                )
            ).first()
            if previous:
                results.append(previous)
                continue
            args = event.args
            sun_events = self.event(
                self.contract("SUNToken", deployment.sun_address), "Transfer", receipt
            )
            payment_events = self.event(
                self.contract("MockUSD", deployment.payment_address),
                "Transfer",
                receipt,
            )

            def transfer_matches(events, sender, recipient, value):
                return any(
                    e.args["from"].lower() == sender.lower()
                    and e.args.to.lower() == recipient.lower()
                    and e.args.value == value
                    for e in events
                )

            if not transfer_matches(
                sun_events, contract.address, args.buyer, args.amount
            ) or not transfer_matches(
                payment_events, args.buyer, args.seller, args.totalPaid
            ):
                raise ValueError("Both atomic token transfers must be verified")
            row = SettlementObligation(
                community_id=community_id,
                order_id=args.orderId,
                buyer=args.buyer,
                seller=args.seller,
                sun_units=Decimal(args.amount),
                payment_units=Decimal(args.totalPaid),
                transaction_hash=tx_hash,
                log_index=event.logIndex,
                block_hash=Web3.to_hex(receipt.blockHash),
            )
            session.add(row)
            await session.flush()
            CommunityService().ledger(
                session, community_id, "TRADE_SETTLED", row.id, blockchain_hash=tx_hash
            )
            results.append(row)
        return results

    async def audit_confirmed(self, factory: async_sessionmaker[AsyncSession]) -> None:
        """Detect canonical-history changes after confirmation; never erase history.

        Reorgs freeze affected domain records for operator reconciliation. A
        later explicit reversal/reissue must follow accounting review.
        """

        def still_canonical(tx_hash: str, expected_block_hash):
            try:
                receipt = self.web3.eth.get_transaction_receipt(tx_hash)
                block = self.web3.eth.get_block(receipt.blockNumber)
                return (
                    receipt.status == 1
                    and Web3.to_hex(block.hash) == expected_block_hash
                    and receipt.blockHash == block.hash
                )
            except TransactionNotFound:
                return False

        async with factory() as session:
            async with session.begin():
                operations = (
                    await session.exec(
                        select(ChainOperation)
                        .where(ChainOperation.status == "CONFIRMED")
                        .with_for_update()
                    )
                ).all()
                for operation in operations:
                    if still_canonical(
                        operation.transaction_hash, operation.block_hash
                    ):
                        continue
                    operation.status = "RECONCILIATION"
                    event = await session.get(OutboxEvent, operation.outbox_id)
                    event.status = "RECONCILIATION"
                    community_id = UUID(event.payload["community_id"])
                    if event.event_type == "community.credit.issue":
                        credit = await session.get(EnergyCredit, event.aggregate_id)
                        credit.status = "FAILED"
                    elif event.event_type == "community.retirement.authorize":
                        request = await session.get(
                            CompensationRequest, event.aggregate_id
                        )
                        request.status = "RECONCILIATION"
                    CommunityService().ledger(
                        session,
                        community_id,
                        "CHAIN_OPERATION_REORG",
                        operation.id,
                        blockchain_hash=operation.transaction_hash,
                    )
                requests = (
                    await session.exec(
                        select(CompensationRequest)
                        .where(CompensationRequest.status == "CONFIRMED")
                        .with_for_update()
                    )
                ).all()
                for request in requests:
                    if not still_canonical(
                        request.transaction_hash, request.block_hash
                    ):
                        request.status = "RECONCILIATION"
                        CommunityService().ledger(
                            session,
                            request.community_id,
                            "COMPENSATION_REORG",
                            request.id,
                            -request.energy_wh,
                            request.transaction_hash,
                        )
                payments = (
                    await session.exec(
                        select(SettlementObligation)
                        .where(SettlementObligation.status == "CONFIRMED_SIMULATED")
                        .with_for_update()
                    )
                ).all()
                for payment in payments:
                    if not still_canonical(
                        payment.transaction_hash, payment.block_hash
                    ):
                        payment.status = "RECONCILIATION"
                        CommunityService().ledger(
                            session,
                            payment.community_id,
                            "PAYMENT_REORG",
                            payment.id,
                            blockchain_hash=payment.transaction_hash,
                        )

    async def sync_events(self, factory: async_sessionmaker[AsyncSession]) -> int:
        """Index confirmed user-signed trade and retirement events after crashes."""
        from src.modules.community.models import ChainSyncState, CommunityMembership
        from web3.exceptions import BlockNotFound

        count = 0
        async with factory() as session:
            deployments = (await session.exec(select(ChainDeployment))).all()
        for deployment in deployments:
            async with factory() as session:
                async with session.begin():
                    # Serialize cursor creation and advancement on this deployment.
                    await session.exec(
                        select(ChainDeployment)
                        .where(ChainDeployment.community_id == deployment.community_id)
                        .with_for_update()
                    )
                    state = await session.get(ChainSyncState, deployment.community_id)
                    if state is None:
                        state = ChainSyncState(community_id=deployment.community_id)
                        session.add(state)
                    if state.block_number >= 0:
                        try:
                            canonical = (
                                Web3.to_hex(
                                    self.web3.eth.get_block(state.block_number).hash
                                )
                                == state.block_hash
                            )
                        except BlockNotFound:
                            canonical = False
                        if not canonical:
                            state.block_number = max(-1, state.block_number - 64)
                    end = min(
                        self.web3.eth.block_number
                        - Config.BLOCKCHAIN_CONFIRMATION_BLOCKS
                        + 1,
                        state.block_number + 500,
                    )
                    if end <= state.block_number:
                        continue
                    member = (
                        await session.exec(
                            select(CommunityMembership).where(
                                CommunityMembership.community_id
                                == deployment.community_id,
                                CommunityMembership.status == "ACTIVE",
                                CommunityMembership.role == "operator",
                            )
                        )
                    ).first()
                    if member is None:
                        continue
                    operator = await session.get(User, member.user_id)
                    market = self.contract(
                        "EnergyMarketplace", deployment.marketplace_address
                    )
                    retirement = self.contract(
                        "EnergyCompensation", deployment.compensation_address
                    )
                    for log in market.events.OrderFilled().get_logs(
                        from_block=state.block_number + 1, to_block=end
                    ):
                        await self.reconcile_trade(
                            session,
                            operator,
                            deployment.community_id,
                            Web3.to_hex(log.transactionHash),
                        )
                        count += 1
                    requests = (
                        await session.exec(
                            select(CompensationRequest).where(
                                CompensationRequest.community_id
                                == deployment.community_id,
                                CompensationRequest.status.in_(
                                    ("AUTHORIZED", "SUBMITTED", "RECONCILIATION")
                                ),
                            )
                        )
                    ).all()
                    by_hash = {Web3.keccak(text=str(row.id)): row for row in requests}
                    for log in retirement.events.CreditRetired().get_logs(
                        from_block=state.block_number + 1, to_block=end
                    ):
                        request = by_hash.get(log.args.retirementId)
                        if request:
                            consumer = await session.get(User, request.user_id)
                            await self.confirm_retirement(
                                session,
                                consumer,
                                request.id,
                                Web3.to_hex(log.transactionHash),
                            )
                            count += 1
                    state.block_number = end
                    state.block_hash = Web3.to_hex(self.web3.eth.get_block(end).hash)
        return count

    async def replace_pending(
        self, session: AsyncSession, operation_id: UUID
    ) -> ChainOperation:
        """Prepare an explicit fee bump with identical nonce, value and calldata.

        The replacement is persisted before broadcast by the ordinary worker.
        Previous signed attempts remain available for receipt reconciliation.
        """
        operation = (
            await session.exec(
                select(ChainOperation)
                .where(ChainOperation.id == operation_id)
                .with_for_update()
            )
        ).one()
        if operation.status != "PREPARED":
            raise ValueError("Only an unconfirmed pending operation may be replaced")
        transaction = self.web3.eth.get_transaction(operation.transaction_hash)
        if transaction.get("blockNumber") is not None:
            raise ValueError(
                "Mined transactions must be confirmed or reconciled, not replaced"
            )
        account = self.web3.eth.account.from_key(Config.BACKEND_PRIVATE_KEY)
        if account.address.lower() != operation.sender.lower():
            raise ValueError("Operation belongs to a different authority signer")
        fees = (
            {
                "maxFeePerGas": max(
                    int(transaction["maxFeePerGas"]) * 2,
                    int(self.web3.eth.get_block("latest")["baseFeePerGas"]) * 2
                    + 2_000_000_000,
                ),
                "maxPriorityFeePerGas": int(transaction["maxPriorityFeePerGas"]) * 2,
            }
            if transaction.get("maxFeePerGas") is not None
            else {"gasPrice": int(transaction["gasPrice"]) * 2}
        )
        replacement = {
            "chainId": operation.chain_id,
            "nonce": operation.nonce,
            "to": transaction["to"],
            "value": transaction["value"],
            "gas": transaction["gas"],
            "data": transaction["input"],
            **fees,
        }
        signed = account.sign_transaction(replacement)
        operation.previous_transactions = [
            *operation.previous_transactions,
            {"hash": operation.transaction_hash, "raw": operation.raw_transaction},
        ]
        operation.transaction_hash = Web3.to_hex(signed.hash)
        operation.raw_transaction = Web3.to_hex(signed.raw_transaction)
        return operation
