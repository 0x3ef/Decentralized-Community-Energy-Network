"""Integer Wh allocation and Solidity-compatible commitments; no financial floats."""

from eth_abi import encode
from src.modules.community.allocation import allocate
from web3 import Web3

UINT256 = 2**256


def obligation(wh: int, price: int) -> int:
    if wh <= 0 or price <= 0 or wh >= UINT256 or price >= UINT256:
        raise ValueError("Positive uint256 quantity and price required")
    value = (wh * price + 999) // 1000
    if value >= UINT256:
        raise ValueError("Obligation exceeds uint256")
    return value


def distribute(supply: dict[str, int], demand: dict[str, int]):
    if any(v < 0 for v in [*supply.values(), *demand.values()]):
        raise ValueError("Nonnegative verified quantities required")
    if set(supply) & set(demand):
        raise ValueError("Net each node's import/export before allocation")
    total = min(sum(supply.values()), sum(demand.values()))
    producers = allocate(total, supply)
    consumers = allocate(total, demand)
    remaining = dict(consumers)
    pairs = []
    for producer, quantity in producers.items():
        for consumer in consumers:
            wh = min(quantity, remaining[consumer])
            if wh:
                pairs.append((producer, consumer, wh, consumers[consumer]))
                quantity -= wh
                remaining[consumer] -= wh
    return pairs


def commitment(types, values) -> bytes:
    return Web3.keccak(Web3.keccak(encode(types, values)))


def energy_leaf(kind, batch, claim, node, meter, wallet, wh):
    return commitment(
        ["uint8", "bytes32", "bytes32", "bytes32", "bytes32", "address", "uint256"],
        [kind, batch, claim, node, meter, wallet, wh],
    )


def allocation_leaf(batch, claim, producer, consumer, node, wh, cap, price):
    return commitment(
        [
            "uint8",
            "bytes32",
            "bytes32",
            "address",
            "address",
            "bytes32",
            "uint256",
            "uint256",
            "uint256",
        ],
        [2, batch, claim, producer, consumer, node, wh, cap, price],
    )


def merkle(leaves: list[bytes]):
    if not leaves or len(set(leaves)) != len(leaves):
        raise ValueError("Nonempty unique leaves required")
    levels = [leaves]
    while len(levels[-1]) > 1:
        current = levels[-1]
        levels.append(
            [
                Web3.keccak(
                    b"".join(
                        sorted((current[i], current[min(i + 1, len(current) - 1)]))
                    )
                )
                for i in range(0, len(current), 2)
            ]
        )
    proofs = []
    for index in range(len(leaves)):
        proof = []
        for level in levels[:-1]:
            proof.append(Web3.to_hex(level[min(index ^ 1, len(level) - 1)]))
            index //= 2
        proofs.append(proof)
    return Web3.to_hex(levels[-1][0]), proofs


def key(identifier):
    return identifier.bytes.rjust(32, b"\0")


def hashed(text):
    return Web3.to_hex(Web3.keccak(text=text))
