from random import Random

import pytest
from src.modules.settlement.engine import distribute, merkle, obligation
from web3 import Web3


def test_five_kwh_injection_three_kwh_consumption():
    pairs = distribute({"A": 5000}, {"B": 3000})
    assert pairs == [("A", "B", 3000, 3000)]
    assert obligation(3000, 10**15) == 3 * 10**15


def test_exact_wei_rounding_and_bounds():
    assert obligation(1, 1) == 1
    assert obligation(999, 1001) == 1000
    assert obligation(10**50, 10**20) == 10**67
    for args in [(0, 1), (1, 0), (-1, 1), (2**256, 1), (2**255, 2**255)]:
        with pytest.raises(ValueError):
            obligation(*args)


def test_allocation_conserves_and_is_independent_of_input_order():
    random = Random(91)
    for _ in range(200):
        supply = {f"p{i}": random.randrange(10000) for i in range(4)}
        demand = {f"c{i}": random.randrange(10000) for i in range(7)}
        pairs = distribute(supply, demand)
        assert pairs == distribute(
            dict(reversed(list(supply.items()))), dict(reversed(list(demand.items())))
        )
        assert sum(p[2] for p in pairs) == min(
            sum(supply.values()), sum(demand.values())
        )
        assert all(
            sum(p[2] for p in pairs if p[0] == node) <= wh
            for node, wh in supply.items()
        )
        assert all(
            sum(p[2] for p in pairs if p[1] == node) <= wh
            for node, wh in demand.items()
        )
        paid = sum(obligation(p[2], 1001) for p in pairs)
        assert paid == sum(
            sum(obligation(p[2], 1001) for p in pairs if p[0] == node)
            for node in supply
        )


@pytest.mark.parametrize("count", [1, 2, 3, 7, 16, 33])
def test_merkle_proofs_with_odd_leaves_and_tampering(count):
    leaves = [Web3.keccak(text=str(i)) for i in range(count)]
    root, proofs = merkle(leaves)
    for leaf, proof in zip(leaves, proofs, strict=True):
        current = leaf
        for sibling in proof:
            current = Web3.keccak(
                b"".join(sorted((current, Web3.to_bytes(hexstr=sibling))))
            )
        assert Web3.to_hex(current) == root
