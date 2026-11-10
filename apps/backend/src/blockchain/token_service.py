"""SUN ERC-20 operations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from web3 import Web3

from src.blockchain.abi import SUN_TOKEN_ABI
from src.blockchain.transaction_service import TransactionService
from src.blockchain.web3_client import get_web3, load_contract
from src.core.config import Config


class TokenService:
    """Read SUN balances and submit authorized SUN mint transactions."""

    DECIMALS = 18

    def __init__(self) -> None:
        self.web3 = get_web3()
        self.contract = load_contract(Config.SUN_TOKEN_ADDRESS, SUN_TOKEN_ABI)
        self.transactions = TransactionService()

    @classmethod
    def to_base_units(cls, amount: Decimal | str | int) -> int:
        """Convert a human-readable SUN amount into uint256 base units."""
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Invalid SUN amount") from exc
        if not value.is_finite() or value <= 0:
            raise ValueError("SUN amount must be greater than zero")
        scaled = value * (Decimal(10) ** cls.DECIMALS)
        if scaled != scaled.to_integral_value():
            raise ValueError("SUN supports at most 18 decimal places")
        return int(scaled)

    @staticmethod
    def credit_uuid_to_bytes32(credit_id: str) -> bytes:
        """Encode a UUID as a stable bytes32 value."""
        import uuid

        try:
            return uuid.UUID(str(credit_id)).bytes
        except (ValueError, AttributeError) as exc:
            raise ValueError("credit_id must be a valid UUID") from exc

    def mint(
        self,
        *,
        to: str,
        amount_tokens: Decimal | str | int,
        credit_id: str,
    ) -> dict:
        """Mint SUN once for an approved energy-credit UUID."""
        recipient = Web3.to_checksum_address(to)
        amount = self.to_base_units(amount_tokens)
        credit_key = self.credit_uuid_to_bytes32(credit_id)

        if self.contract.functions.issuedCredits(credit_key).call():
            raise ValueError(f"Credit {credit_id} was already issued on-chain")

        function = self.contract.functions.mint(recipient, amount, credit_key)
        return self.transactions.submit_transaction(function)

    def balance_of(self, address: str) -> Decimal:
        checksum = Web3.to_checksum_address(address)
        raw = self.contract.functions.balanceOf(checksum).call()
        return Decimal(raw) / (Decimal(10) ** self.DECIMALS)

    def total_supply(self) -> Decimal:
        raw = self.contract.functions.totalSupply().call()
        return Decimal(raw) / (Decimal(10) ** self.DECIMALS)
