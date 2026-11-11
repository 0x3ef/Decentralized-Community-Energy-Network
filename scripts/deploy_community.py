"""Deploy locally with a dedicated backend authority; never sign for users.

Run from repository root with PYTHONPATH=apps/backend and environment loaded.
Register the resulting public deployment through the authenticated API.
"""

import argparse
import json
from pathlib import Path
from uuid import UUID
from web3 import Web3
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "infrastructure/docker/.env", override=False)
from src.core.config import Config

parser = argparse.ArgumentParser()
parser.add_argument("community_id", type=UUID)
args = parser.parse_args()
web3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL))
if Config.ENVIRONMENT != "development" or web3.eth.chain_id not in (31337, 1337):
    raise SystemExit("This deployment tool is restricted to local development chains")
if not Config.LEGACY_SETTLEMENT_ENABLED:
    raise SystemExit("Legacy deployment is disabled. Use scripts/deploy.sh COMMUNITY_UUID --network sepolia for the native protocol.")
account = web3.eth.account.from_key(Config.BACKEND_PRIVATE_KEY)
web3.provider.make_request("anvil_setBalance", [account.address, hex(10**20)])
root = Path(__file__).resolve().parents[1]


def deploy(name, *arguments):
    artifact = json.loads(
        (root / "contracts" / "out" / f"{name}.sol" / f"{name}.json").read_text()
    )
    factory = web3.eth.contract(
        abi=artifact["abi"], bytecode=artifact["bytecode"]["object"]
    )
    tx = factory.constructor(*arguments).build_transaction(
        {
            "from": account.address,
            "nonce": web3.eth.get_transaction_count(account.address, "pending"),
            "chainId": web3.eth.chain_id,
        }
    )
    signed = account.sign_transaction(tx)
    receipt = web3.eth.wait_for_transaction_receipt(
        web3.eth.send_raw_transaction(signed.raw_transaction)
    )
    if receipt.status != 1:
        raise RuntimeError("Deployment reverted")
    return receipt.contractAddress


sun = deploy("SUNToken", account.address, account.address)
payment = deploy("MockUSD", account.address)
reference = args.community_id.bytes.rjust(32, b"\0")
market = deploy("EnergyMarketplace", sun, payment, reference, account.address)
retirement = deploy("EnergyCompensation", sun, reference, account.address)
print(
    json.dumps(
        {
            "chain_id": web3.eth.chain_id,
            "sun_address": sun,
            "payment_address": payment,
            "marketplace_address": market,
            "compensation_address": retirement,
        },
        indent=2,
    )
)
