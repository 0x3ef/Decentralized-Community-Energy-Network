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
