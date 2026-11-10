"""Runtime settings loaded from environment variables."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PublisherKind(StrEnum):
    """Supported telemetry sink implementations."""

    CONSOLE = "console"
    MQTT = "mqtt"


class Settings(BaseSettings):
    """Simulator and gateway configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    interval_seconds: float = Field(default=15.0, gt=0)
    checkpoint_path: str | None = None
    device_registry: str | None = None
    home_profiles_json: str = "{}"
    mqtt_tls: bool = False
    mqtt_ca_cert: str | None = None
    mqtt_client_cert: str | None = None
    mqtt_client_key: str | None = None
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    random_seed: int | None = None
    sequence_offset: int | None = None
    use_grpc: bool = True
    gateway_address: str = "gateway:50051"
    log_level: str = "INFO"

    publisher: PublisherKind = PublisherKind.MQTT

    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_client_id: str = "solar-gateway"
    mqtt_qos: int = Field(default=1, ge=0, le=2)

    grpc_port: int = 50051
    grpc_max_workers: int = 8
