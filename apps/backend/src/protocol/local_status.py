"""Machine-readable local deployment inspection, without writes or secrets."""

import asyncio
import json

from sqlmodel import select
from web3 import Web3

from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.modules.community.models import EnergyCommunity, NativeDeployment
from src.modules.settlement.models import LocalChainRecovery
from src.protocol.bootstrap import identifier


async def inspect():
    web3 = Web3(
        Web3.HTTPProvider(Config.WEB3_PROVIDER_URL, request_kwargs={"timeout": 5})
    )
    async with AsyncSessionFactory() as session:
        community = await session.get(EnergyCommunity, identifier("community"))
        native = await session.get(NativeDeployment, identifier("community"))
        try:
            chain = web3.eth.chain_id
            genesis = Web3.to_hex(web3.eth.get_block(0).hash)
        except Exception:
            return {"state": "RPC_UNAVAILABLE"}
        if chain != 31337 or Config.ENVIRONMENT != "development":
            return {"state": "WRONG_NETWORK"}
        pending = (
            await session.exec(
                select(LocalChainRecovery).where(
                    LocalChainRecovery.community_id == identifier("community"),
                    LocalChainRecovery.new_genesis == genesis,
                    LocalChainRecovery.status == "PREPARED",
                )
            )
        ).first()
        if pending:
            return {"state": "RECOVERING", "genesis": genesis}
        if not community and not native:
            return {"state": "EMPTY", "genesis": genesis}
        if not community or not native or not community.registry_address:
            return {"state": "INCOMPLETE_BINDING", "genesis": genesis}
        addresses = [
            community.registry_address,
            native.sun_address,
            native.settlement_address,
            native.vault_address,
        ]
        state = (
            "READY"
            if all(web3.eth.get_code(a) for a in addresses)
            else "MISSING_CONTRACTS"
        )
        return {
            "state": state,
            "genesis": genesis,
            "registry": community.registry_address,
        }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(inspect())))
