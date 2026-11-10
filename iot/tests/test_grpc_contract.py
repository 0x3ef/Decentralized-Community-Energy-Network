"""Unit tests for the generated protobuf/gRPC contract."""

from grpc_client import sensor_pb2, sensor_pb2_grpc


def test_generated_modules_are_importable() -> None:
    """CI must generate both protobuf modules before collecting tests."""
    request = sensor_pb2.SmartMeterSensorRequest(
        device_id="SM-UNIT-001",
        home_id="HOME-UNIT-001",
        sequence=7,
    )

    assert request.device_id == "SM-UNIT-001"
    assert request.sequence == 7
    assert hasattr(
        sensor_pb2_grpc, "SmartMeterSensorServiceServicer"
    )


def test_proto_round_trip_preserves_nested_measurements() -> None:
    """Nested sensor measurements must survive protobuf serialization."""
    original = sensor_pb2.WeatherSensorRequest(
        device_id="WS-UNIT-001",
        measurements=sensor_pb2.WeatherMeasurements(
            irradiance_w_m2=812.5,
            ambient_temperature_c=27.25,
        ),
    )

    decoded = sensor_pb2.WeatherSensorRequest.FromString(
        original.SerializeToString()
    )

    assert decoded.measurements.irradiance_w_m2 == 812.5
    assert decoded.measurements.ambient_temperature_c == 27.25
