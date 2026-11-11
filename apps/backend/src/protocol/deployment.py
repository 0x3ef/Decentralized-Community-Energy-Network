"""Receipt-verified deployments with a public, resumable journal; no custody keys."""

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import UUID

from web3 import Web3

NAMES = (
    "TimelockController",
    "CommunityRegistry",
    "SUNToken",
    "CommunitySettlement",
    "NativeSettlementVault",
)
ZERO = "0x" + "0" * 40


def artifacts_at(directory):
    result = {}
    for name in NAMES:
        value = json.loads(
            (Path(directory) / f"{name}.sol" / f"{name}.json").read_text()
        )
        if not value.get("bytecode", {}).get("object"):
            raise ValueError(f"Compile the Foundry artifact for {name}")
        result[name] = value
    return result


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)


class Deployment:
    def __init__(
        self,
        web3,
        artifacts,
        journal,
        community_id,
        authority,
        proposer,
        executor,
        oracle,
        *,
        private_key=None,
        delay=0,
        challenge=1,
        confirmations=1,
    ):
        self.web3, self.artifacts, self.path = web3, artifacts, Path(journal)
        self.cid = UUID(str(community_id)).bytes.rjust(32, b"\0")
        self.authority, self.proposer, self.executor, self.oracle = [
            Web3.to_checksum_address(x) for x in (authority, proposer, executor, oracle)
        ]
        self.private_key, self.confirmations = private_key, confirmations
        self.delay, self.challenge = delay, challenge
        chain = web3.eth.chain_id
        if chain not in (31337, 1337, 11155111):
            raise ValueError("Only Anvil and Sepolia are supported")
        if any(
            x == ZERO
            for x in (self.authority, self.proposer, self.executor, self.oracle)
        ):
            raise ValueError(
                "Explicit nonzero deployment and authority addresses required"
            )
        if chain == 11155111 and (
            delay < 86400 or challenge < 86400 or confirmations < 3
        ):
            raise ValueError(
                "Sepolia requires >=1 day governance/challenge and >=3 confirmations"
            )
        fingerprint = {
            "chain_id": chain,
            "chain_genesis": Web3.to_hex(web3.eth.get_block(0).hash),
            "community_id": str(community_id),
            "deployer": self.authority,
            "proposer": self.proposer,
            "executor": self.executor,
            "oracle": self.oracle,
            "delay_seconds": delay,
            "challenge_seconds": challenge,
            "artifacts_hash": hashlib.sha256(
                json.dumps(
                    {
                        name: {
                            "abi": value["abi"],
                            "bytecode": value["bytecode"]["object"],
                        }
                        for name, value in artifacts.items()
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        }
        self.journal = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"configuration": fingerprint, "contracts": {}, "transactions": []}
        )
        if self.journal["configuration"] != fingerprint:
            raise ValueError(
                "Deployment journal/configuration differs; choose another journal"
            )
        for entry in self.journal["contracts"].values():
            if (
                not web3.eth.get_code(entry["address"])
                or Web3.to_hex(web3.eth.get_block(entry["block_number"]).hash)
                != entry["block_hash"]
            ):
                raise ValueError(
                    "Deployment chain was reset/reorganized; restore its state or use a fresh demo database and journal"
                )
        self.contracts = {}
        self.pending_name = None

    def send(self, function, sender=None, value=0):
        sender = sender or self.authority
        tx = {"from": sender, "value": value}
        if self.private_key:
            if sender.lower() != self.authority.lower():
                raise ValueError("This signer may not act for another participant")
            tx.update(
                chainId=self.web3.eth.chain_id,
                nonce=self.web3.eth.get_transaction_count(sender, "pending"),
            )
            signed = self.web3.eth.account.sign_transaction(
                function.build_transaction(tx), self.private_key
            )
            transaction_hash = self.web3.eth.send_raw_transaction(
                signed.raw_transaction
            )
        else:
            if self.web3.eth.chain_id not in (31337, 1337):
                raise ValueError("Unlocked-account submission is local-only")
            transaction_hash = function.transact(tx)
        if self.pending_name:
            self.journal.setdefault("pending", {})[self.pending_name] = Web3.to_hex(
                transaction_hash
            )
            save_json(self.path, self.journal)
        receipt = self.wait(transaction_hash)
        return receipt

    def wait(self, transaction_hash):
        receipt = self.web3.eth.wait_for_transaction_receipt(
            transaction_hash, timeout=180
        )
        if receipt.status != 1:
            raise RuntimeError(f"Transaction reverted: {Web3.to_hex(transaction_hash)}")
        deadline = time.monotonic() + 300
        while self.web3.eth.block_number < receipt.blockNumber + self.confirmations - 1:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Confirmation pending: {Web3.to_hex(transaction_hash)}"
                )
            time.sleep(1)
        if (
            self.web3.eth.get_transaction_receipt(transaction_hash).blockHash
            != receipt.blockHash
        ):
            raise RuntimeError("Receipt reorganized during confirmation")
        return receipt

    def deploy(self):
        arguments = {
            "TimelockController": lambda: (
                self.delay,
                [self.proposer],
                [self.executor],
                ZERO,
            ),
            "CommunityRegistry": lambda: (
                self.contracts["TimelockController"].address,
            ),
            "SUNToken": lambda: (self.contracts["TimelockController"].address,) * 2,
            "CommunitySettlement": lambda: (
                self.contracts["CommunityRegistry"].address,
                self.contracts["SUNToken"].address,
                self.contracts["TimelockController"].address,
                self.challenge,
                self.cid,
            ),
            "NativeSettlementVault": lambda: (
                self.contracts["CommunityRegistry"].address,
                self.contracts["CommunitySettlement"].address,
                self.contracts["SUNToken"].address,
            ),
        }
        for name in NAMES:
            artifact = self.artifacts[name]
            entry = self.journal["contracts"].get(name)
            if entry is None:
                pending = self.journal.get("pending", {}).get(name)
                self.pending_name = name
                try:
                    receipt = (
                        self.wait(pending)
                        if pending
                        else self.send(
                            self.web3.eth.contract(
                                abi=artifact["abi"],
                                bytecode=artifact["bytecode"]["object"],
                            ).constructor(*arguments[name]())
                        )
                    )
                finally:
                    self.pending_name = None
                self.journal.get("pending", {}).pop(name, None)
                entry = {
                    "address": receipt.contractAddress,
                    "transaction_hash": Web3.to_hex(receipt.transactionHash),
                    "block_number": receipt.blockNumber,
                    "block_hash": Web3.to_hex(receipt.blockHash),
                }
                self.journal["contracts"][name] = entry
                save_json(self.path, self.journal)
            self.contracts[name] = self.web3.eth.contract(
                address=entry["address"], abi=artifact["abi"]
            )
        return self.contracts

    def govern(self, function):
        """Explicit local demo authority only. Public governance uses a reviewable plan."""
        if self.web3.eth.chain_id not in (31337, 1337) or self.delay:
            raise ValueError(
                "Automatic governance is restricted to the local zero-delay demo"
            )
        governor = self.contracts["TimelockController"]
        data = function._encode_transaction_data()
        salt = Web3.keccak(text=f"{function.address}:{data}")
        operation = governor.functions.hashOperation(
            function.address, 0, data, bytes(32), salt
        ).call()
        if governor.functions.isOperationDone(operation).call():
            return None
        if not governor.functions.isOperationPending(operation).call():
            self.send(
                governor.functions.schedule(
                    function.address, 0, data, bytes(32), salt, 0
                )
            )
        receipt = self.send(
            governor.functions.execute(function.address, 0, data, bytes(32), salt)
        )
        self.journal["transactions"].append(
            {
                "action": function.fn_name,
                "transaction_hash": Web3.to_hex(receipt.transactionHash),
                "block_number": receipt.blockNumber,
            }
        )
        save_json(self.path, self.journal)
        return receipt

    def setup_calls(self):
        c = self.contracts
        registry, sun, settlement, vault = [c[x] for x in NAMES[1:]]
        governor = c["TimelockController"]
        return [
            settlement.functions.bindVault(vault.address),
            registry.functions.bindProtocol(
                self.cid, settlement.address, vault.address, sun.address
            ),
            sun.functions.grantRole(
                sun.functions.MINTER_ROLE().call(), settlement.address
            ),
            sun.functions.revokeRole(
                sun.functions.MINTER_ROLE().call(), governor.address
            ),
            registry.functions.grantRole(
                registry.functions.ORACLE_ROLE().call(), self.oracle
            ),
            registry.functions.grantRole(
                registry.functions.SETTLEMENT_ROLE().call(), self.oracle
            ),
        ]

    def governance_plan(self):
        governor = self.contracts["TimelockController"]
        result = []
        for fn in self.setup_calls():
            data = fn._encode_transaction_data()
            salt = Web3.keccak(text=f"{fn.address}:{data}")
            result.append(
                {
                    "action": fn.fn_name,
                    "target": fn.address,
                    "value": "0",
                    "data": data,
                    "predecessor": Web3.to_hex(bytes(32)),
                    "salt": Web3.to_hex(salt),
                    "operation_id": Web3.to_hex(
                        governor.functions.hashOperation(
                            fn.address, 0, data, bytes(32), salt
                        ).call()
                    ),
                    "schedule_data": governor.functions.schedule(
                        fn.address, 0, data, bytes(32), salt, self.delay
                    )._encode_transaction_data(),
                    "execute_data": governor.functions.execute(
                        fn.address, 0, data, bytes(32), salt
                    )._encode_transaction_data(),
                }
            )
        return {
            "timelock": governor.address,
            "delay_seconds": self.delay,
            "calls": result,
            "notice": "Deployment does not activate a community. Review and execute setup through authorized governance after proposing and approving the community.",
        }
