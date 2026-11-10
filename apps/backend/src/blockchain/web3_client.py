"""Centralized synchronous Web3 client.

The client is intentionally synchronous because web3.py's HTTP provider is
synchronous. Call it through asyncio.to_thread() from async application code.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import HTTPProvider, Web3
from web3.middleware import ExtraDataToPOAMiddleware

from src.core.config import Config

logger = logging.getLogger(__name__)


class Web3Client:
    """Owns the RPC connection and the backend transaction signer."""

    def __init__(self) -> None:
        self._web3: Web3 | None = None
        self._account: LocalAccount | None = None

    def _initialize(self) -> None:
        if self._web3 is not None and self._account is not None:
            return

        if not Config.WEB3_PROVIDER_URL:
            raise RuntimeError("WEB3_PROVIDER_URL is not configured")
        if not Config.BACKEND_PRIVATE_KEY:
            raise RuntimeError("BACKEND_PRIVATE_KEY is not configured")

        web3 = Web3(
            HTTPProvider(
                Config.WEB3_PROVIDER_URL,
                request_kwargs={"timeout": 30},
            )
        )

        # Keep this middleware only if the selected chain uses PoA headers.
        web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not web3.is_connected():
            raise ConnectionError("Unable to connect to the blockchain RPC")

        actual_chain_id = int(web3.eth.chain_id)
        if actual_chain_id != int(Config.CHAIN_ID):
            raise RuntimeError(
                f"Wrong chain: expected {Config.CHAIN_ID}, got {actual_chain_id}"
            )

        account = Account.from_key(Config.BACKEND_PRIVATE_KEY)
        self._web3 = web3
        self._account = account

        logger.info(
            "Connected to chain_id=%s with signer=%s",
            actual_chain_id,
            account.address,
        )

    @property
    def web3(self) -> Web3:
        if self._web3 is None:
            self._initialize()
        assert self._web3 is not None
        return self._web3

    @property
    def account(self) -> LocalAccount:
        if self._account is None:
            self._initialize()
        assert self._account is not None
        return self._account

    def load_contract(self, address: str, abi: list[dict]):
        """Load a deployed contract after validating its address and bytecode."""
        checksum = Web3.to_checksum_address(address)
        code = self.web3.eth.get_code(checksum)
        if not code or code == b"\x00":
            raise ValueError(f"No contract bytecode found at {checksum}")
        return self.web3.eth.contract(address=checksum, abi=abi)


@lru_cache(maxsize=1)
def get_web3_client() -> Web3Client:
    """Return the process-wide Web3 client."""
    return Web3Client()


def get_web3() -> Web3:
    return get_web3_client().web3


def get_account() -> LocalAccount:
    return get_web3_client().account


def load_contract(address: str, abi: list[dict]):
    return get_web3_client().load_contract(address, abi)
