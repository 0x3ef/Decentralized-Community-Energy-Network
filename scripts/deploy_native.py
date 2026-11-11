"""Native protocol deployment. Sepolia broadcasts require explicit secure settings.

No key or authenticated RPC URL is printed or written to the public journal.
"""

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from eth_account import Account
from src.protocol.deployment import Deployment, artifacts_at, save_json
from web3 import Web3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("community_id", type=UUID)
    parser.add_argument("--network", choices=["local", "sepolia"], default="sepolia")
    parser.add_argument(
        "--broadcast",
        action="store_true",
        help="Submit real deployment transactions after preflight",
    )
    parser.add_argument(
        "--output", type=Path, default=Path(".run/sepolia/deployment.json")
    )
    parser.add_argument("--artifacts", type=Path, default=Path("contracts/out"))
    args = parser.parse_args()
    url = os.environ.get(
        "SEPOLIA_RPC_URL" if args.network == "sepolia" else "WEB3_PROVIDER_URL", ""
    )
    key = os.environ.get(
        "SEPOLIA_DEPLOYER_PRIVATE_KEY"
        if args.network == "sepolia"
        else "DEPLOYER_PRIVATE_KEY",
        "",
    )
    names = [
        "GOVERNANCE_PROPOSER_ADDRESS",
        "GOVERNANCE_EXECUTOR_ADDRESS",
        "ORACLE_ADDRESS",
    ]
    addresses = [os.environ.get(name, "") for name in names]
    if not url or not key or not all(addresses):
        parser.error(
            "Configure RPC, deployer key and explicit proposer, executor, oracle addresses securely in the environment; never paste keys into chat"
        )
    web3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 15}))
    expected = 11155111 if args.network == "sepolia" else 31337
    if web3.eth.chain_id != expected:
        raise SystemExit(f"RPC chain mismatch; expected {expected}")
    account = Account.from_key(key)
    if addresses[2].lower() in {account.address.lower(), addresses[0].lower(), addresses[1].lower()}:
        raise SystemExit(
            "Deployer/governance and backend oracle must be distinct accounts"
        )
    artifact = artifacts_at(args.artifacts)
    delay = 86400 if args.network == "sepolia" else 0
    confirmations = 3 if args.network == "sepolia" else 1
    deployment = Deployment(
        web3,
        artifact,
        args.output,
        args.community_id,
        account.address,
        *addresses,
        private_key=key,
        delay=delay,
        challenge=max(1, delay),
        confirmations=confirmations,
    )
    balance = web3.eth.get_balance(account.address)
    # Conservative public preflight bound, not a quote or an automatic faucet.
    estimate = 15_000_000 * max(web3.eth.gas_price, 1)
    if balance < estimate:
        raise SystemExit(
            "Deployer needs test ETH for gas; use an external faucet/account transfer, then rerun preflight"
        )
    print(
        json.dumps(
            {
                "status": "PREFLIGHT_OK",
                "chain_id": expected,
                "deployer": account.address,
                "balance_wei": str(balance),
                "minimum_gas_budget_wei": str(estimate),
                "broadcast": args.broadcast,
            }
        )
    )
    if not args.broadcast:
        return
    deployment.deploy()
    save_json(
        args.output.with_name("governance-plan.json"), deployment.governance_plan()
    )
    print(
        json.dumps(
            {
                "status": "DEPLOYMENT_CONFIRMED",
                "journal": str(args.output),
                "governance_plan": str(args.output.with_name("governance-plan.json")),
                "notice": "Contracts deployed; governance setup and community activation remain explicit separate operations.",
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Provider exception strings can expose authenticated URLs or signed data.
        raise SystemExit(
            f"Deployment stopped ({type(error).__name__}); inspect the public journal and secure RPC configuration. No successful deployment is claimed."
        ) from None
