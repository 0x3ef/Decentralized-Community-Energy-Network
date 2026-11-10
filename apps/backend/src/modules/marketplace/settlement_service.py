"""Settlement boundary between the off-chain book and the EVM contract.

A matched trade is not considered settled merely because the database matched
it. The buyer must submit the contract transaction from their own wallet.
This service records that externally signed transaction for confirmation.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from web3 import Web3
from sqlmodel import select

from src.blockchain.transaction_service import TransactionService
from src.core.config import Config
from src.modules.energy.models import BlockchainTransaction
from src.modules.marketplace.models import Trade
from src.modules.wallet.models import Wallet


class SettlementService:
    """Validate and persist buyer-submitted marketplace transaction hashes."""

    async def register_buyer_transaction(
        self, user, trade_id: UUID, tx_hash: str, session
    ) -> BlockchainTransaction:
        trade = await session.get(Trade, trade_id)
        if trade is None:
            raise LookupError("Trade not found")
        if trade.buyer_id != user.uid:
            raise PermissionError("Only the buyer can register settlement")
        if trade.status not in ("MATCHED_PENDING_SETTLEMENT", "PENDING"):
            raise ValueError("Trade is not awaiting settlement")

        existing_result = await session.exec(
            select(BlockchainTransaction).where(
                BlockchainTransaction.idempotency_key == f"marketplace.trade:{trade.id}"
            )
        )
        existing = existing_result.first()
        if existing is not None:
            raise ValueError("A settlement transaction is already registered")

        wallet_result = await session.exec(
            select(Wallet).where(
                Wallet.user_id == user.uid,
                Wallet.is_verified.is_(True),
            )
        )
        wallet = wallet_result.first()
        if wallet is None:
            raise ValueError("A verified wallet is required")

        service = TransactionService()
        tx = await asyncio.to_thread(
            service.web3.eth.get_transaction, tx_hash
        )
        if int(tx["chainId"]) != int(Config.CHAIN_ID):
            raise ValueError("Transaction was sent on the wrong chain")
        if not tx.get("to") or Web3.to_checksum_address(tx["to"]) != Web3.to_checksum_address(Config.ENERGY_MARKET_ADDRESS):
            raise ValueError("Transaction does not target the marketplace contract")
        if Web3.to_checksum_address(tx["from"]) != Web3.to_checksum_address(wallet.address):
            raise ValueError("Transaction sender does not match the buyer wallet")

        record = BlockchainTransaction(
            idempotency_key=f"marketplace.trade:{trade.id}",
            chain_id=int(Config.CHAIN_ID),
            contract_address=Config.ENERGY_MARKET_ADDRESS,
            transaction_hash=Web3.to_hex(tx["hash"]),
            sender=wallet.address,
            recipient=Config.ENERGY_MARKET_ADDRESS,
            operation_type="MARKETPLACE_FILL",
            entity_type="TRADE",
            entity_id=trade.id,
            nonce=int(tx["nonce"]),
            status="SUBMITTED",
        )
        session.add(record)
        trade.status = "SETTLEMENT_SUBMITTED"
        await session.commit()
        await session.refresh(record)
        return record
