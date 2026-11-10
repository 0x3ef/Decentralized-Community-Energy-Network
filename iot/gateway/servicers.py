"""gRPC servicers that forward telemetry to MQTT."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from grpc_client import sensor_pb2, sensor_pb2_grpc
from models.sensor import SensorType
from publishers.base import TelemetryPublisher
from schemas.telemetry import TelemetryPayload

logger = logging.getLogger(__name__)


def _envelope(
    home_id: str,
    device_id: str,
    sensor_type: str,
    sequence: int,
    measured_at: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Build the canonical telemetry envelope."""
    if not measured_at:
        measured_at = datetime.now(UTC).isoformat()
    return TelemetryPayload(
        device_id=device_id,
        home_id=home_id,
        sensor_type=SensorType(sensor_type),
        sequence_number=sequence,
        measured_at=datetime.fromisoformat(measured_at),
        data=data,
    ).to_mqtt_payload()


def _topic(home_id: str, device_id: str) -> str:
    return f"solar/{home_id}/{device_id}/telemetry"


class _BaseServicer:
    """Shared logic: publish + return the response message."""

    def __init__(self, publisher: TelemetryPublisher) -> None:
        self._publisher = publisher

    def _publish(self, topic: str, envelope: dict[str, Any]) -> None:
        self._publisher.publish(topic, envelope)
        logger.info(
            "Published %s seq=%d",
            envelope["device_id"],
            envelope["sequence_number"],
        )


class SmartMeterServicer(
    _BaseServicer, sensor_pb2_grpc.SmartMeterSensorServiceServicer  # type: ignore[misc]
):
    """gRPC servicer for smart meters."""

    def SendSmartMeterRequest(  # noqa: N802 (grpc naming)
        self, request: sensor_pb2.SmartMeterSensorRequest, context: Any
    ) -> sensor_pb2.SmartMeterSensorResponse:
        m = request.measurements
        data = {
            "voltage_v": m.voltage_v,
            "current_a": m.current_a,
            "frequency_hz": m.frequency_hz,
            "active_power_w": m.active_power_w,
            "power_factor": m.power_factor,
            "grid_import_power_w": m.grid_import_power_w,
            "grid_export_power_w": m.grid_export_power_w,
            "consumption_energy_kwh": m.consumption_energy_kwh,
            "grid_import_energy_kwh": m.grid_import_energy_kwh,
            "grid_export_energy_kwh": m.grid_export_energy_kwh,
        }
        envelope = _envelope(
            request.home_id, request.device_id, "smart_meter",
            request.sequence, request.timestamp, data,
        )
        self._publish(_topic(request.home_id, request.device_id), envelope)
        return sensor_pb2.SmartMeterSensorResponse(status="OK")


class SolarInverterServicer(
    _BaseServicer, sensor_pb2_grpc.SolarInverterSensorServiceServicer  # type: ignore[misc]
):
    """gRPC servicer for solar inverters."""

    def SendSolarInverterRequest(  # noqa: N802
        self, request: sensor_pb2.SolarInverterSensorRequest, context: Any
    ) -> sensor_pb2.SolarInverterSensorResponse:
        m = request.measurements
        data = {
            "dc_power_w": m.dc_power_w,
            "ac_power_w": m.ac_power_w,
            "daily_energy_kwh": m.daily_energy_kwh,
            "lifetime_energy_kwh": m.lifetime_energy_kwh,
            "temperature_c": m.temperature_c,
            "efficiency_pct": m.efficiency_pct,
            "operating_state": request.status.operating_state,
            "alarm_code": request.status.alarm_code,
        }
        envelope = _envelope(
            request.home_id, request.device_id, "solar_inverter",
            request.sequence, request.timestamp, data,
        )
        logger.info("Telemetry received from sensor: %s %s", request, _topic(request.home_id, request.device_id))
        self._publish(_topic(request.home_id, request.device_id), envelope)
        return sensor_pb2.SolarInverterSensorResponse(status="OK")


class WeatherServicer(
    _BaseServicer, sensor_pb2_grpc.WeatherSensorServiceServicer  # type: ignore[misc]
):
    """gRPC servicer for weather stations."""

    def SendWeatherRequest(  # noqa: N802
        self, request: sensor_pb2.WeatherSensorRequest, context: Any
    ) -> sensor_pb2.WeatherSensorResponse:
        m = request.measurements
        data = {
            "irradiance_w_m2": m.irradiance_w_m2,
            "ambient_temperature_c": m.ambient_temperature_c,
            "panel_temperature_c": m.panel_temperature_c,
            "relative_humidity_pct": m.relative_humidity_pct,
            "wind_speed_m_s": m.wind_speed_m_s,
        }
        envelope = _envelope(
            request.home_id, request.device_id, "weather_sensor",
            request.sequence, request.timestamp, data,
        )
        logger.info("Telemetry received from sensor: %s %s", request, _topic(request.home_id, request.device_id))
        self._publish(_topic(request.home_id, request.device_id), envelope)
        return sensor_pb2.WeatherSensorResponse(status="OK")


class BatteryMonitorServicer(
    _BaseServicer, sensor_pb2_grpc.BatteryMonitorSensorServiceServicer  # type: ignore[misc]
):
    """gRPC servicer for battery monitors."""

    def SendBatteryMonitorRequest(  # noqa: N802
        self, request: sensor_pb2.BatteryMonitorSensorRequest, context: Any
    ) -> sensor_pb2.BatteryMonitorSensorResponse:
        m = request.measurements
        data = {
            "state_of_charge_pct": m.state_of_charge_pct,
            "battery_voltage_v": m.battery_voltage_v,
            "battery_current_a": m.battery_current_a,
            "charge_power_w": m.charge_power_w,
            "discharge_power_w": m.discharge_power_w,
            "temperature_c": m.temperature_c,
            "available_energy_kwh": m.available_energy_kwh,
            "status": request.status,
        }
        envelope = _envelope(
            request.home_id, request.device_id, "battery_monitor",
            request.sequence, request.timestamp, data,
        )
        logger.info("Telemetry received from sensor: %s %s", request, _topic(request.home_id, request.device_id))
        self._publish(_topic(request.home_id, request.device_id), envelope)
        return sensor_pb2.BatteryMonitorSensorResponse(details="OK")
