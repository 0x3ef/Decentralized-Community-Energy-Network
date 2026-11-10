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
        raise ValueError("Reconcile atomic SUN/USDx trades through /communities/{community_id}/trades/reconcile")
