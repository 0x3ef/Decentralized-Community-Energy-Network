"""Credential-free evidence audit and server-owned simulation eligibility."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert

from src.core.config import Config
from src.modules.device.models import TelemetryAssessment


def digest(raw):
    safe = {
        k: v for k, v in raw.items() if k != "credential" and not k.startswith("_mqtt_")
    }
    return hashlib.sha256(
        json.dumps(safe, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def assess(session, raw, state, reason, device_id=None, count=1):
    payload_hash = raw.get("_payload_hash") or digest(raw)
    fingerprint = hashlib.sha256(
        f"{payload_hash}:{state}:{reason}:{device_id}".encode()
    ).hexdigest()
    sequence = raw.get("sequence_number")
    sequence = sequence if isinstance(sequence, int) and 0 <= sequence < 2**63 else None
    now = datetime.now(UTC)
    stmt = insert(TelemetryAssessment).values(
        id=uuid4(),
        fingerprint=fingerprint,
        device_id=device_id,
        claimed_device_id=str(raw.get("device_id", ""))[:100],
        sequence_number=sequence,
        payload_hash=payload_hash,
        state=state,
        reason=reason[:300],
        occurrences=count,
        first_seen=now,
        last_seen=now,
    )
    await session.exec(
        stmt.on_conflict_do_update(
            index_elements=["fingerprint"],
            set_={
                "occurrences": TelemetryAssessment.occurrences + count,
                "last_seen": now,
            },
        )
    )


def source_error(device, community, envelope, chain_id=None):
    if device.telemetry_source not in ("PHYSICAL", "SIMULATED"):
        return "Device source requires commissioning review"
    if envelope.source and envelope.source != device.telemetry_source:
        return "Publisher source differs from commissioned device source"
    if envelope.simulation_mode != "REALTIME":
        return "Offline simulation is audit-only, never settlement evidence"
    if envelope.quality and any(flag != "VALID" for flag in envelope.quality):
        return "Publisher reported unresolved measurement quality"
    if device.telemetry_source == "SIMULATED" and (
        not community.allow_simulated_telemetry
        or (chain_id if chain_id is not None else Config.CHAIN_ID) not in (31337, 1337)
    ):
        return "Simulated telemetry requires an opted-in local Anvil community"
    return None


async def quarantine(session, device, envelope):
    """Hold future accounting on authenticated conflicting evidence; never undo money."""
    from sqlmodel import select

    from src.modules.energy.models import EnergyCredit, EnergyInterval

    intervals = (
        await session.exec(
            select(EnergyInterval).where(
                EnergyInterval.home_id == device.home_id,
                EnergyInterval.interval_start <= envelope.measured_at,
                EnergyInterval.interval_end >= envelope.measured_at,
            )
        )
    ).all()
    for interval in intervals:
        interval.quality_status = "DISPUTED"
        for credit in (
            await session.exec(
                select(EnergyCredit).where(
                    EnergyCredit.interval_id == interval.id,
                    EnergyCredit.status.in_(["PENDING", "APPROVED"]),
                )
            )
        ).all():
            credit.status = "REJECTED"
