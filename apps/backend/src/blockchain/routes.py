"""Read-only API endpoints for network and SUN token information."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from web3 import Web3

from src.blockchain.service import BlockchainService

blockchain_router = APIRouter(prefix="/blockchain", tags=["Blockchain"])
service = BlockchainService()


@blockchain_router.get("/network")
async def network_info():
    try:
        return service.network_info()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Blockchain RPC is unavailable",
        ) from exc


@blockchain_router.get("/token/balance/{address}")
async def token_balance(address: str):
    try:
        checksum = Web3.to_checksum_address(address)
        return {"address": checksum, "balance_sun": str(service.token_balance(checksum))}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid wallet address") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="SUN contract is unavailable") from exc


@blockchain_router.get("/token/supply")
async def token_supply():
    try:
        return {"total_supply_sun": str(service.total_supply())}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="SUN contract is unavailable") from exc
