"""Signing, submitting and inspecting EVM transactions."""

from __future__ import annotations

import logging
import threading
from typing import Any

from web3 import Web3
from web3.exceptions import TransactionNotFound

from src.blockchain.web3_client import get_account, get_web3

logger = logging.getLogger(__name__)
_nonce_lock = threading.Lock()


class TransactionService:
    """Submit transactions from the configured backend signer.

    The in-process lock prevents concurrent nonce allocation inside one
    process. Run a single signer worker per private key until a persistent,
    distributed nonce coordinator is implemented.
    """

    def __init__(self) -> None:
        self.web3 = get_web3()
        self.account = get_account()

    def submit_transaction(
        self,
        contract_function: Any,
        *,
        value: int = 0,
        gas_limit: int | None = None,
    ) -> dict[str, Any]:
        """Build, sign and broadcast a transaction without waiting for mining."""
        with _nonce_lock:
            nonce = self.web3.eth.get_transaction_count(
                self.account.address,
                block_identifier="pending",
            )
            tx: dict[str, Any] = {
                "from": self.account.address,
                "nonce": nonce,
                "chainId": self.web3.eth.chain_id,
                "value": value,
            }

            latest_block = self.web3.eth.get_block("latest")
            base_fee = latest_block.get("baseFeePerGas")
            if base_fee is not None:
                priority_fee = self.web3.to_wei(2, "gwei")
                tx["maxPriorityFeePerGas"] = priority_fee
                tx["maxFeePerGas"] = int(base_fee) * 2 + priority_fee
            else:
                tx["gasPrice"] = self.web3.eth.gas_price

            if gas_limit is None:
                estimate = contract_function.estimate_gas(
                    {"from": self.account.address, "value": value}
                )
                tx["gas"] = int(estimate * 1.20)
            else:
                tx["gas"] = gas_limit

            built = contract_function.build_transaction(tx)
            signed = self.account.sign_transaction(built)
            raw = getattr(signed, "raw_transaction", None)
            if raw is None:  # Compatibility with older web3.py releases.
                raw = signed.rawTransaction

            tx_hash = self.web3.eth.send_raw_transaction(raw)
            result = {
                "transaction_hash": Web3.to_hex(tx_hash),
                "nonce": nonce,
                "chain_id": int(self.web3.eth.chain_id),
                "sender": self.account.address,
            }
            logger.info(
                "Submitted transaction hash=%s nonce=%s",
                result["transaction_hash"],
                nonce,
            )
            return result

    def get_receipt(self, transaction_hash: str) -> dict[str, Any] | None:
        """Return a normalized receipt, or None while the transaction is pending."""
        try:
            receipt = self.web3.eth.get_transaction_receipt(transaction_hash)
        except TransactionNotFound:
            return None

        return {
            "transaction_hash": Web3.to_hex(receipt["transactionHash"]),
            "block_number": int(receipt["blockNumber"]),
            "block_hash": Web3.to_hex(receipt["blockHash"]),
            "gas_used": int(receipt["gasUsed"]),
            "status": int(receipt["status"]),
        }

    def confirmation_count(self, receipt: dict[str, Any]) -> int:
        """Return the number of canonical blocks including the receipt block."""
        current = int(self.web3.eth.block_number)
        return max(0, current - int(receipt["block_number"]) + 1)

    def is_confirmed(self, receipt: dict[str, Any], confirmations: int) -> bool:
        return self.confirmation_count(receipt) >= confirmations
