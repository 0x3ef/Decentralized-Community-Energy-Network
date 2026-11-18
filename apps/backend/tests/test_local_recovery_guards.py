"""Compatibility repair preflight preserves existing private settings."""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def bootstrap_wrapper(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "local_bootstrap_wrapper", root / "scripts/bootstrap_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["bootstrap_demo.py", "--recommission"])

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected repair reached Docker")

    monkeypatch.setattr(module.subprocess, "run", forbidden)
    path = tmp_path / "infrastructure/docker/.env"
    path.parent.mkdir(parents=True)
    return module, path


def test_repair_accepts_omitted_local_defaults_without_changing_file(bootstrap_wrapper):
    from src.core.config import Settings

    module, path = bootstrap_wrapper
    path.write_text("# Existing private configuration with optional fields omitted\n")
    before = path.read_bytes()
    assert Settings.model_fields["ENVIRONMENT"].default == "development"
    assert Settings.model_fields["CHAIN_ID"].default == 31337
    module.validate_repair_environment(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "body,field",
    [
        ("ENVIRONMENT=testnet\nCHAIN_ID=11155111\n", "ENVIRONMENT"),
        ("ENVIRONMENT=development\nCHAIN_ID=11155111\n", "CHAIN_ID"),
        ("ENVIRONMENT=\nCHAIN_ID=31337\n", "ENVIRONMENT"),
        ("ENVIRONMENT=development\nCHAIN_ID=\n", "CHAIN_ID"),
    ],
)
def test_repair_rejects_public_or_empty_settings_before_docker(
    bootstrap_wrapper, body, field
):
    module, path = bootstrap_wrapper
    path.write_text(body)
    with pytest.raises(SystemExit, match=field):
        module.main()
    assert path.read_text() == body


def test_repair_requires_existing_private_file(bootstrap_wrapper):
    module, path = bootstrap_wrapper
    with pytest.raises(SystemExit, match="Restore the original"):
        module.main()
    assert not path.exists()
