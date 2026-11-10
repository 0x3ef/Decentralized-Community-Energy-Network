"""Tests for the gRPC servicers using an in-process gRPC server."""

from __future__ import annotations

from concurrent import futures

import grpc
import pytest

from gateway.servicers import (
    BatteryMonitorServicer,
    SmartMeterServicer,
    SolarInverterServicer,
    WeatherServicer,
)
from grpc_client import sensor_pb2, sensor_pb2_grpc

pytestmark = pytest.mark.integration


class _RecordingPublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def publish(self, topic: str, message: dict) -> None:
        self.messages.append((topic, message))

    def close(self) -> None:
        pass


@pytest.fixture()
def in_process_server():
    publisher = _RecordingPublisher()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    sensor_pb2_grpc.add_SmartMeterSensorServiceServicer_to_server(
        SmartMeterServicer(publisher), server
    )
    sensor_pb2_grpc.add_SolarInverterSensorServiceServicer_to_server(
        SolarInverterServicer(publisher), server
    )
    sensor_pb2_grpc.add_WeatherSensorServiceServicer_to_server(
        WeatherServicer(publisher), server
    )
    sensor_pb2_grpc.add_BatteryMonitorSensorServiceServicer_to_server(
        BatteryMonitorServicer(publisher), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()

    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    yield channel, publisher

    channel.close()
    server.stop(grace=0).wait()


def test_smart_meter_forwards_to_publisher(in_process_server) -> None:
    channel, publisher = in_process_server
    stub = sensor_pb2_grpc.SmartMeterSensorServiceStub(channel)
    stub.SendSmartMeterRequest(
        sensor_pb2.SmartMeterSensorRequest(
            device_id="SM-1",
            home_id="HOME-1",
            timestamp="2026-01-15T12:00:00+00:00",
            sequence=1,
            measurements=sensor_pb2.SmartMeterMeasurements(
                voltage_v=120.0
            ),
        )
    )
    assert len(publisher.messages) == 1
    topic, message = publisher.messages[0]
    assert topic == "solar/HOME-1/SM-1/telemetry"
    assert message["data"]["voltage_v"] == 120.0


def test_all_services_publish(in_process_server) -> None:
    channel, publisher = in_process_server

    sensor_pb2_grpc.SolarInverterSensorServiceStub(
        channel
    ).SendSolarInverterRequest(
        sensor_pb2.SolarInverterSensorRequest(
            device_id="INV-1",
            home_id="HOME-1",
            timestamp="2026-01-15T12:00:00+00:00",
            sequence=1,
            measurements=sensor_pb2.SolarInverterMeasurements(
                dc_power_w=1000.0
            ),
            status=sensor_pb2.SolarInverterStatus(operating_state=True),
        )
    )
    sensor_pb2_grpc.WeatherSensorServiceStub(channel).SendWeatherRequest(
        sensor_pb2.WeatherSensorRequest(
            device_id="WS-1",
            home_id="HOME-1",
            timestamp="2026-01-15T12:00:00+00:00",
            sequence=1,
            measurements=sensor_pb2.WeatherMeasurements(
                irradiance_w_m2=500.0
            ),
        )
    )
    sensor_pb2_grpc.BatteryMonitorSensorServiceStub(
        channel
    ).SendBatteryMonitorRequest(
        sensor_pb2.BatteryMonitorSensorRequest(
            device_id="BM-1",
            home_id="HOME-1",
            timestamp="2026-01-15T12:00:00+00:00",
            sequence=1,
            measurements=sensor_pb2.BatteryMeasurements(
                state_of_charge_pct=75.0
            ),
            status="OK",
        )
    )
    assert len(publisher.messages) == 3


def test_gateway_defaults_missing_timestamp_to_utc(in_process_server) -> None:
    """A missing producer timestamp still yields a valid envelope."""
    channel, publisher = in_process_server
    stub = sensor_pb2_grpc.SmartMeterSensorServiceStub(channel)

    response = stub.SendSmartMeterRequest(
        sensor_pb2.SmartMeterSensorRequest(
            device_id="SM-DEFAULT-TIME",
            home_id="HOME-1",
            sequence=2,
        )
    )

    assert response.status == "OK"
    assert publisher.messages[0][1]["measured_at"].endswith("+00:00")


def test_gateway_preserves_sequence_and_schema_version(in_process_server) -> None:
    """The gateway must forward idempotency sequence metadata unchanged."""
    channel, publisher = in_process_server
    stub = sensor_pb2_grpc.SmartMeterSensorServiceStub(channel)

    stub.SendSmartMeterRequest(
        sensor_pb2.SmartMeterSensorRequest(
            device_id="SM-SEQUENCE",
            home_id="HOME-1",
            sequence=987,
            timestamp="2026-01-15T12:00:00+00:00",
        )
    )

    envelope = publisher.messages[0][1]
    assert envelope["sequence_number"] == 987
    assert envelope["schema_version"] == "1.0"
