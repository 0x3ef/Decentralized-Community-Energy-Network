"""Application-level blockchain read operations."""

from __future__ import annotations

from decimal import Decimal

from src.blockchain.token_service import TokenService
from src.blockchain.web3_client import get_web3
from src.core.config import Config


class BlockchainService:
    """Expose network and SUN token information to API handlers."""

    def network_info(self) -> dict:
        web3 = get_web3()
        return {
            "chain_id": int(web3.eth.chain_id),
            "latest_block": int(web3.eth.block_number),
            "rpc_connected": bool(web3.is_connected()),
            "sun_token_address": Config.SUN_TOKEN_ADDRESS,
            "marketplace_address": Config.ENERGY_MARKET_ADDRESS,
        }

    def token_balance(self, address: str) -> Decimal:
        return TokenService().balance_of(address)

    def total_supply(self) -> Decimal:
        return TokenService().total_supply()
