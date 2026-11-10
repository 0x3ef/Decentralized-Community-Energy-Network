"""Tests for the Settings model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import PublisherKind, Settings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTERVAL_SECONDS", raising=False)
    settings = Settings()
    assert settings.interval_seconds == 15.0
    assert settings.random_seed is None
    assert settings.sequence_offset is None
    assert settings.publisher == PublisherKind.MQTT


def test_settings_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVAL_SECONDS", "5")
    monkeypatch.setenv("PUBLISHER", "console")
    settings = Settings()
    assert settings.interval_seconds == 5.0
    assert settings.publisher == PublisherKind.CONSOLE


def test_settings_invalid_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERVAL_SECONDS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_random_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RANDOM_SEED", "42")
    assert Settings().random_seed == 42


def test_settings_sequence_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEQUENCE_OFFSET", "100")
    assert Settings().sequence_offset == 100
