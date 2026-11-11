"""Secret-free service heartbeats and structured operational logging."""

import asyncio
import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlmodel import func, select
from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.core.redis import token_blocklist as redis
from src.modules.auth.dependencies import get_current_user
from web3 import Web3


class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Never serialize exception arguments/tracebacks: SQL and provider errors
        # can contain parameters, signed data or credentials.
        message = record.getMessage()
        try:
            structured = json.loads(message)
        except (ValueError, TypeError):
            structured = None
        if re.search(
            r"(?i)(password|private.key|credential|secret|authorization|access.token|refresh.token|https?://)",
            message,
        ):
            message = "sensitive_log_redacted"
            structured = None
        value = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": message
            if not isinstance(structured, dict)
            else structured.get("event", "log"),
        }
        if isinstance(structured, dict):
            for key in (
                "persisted",
                "duplicates",
                "rejected_before_insert",
                "latency_seconds",
                "queue_depth",
                "duration_ms",
                "community_id",
                "batch_id",
                "code",
            ):
                if key in structured:
                    value[key] = structured[key]
        if record.exc_info:
            value["exception_type"] = record.exc_info[0].__name__
        return json.dumps(value)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=Config.LOG_LEVEL, handlers=[handler], force=True)
    # Libraries must not dump signed transactions, payloads or SQL parameters.
    for name in ("sqlalchemy.engine", "web3", "httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


async def heartbeat(service, ok=True, **metrics):
    value = {"service": service, "ok": bool(ok), "at": time.time(), **metrics}
    try:
        await redis.set(f"solar:heartbeat:{service}", json.dumps(value), ex=90)
    except Exception:
        logging.getLogger(__name__).warning("heartbeat_store_unavailable")


async def service_state(service):
    try:
        raw = await redis.get(f"solar:heartbeat:{service}")
        if not raw:
            return {"state": "missing"}
        value = json.loads(raw)
        age = max(0, time.time() - value["at"])
        return {
            "state": "ready"
            if value["ok"] and age < 30
            else "stale"
            if age >= 30
            else "degraded",
            "age_seconds": round(age, 1),
            **{
                k: v
                for k, v in value.items()
                if k
                in ("persisted", "duplicates", "rejected", "queue_depth", "error_code")
            },
        }
    except Exception:
        return {"state": "unavailable"}


async def readiness():
    components = {}
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        components["database"] = {"state": "ready"}
    except Exception:
        components["database"] = {"state": "unavailable"}
    try:
        await redis.ping()
        components["redis"] = {"state": "ready"}
    except Exception:
        components["redis"] = {"state": "unavailable"}
    try:

        def chain_state():
            web3 = Web3(
                Web3.HTTPProvider(
                    Config.WEB3_PROVIDER_URL, request_kwargs={"timeout": 4}
                )
            )
            chain, height = web3.eth.chain_id, web3.eth.block_number
            return {
                "state": "ready" if chain == Config.CHAIN_ID else "wrong_chain",
                "chain_id": chain,
                "block_number": height,
                "confirmation_blocks": Config.BLOCKCHAIN_CONFIRMATION_BLOCKS,
            }

        components["blockchain"] = await asyncio.to_thread(chain_state)
    except Exception:
        components["blockchain"] = {"state": "unavailable"}
    for service in ("worker", "subscriber"):
        components[service] = await service_state(service)
    healthy = all(value["state"] == "ready" for value in components.values())
    return {"status": "ready" if healthy else "degraded", "components": components}


router = APIRouter()


@router.get("/system/status")
async def system_status(user: Annotated[Any, Depends(get_current_user)]):
    return await readiness()


@router.get("/communities/{community_id}/operations/status")
async def community_status(
    community_id: UUID, user: Annotated[Any, Depends(get_current_user)]
):
    from src.modules.community.models import CommunityNode
    from src.modules.community.service import CommunityService
    from src.modules.device.models import Device, TelemetryAssessment
    from src.modules.energy.models import OutboxEvent
    from src.modules.settlement.models import NativeSyncCursor, SettlementBatch

    async with AsyncSessionFactory() as session:
        await CommunityService().membership(
            session, community_id, user.uid, operator=True
        )
        batches = (
            await session.exec(
                select(SettlementBatch.status, func.count())
                .where(SettlementBatch.community_id == community_id)
                .group_by(SettlementBatch.status)
            )
        ).all()
        jobs = (
            await session.exec(
                select(OutboxEvent.status, func.count())
                .where(OutboxEvent.payload["community_id"].astext == str(community_id))
                .group_by(OutboxEvent.status)
            )
        ).all()
        quality = (
            await session.exec(
                select(
                    TelemetryAssessment.state, func.sum(TelemetryAssessment.occurrences)
                )
                .join(Device, Device.id == TelemetryAssessment.device_id)
                .join(CommunityNode, CommunityNode.home_id == Device.home_id)
                .where(CommunityNode.community_id == community_id)
                .group_by(TelemetryAssessment.state)
            )
        ).all()
        cursor = await session.get(NativeSyncCursor, community_id)
    status = await readiness()
    chain = status["components"]["blockchain"]
    height = chain.get("block_number")
    confirmed = (
        max(0, height - Config.BLOCKCHAIN_CONFIRMATION_BLOCKS + 1)
        if height is not None
        else None
    )
    lag = (
        max(0, confirmed - cursor.block_number)
        if confirmed is not None and cursor
        else None
    )
    return {
        **status,
        "community_id": str(community_id),
        "batches": dict(batches),
        "jobs": dict(jobs),
        "telemetry_quality": dict(quality),
        "indexed_block": cursor.block_number if cursor else None,
        "confirmed_block": confirmed,
        "lag_blocks": lag,
        "alerts": (["FAILED_JOBS"] if dict(jobs).get("FAILED", 0) else [])
        + (
            ["RECONCILIATION_REQUIRED"]
            if dict(batches).get("RECONCILIATION_REQUIRED", 0)
            else []
        )
        + (["INDEX_LAG"] if lag is not None and lag > 100 else []),
    }


async def ready_response():
    status = await readiness()
    return JSONResponse(
        status_code=200 if status["status"] == "ready" else 503, content=status
    )


async def check_service(service):
    state = await service_state(service)
    return state["state"] == "ready"


if __name__ == "__main__":
    import sys

    raise SystemExit(0 if asyncio.run(check_service(sys.argv[1])) else 1)
