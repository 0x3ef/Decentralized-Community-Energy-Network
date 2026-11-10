"""Outbox dispatcher and blockchain confirmation worker."""

from __future__ import annotations

import asyncio
import logging
import socket
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlmodel import select

from src.blockchain.monitor import monitor_submitted_transactions
from src.blockchain.token_service import TokenService
from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.modules.energy.models import (
    BlockchainTransaction, EnergyCredit, OutboxEvent,
)
from src.modules.wallet.models import Wallet

logger = logging.getLogger(__name__)
WORKER_ID = f"{socket.gethostname()}:{uuid.uuid4()}"
MAX_ATTEMPTS = 8
LEASE_SECONDS = 120


async def claim_outbox_events(limit: int = 20):
    """Atomically lease due outbox rows; no network calls occur in this transaction."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session:
        async with session.begin():
            result = await session.exec(
                select(OutboxEvent)
                .where(
                    ((OutboxEvent.status == "PENDING") &
                     (OutboxEvent.available_at <= now))
                    | ((OutboxEvent.status == "PROCESSING") &
                       (OutboxEvent.locked_at < now - timedelta(seconds=LEASE_SECONDS)))
                )
                .order_by(OutboxEvent.available_at, OutboxEvent.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = list(result.all())
            for row in rows:
                row.status = "PROCESSING"
                row.locked_at = now
                row.locked_by = WORKER_ID
                row.attempts += 1
            return [row.id for row in rows]


async def issue_credit(credit_id: uuid.UUID) -> None:
    """Create a durable transaction record, then broadcast the mint."""
    key = f"credit.issue:{credit_id}"
    async with AsyncSessionFactory() as session:
        credit = await session.get(EnergyCredit, credit_id)
        if credit is None:
            raise LookupError(f"Energy credit {credit_id} not found")
        if credit.status == "ISSUED":
            return
        if credit.status not in ("APPROVED", "ISSUANCE_PENDING"):
            raise ValueError(f"Credit cannot be issued from {credit.status}")

        existing_result = await session.exec(
            select(BlockchainTransaction).where(
                BlockchainTransaction.idempotency_key == key
            )
        )
        existing = existing_result.first()
        if existing and existing.status in ("SUBMITTED", "CONFIRMED"):
            return
        if existing and existing.status == "PENDING" and existing.transaction_hash:
            return

        wallet_result = await session.exec(
            select(Wallet).where(
                Wallet.user_id == credit.owner_id,
                Wallet.is_verified.is_(True),
            ).order_by(Wallet.created_at)
        )
        wallet = wallet_result.first()
        if wallet is None:
            raise ValueError("Credit owner has no verified wallet")

        if existing is None:
            tx_record = BlockchainTransaction(
                idempotency_key=key,
                chain_id=Config.CHAIN_ID,
                contract_address=Config.SUN_TOKEN_ADDRESS,
                operation_type="MINT",
                entity_type="ENERGY_CREDIT",
                entity_id=credit.id,
                status="PENDING",
            )
            session.add(tx_record)
        else:
            tx_record = existing
        credit.status = "ISSUANCE_PENDING"
        await session.commit()
        tx_id = tx_record.id
        amount = Decimal(credit.token_amount)
        wallet_address = wallet.address

    token_service = TokenService()
    result = await asyncio.to_thread(
        token_service.mint,
        to=wallet_address,
        amount_tokens=amount,
        credit_id=str(credit_id),
    )

    async with AsyncSessionFactory() as session:
        async with session.begin():
            tx_record = await session.get(BlockchainTransaction, tx_id)
            if tx_record is None:
                raise RuntimeError("Transaction record disappeared")
            tx_record.transaction_hash = result["transaction_hash"]
            tx_record.sender = result["sender"]
            tx_record.recipient = wallet_address
            tx_record.nonce = result["nonce"]
            tx_record.chain_id = result["chain_id"]
            tx_record.status = "SUBMITTED"
            tx_record.submitted_at = datetime.now(timezone.utc)


async def finish_event(event_id: uuid.UUID, error: Exception | None = None):
    async with AsyncSessionFactory() as session:
        async with session.begin():
            event = await session.get(OutboxEvent, event_id)
            if event is None:
                return
            event.locked_at = None
            event.locked_by = None
            if error is None:
                event.status = "PROCESSED"
                event.processed_at = datetime.now(timezone.utc)
                event.last_error = None
            else:
                event.last_error = str(error)[:4000]
                if event.attempts >= MAX_ATTEMPTS:
                    event.status = "DEAD_LETTER"
                else:
                    event.status = "PENDING"
                    event.available_at = datetime.now(timezone.utc) + timedelta(
                        seconds=min(300, 2 ** event.attempts)
                    )


async def process_event(event_id: uuid.UUID):
    async with AsyncSessionFactory() as session:
        event = await session.get(OutboxEvent, event_id)
        if event is None:
            return
        event_type = event.event_type
        aggregate_id = event.aggregate_id

    try:
        if event_type == "credit.issue":
            await issue_credit(aggregate_id)
        else:
            raise ValueError(f"Unsupported outbox event: {event_type}")
    except Exception as exc:
        logger.exception("Outbox event %s failed", event_id)
        await finish_event(event_id, exc)
    else:
        await finish_event(event_id)


async def run(poll_seconds: float = 2.0):
    """Run outbox dispatch and receipt monitoring continuously."""
    logger.info("Blockchain worker started: %s", WORKER_ID)
    while True:
        try:
            event_ids = await claim_outbox_events()
            for event_id in event_ids:
                await process_event(event_id)
            await monitor_submitted_transactions(AsyncSessionFactory)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Blockchain worker cycle failed")
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
