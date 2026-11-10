"""A hash or receipt alone must never establish confirmed accounting."""

from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from hexbytes import HexBytes
from src.modules.community.chain import CommunityChain
from src.core.config import Config


@pytest.mark.parametrize(
    "status,canonical,depth,error",
    [
        (0, True, 10, "reverted"),
        (1, False, 10, "canonical"),
        (1, True, 0, "confirmations"),
    ],
)
def test_receipt_requires_success_canonical_block_and_confirmations(
    status, canonical, depth, error
):
    Config.BLOCKCHAIN_CONFIRMATION_BLOCKS = 2
    block_hash = HexBytes("0x" + "11" * 32)
    receipt = SimpleNamespace(status=status, blockNumber=10, blockHash=block_hash)
    eth = Mock()
    eth.get_transaction_receipt.return_value = receipt
    eth.get_block.return_value = SimpleNamespace(
        hash=block_hash if canonical else HexBytes("0x" + "22" * 32)
    )
    eth.block_number = 10 + depth
    with pytest.raises(ValueError, match=error):
        CommunityChain(SimpleNamespace(eth=eth)).canonical_receipt("0x" + "33" * 32)


def test_rpc_timeout_is_never_a_confirmation():
    eth = Mock()
    eth.get_transaction_receipt.side_effect = TimeoutError("RPC timed out")
    with pytest.raises(TimeoutError):
        CommunityChain(SimpleNamespace(eth=eth)).canonical_receipt("0x" + "33" * 32)
