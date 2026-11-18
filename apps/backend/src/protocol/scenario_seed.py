"""Append local scenario telemetry through the real SQLModel ingestion pipeline."""

import asyncio
import json
import sys
from datetime import datetime
from uuid import UUID

from sqlmodel import or_, select
from web3 import Web3

from src.core.config import Config
from src.core.db import AsyncSessionFactory, dispose_engine
from src.iot.mqtt_handler import _insert_batch
from src.iot.telemetry_validator import validate_envelope
from src.modules.device.models import Device, TelemetryMessage


async def insert_scenario(session, messages):
    """Caller owns the transaction. Refuse conflicting or superseded evidence."""
    if Config.ENVIRONMENT != "development" or Config.CHAIN_ID not in (31337, 1337):
        raise ValueError("Scenario insertion is restricted to local development")
    chain = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL))
    if chain.eth.chain_id != Config.CHAIN_ID:
        raise ValueError("Configured and connected local chains differ")
    if not messages or any(m.get("source") != "SIMULATED" for m in messages):
        raise ValueError("Only explicitly simulated scenario evidence is accepted")
    start = min(datetime.fromisoformat(m["measured_at"]) for m in messages)
    ids = {UUID(m["message_id"]) for m in messages}
    for message in messages:
        device = await session.scalar(
            select(Device).where(Device.device_id == UUID(message["device_id"]))
        )
        if not device:
            raise ValueError("Commission the registered scenario meters first")
        # A retry may encounter its own committed readings. Other later readings
        # indicate that this fixture would rewind counters or rewrite history.
        conflict = await session.scalar(
            select(TelemetryMessage.id)
            .where(
                TelemetryMessage.device_id == device.id,
                TelemetryMessage.measured_at >= start,
                or_(
                    TelemetryMessage.message_id.is_(None),
                    TelemetryMessage.message_id.not_in(ids),
                ),
            )
            .limit(1)
        )
        if conflict:
            raise ValueError(
                "Scenario meters already have later evidence; no rows changed"
            )
    inserted, duplicates = await _insert_batch(session, messages)
    if inserted + duplicates != len(messages):
        raise ValueError(
            "Scenario telemetry failed authentication; transaction rolled back"
        )
    for message in messages:
        row = await session.scalar(
            select(TelemetryMessage)
            .join(Device)
            .where(
                Device.device_id == UUID(message["device_id"]),
                TelemetryMessage.message_id == UUID(message["message_id"]),
            )
        )
        envelope, errors = validate_envelope(
            {k: v for k, v in message.items() if k != "credential"}
        )
        if (
            errors
            or not envelope
            or not row
            or row.quality_status not in ("valid", "PROCESSED", "COUNTER_GAP")
            or row.payload != json.loads(envelope.model_dump_json())
        ):
            raise ValueError("Conflicting or invalid evidence; transaction rolled back")
    return {"inserted": inserted, "duplicates": duplicates}


async def main():
    try:
        messages = json.load(sys.stdin)
        async with AsyncSessionFactory() as session, session.begin():
            result = await insert_scenario(session, messages)
        print(json.dumps(result))
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
