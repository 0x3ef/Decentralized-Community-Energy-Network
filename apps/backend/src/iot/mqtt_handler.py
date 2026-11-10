"""MQTT → PostgreSQL ingest worker.

Threading model:

* ``paho-mqtt`` runs its network loop in a background thread
  (``loop_start``). Its ``on_message`` callback runs in that thread.
* The main thread is an asyncio event loop. The callback pushes each
  message into an ``asyncio.Queue`` via ``loop.call_soon_threadsafe``.
* A background asyncio task drains the queue in batches and writes
  them in a single transaction per batch.

This keeps ``on_message`` non-blocking and avoids stalling the MQTT
network loop when the database is slow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import paho.mqtt.client as mqtt
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import AsyncSessionFactory, dispose_engine
from src.core.config import Config

from src.modules.device.models import (
    Device,
    SmartMeter,
    Inverter,
    WeatherSensor,
    BatteryMonitor,
    TelemetryMessage
)

from src.iot.telemetry_validator import Envelope, validate_envelope

logger = logging.getLogger("ingest")


class MqttIngestWorker:
    """Bridge between Mosquitto and PostgreSQL."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=Config.QUEUE_MAXSIZE
        )
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        self._session_factory = AsyncSessionFactory

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=Config.MQTT_CLIENT_ID
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # ------------------------------------------------------------------
    # MQTT callbacks (network thread)
    # ------------------------------------------------------------------
    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: int,
        properties: Any = None,
    ) -> None:
        if rc != 0:
            logger.error("MQTT connect failed (rc=%s)", rc)
            return
        logger.info(
            "Connected to %s, subscribing to %s (qos=%d)",
            Config.MQTT_HOST,
            Config.MQTT_TOPIC,
            Config.MQTT_QOS,
        )
        client.subscribe(Config.MQTT_TOPIC, qos=Config.MQTT_QOS)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: int,
        properties: Any = None,
    ) -> None:
        logger.warning("MQTT disconnected (rc=%s)", rc)

    def _on_message(
        self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage
    ) -> None:
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.exception("Malformed JSON on %s", msg.topic)
            return
        self._loop.call_soon_threadsafe(self._enqueue, payload)

    def _enqueue(self, payload: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.error(
                "Ingest queue full (max=%d); dropping message",
                self._queue.maxsize,
            )

    # ------------------------------------------------------------------
    # Async side
    # ------------------------------------------------------------------
    async def _drain_loop(self) -> None:
        while not self._stop.is_set():
            batch = await self._collect_batch()
            if batch:
                await self._persist(batch)

    async def _collect_batch(self) -> list[dict[str, Any]]:
        try:
            first = await asyncio.wait_for(
                self._queue.get(),
                timeout=Config.BATCH_FLUSH_SECONDS,
            )
        except TimeoutError:
            return []

        batch = [first]
        while len(batch) < Config.BATCH_SIZE:
            try:
                batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    async def _persist(self, batch: list[dict[str, Any]]) -> None:
        try:
            async with self._session_factory() as session:
                inserted, skipped = await _insert_batch(session, batch)
                await session.commit()
            logger.info("Batch persisted: %d inserted, %d skipped", inserted, skipped)
        except Exception:
            logger.exception("Failed to persist batch of %d", len(batch))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def run(self) -> None:
        logger.info(
            "Starting ingest worker (topic=%s, batch=%d, queue=%d)",
            Config.MQTT_TOPIC,
            Config.BATCH_SIZE,
            Config.QUEUE_MAXSIZE,
        )
        self._client.connect(
            Config.MQTT_HOST,
            Config.MQTT_PORT,
            keepalive=60,
        )
        self._client.loop_start()

        drain_task = asyncio.create_task(self._drain_loop())

        try:
            await self._stop.wait()
        finally:
            drain_task.cancel()
            with suppress(asyncio.CancelledError):
                await drain_task
            self._client.loop_stop()
            self._client.disconnect()
            await dispose_engine()
            logger.info("Ingest worker stopped")

    def stop(self) -> None:
        self._stop.set()


# ---------------------------------------------------------------------------
# Batch insertion
# ---------------------------------------------------------------------------
async def _insert_batch(
    session: AsyncSession,
    messages: list[dict[str, Any]],
) -> tuple[int, int]:
    """Insert a batch of raw MQTT messages.

    Returns:
        ``(inserted, skipped)``.
    """
    prepared: list[tuple[Envelope, uuid.UUID, list[dict[str, Any]]]] = []
    for raw in messages:
        envelope, errors = validate_envelope(raw)
        if envelope is None:
            logger.warning("Dropping malformed envelope: %s", errors)
            continue
        try:
            device_uuid = await _resolve_device_id(session, envelope)
        except ValueError as exc:
            logger.warning("Skipping message: %s", exc)
            continue
        prepared.append((envelope, device_uuid, errors))

    if not prepared:
        return 0, 0

    rows = [
        {
            "id": uuid.uuid4(),
            "device_id": device_uuid,
            "sequence_number": envelope.sequence_number,
            "schema_version": envelope.schema_version,
            "measured_at": envelope.measured_at,
            "received_at": datetime.now(UTC),
            # Serialize through Pydantic's JSON encoder so Decimal values
            # produced by typed validation never reach PostgreSQL's JSONB
            # serializer as non-JSON-native objects.
            "payload": json.loads(envelope.model_dump_json()),
            "quality_status": "valid" if not errors else "invalid",
            "validation_errors": (
                json.loads(json.dumps(errors, default=str))
                if errors
                else None
            ),
        }
        for envelope, device_uuid, errors in prepared
    ]

    stmt = (
        insert(TelemetryMessage)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["device_id", "sequence_number"])
        .returning(
            TelemetryMessage.id,
            TelemetryMessage.device_id,
            TelemetryMessage.sequence_number,
        )
    )
    result = await session.execute(stmt)
    inserted_rows = result.all()
    inserted_ids = {row.id for row in inserted_rows}

    for envelope, device_uuid, errors in prepared:
        if errors:
            continue
        row_id = next(
            (
                r.id
                for r in inserted_rows
                if r.device_id == device_uuid
                and r.sequence_number == envelope.sequence_number
            ),
            None,
        )
        if row_id is None:
            continue
        await _insert_typed_reading(session, row_id, envelope)

    return len(inserted_ids), len(prepared) - len(inserted_ids)


async def _resolve_device_id(session: AsyncSession, envelope: Envelope) -> uuid.UUID:
    """Return ``devices.id`` for ``envelope.device_id``.

    The device must already exist; the ingest worker does not
    auto-provision devices or homes. Provisioning is a separate admin
    operation, which keeps this worker deterministic and idempotent.
    """
    device = await session.scalar(
        select(Device).where(Device.device_id == uuid.UUID(envelope.device_id))
    )
    if device is None:
        raise ValueError(
            f"Unknown device {envelope.device_id}; register it before sending telemetry"
        )
    if str(device.home_id) != str(uuid.UUID(envelope.home_id)):
        raise ValueError("Telemetry home_id does not match the registered device home")
    device.last_seen_at = datetime.now(UTC)
    return device.id


async def _insert_typed_reading(
    session: AsyncSession, telemetry_id: uuid.UUID, envelope: Envelope
) -> None:
    if envelope.sensor_type == "smart_meter":
        data = envelope.typed_data()
        session.add(
            SmartMeter(
                telemetry_id=telemetry_id,
                voltage_v=data.voltage_v,
                current_a=data.current_a,
                frequency_hz=data.frequency_hz,
                active_power_w=data.active_power_w,
                power_factor=data.power_factor,
                grid_import_power_w=data.grid_import_power_w,
                grid_export_power_w=data.grid_export_power_w,
                cumulative_consumption_wh=_kwh_to_wh(data.consumption_energy_kwh),
                cumulative_import_wh=_kwh_to_wh(data.grid_import_energy_kwh),
                cumulative_export_wh=_kwh_to_wh(data.grid_export_energy_kwh),
            )
        )
    elif envelope.sensor_type == "solar_inverter":
        data = envelope.typed_data()
        session.add(
            Inverter(
                telemetry_id=telemetry_id,
                dc_power_w=data.dc_power_w,
                ac_power_w=data.ac_power_w,
                daily_energy_wh=_kwh_to_wh(data.daily_energy_kwh),
                lifetime_energy_wh=_kwh_to_wh(data.lifetime_energy_kwh),
                temperature_c=data.temperature_c,
                efficiency_pct=data.efficiency_pct,
                operating_state=("on" if data.operating_state else "off")
                if data.operating_state is not None
                else None,
                alarm_code=data.alarm_code,
            )
        )
    elif envelope.sensor_type == "weather_sensor":
        data = envelope.typed_data()
        session.add(
            WeatherSensor(
                telemetry_id=telemetry_id,
                irradiance_w_m2=data.irradiance_w_m2,
                ambient_temperature_c=data.ambient_temperature_c,
                panel_temperature_c=data.panel_temperature_c,
                humidity_pct=data.relative_humidity_pct,
                wind_speed_m_s=data.wind_speed_m_s,
            )
        )
    elif envelope.sensor_type == "battery_monitor":
        data = envelope.typed_data()
        session.add(
            BatteryMonitor(
                telemetry_id=telemetry_id,
                state_of_charge_pct=data.state_of_charge_pct,
                voltage_v=data.battery_voltage_v,
                current_a=data.battery_current_a,
                charge_power_w=data.charge_power_w,
                discharge_power_w=data.discharge_power_w,
                temperature_c=data.temperature_c,
                available_energy_wh=_kwh_to_wh(data.available_energy_kwh),
            )
        )


def _kwh_to_wh(value: float | None) -> int | None:
    if value is None:
        return None
    return round(value * 1000)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def _main() -> None:
    worker = MqttIngestWorker()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, worker.stop)

    await worker.run()


def main() -> None:
    """Blocking entry point used by ``python -m app.iot``."""
    asyncio.run(_main())

if __name__ == "__main__":
    main()