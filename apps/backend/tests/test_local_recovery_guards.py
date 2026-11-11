"""Recovery must refuse public networks and intact deployments before mutation."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "local_demo_recovery", root / "scripts/recover_local_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env = tmp_path / "private.env"
    monkeypatch.setattr(module, "ENV_FILE", env)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["recover_local_demo.py", "--new-demo"])
    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DEMO_RPC_URL", raising=False)

    # No guard rejection may reach Docker, backup creation or credential rotation.
    def forbidden(*args, **kwargs):
        pytest.fail("Recovery mutated infrastructure before passing its safety guards")

    monkeypatch.setattr(module, "call", forbidden)
    return module, env


def test_recovery_refuses_public_configuration(recovery):
    module, env = recovery
    env.write_text("ENVIRONMENT=testnet\nCHAIN_ID=11155111\n")
    with pytest.raises(module.RecoveryGuardError, match="development Anvil"):
        module.main()


def test_recovery_refuses_public_rpc_endpoint(recovery, monkeypatch):
    module, env = recovery
    env.write_text("ENVIRONMENT=development\nCHAIN_ID=31337\n")
    monkeypatch.setenv("DEMO_RPC_URL", "https://public-rpc.example.invalid")
    with pytest.raises(module.RecoveryGuardError, match="loopback"):
        module.main()


def test_recovery_preserves_an_intact_registry(recovery, monkeypatch):
    module, env = recovery
    env.write_text("ENVIRONMENT=development\nCHAIN_ID=31337\n")
    directory = module.ROOT / ".run/demo"
    directory.mkdir(parents=True)
    (directory / "demo.json").write_text('{"registry":"existing-contract"}')

    class LocalWeb3:
        HTTPProvider = staticmethod(lambda *args, **kwargs: None)

        def __init__(self, provider):
            self.eth = SimpleNamespace(chain_id=31337, get_code=lambda address: b"code")

    monkeypatch.setattr(module, "Web3", LocalWeb3)
    with pytest.raises(module.RecoveryGuardError, match="Registry still exists"):
        module.main()
    assert not list(module.ROOT.glob(".run/recovery-*"))


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
