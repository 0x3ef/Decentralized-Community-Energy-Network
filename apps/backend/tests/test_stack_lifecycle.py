"""Lifecycle failures must preserve the project, credentials and database volumes."""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def load(name, relative):
    path = Path(__file__).resolve().parents[3] / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def stack(tmp_path, monkeypatch):
    module = load("stack_lifecycle", "scripts/stack.py")
    instance = module.Stack(tmp_path)
    instance.env.parent.mkdir(parents=True)
    instance.env.write_text(
        "ENVIRONMENT=development\nCHAIN_ID=31337\nCOMPOSE_PROJECT_NAME=original-project\nJWT_SECRET=unchanged\nBACKEND_PRIVATE_KEY=unchanged\nSEED_PASSWORD=unchanged\nSEED_DEVICE_KEY=unchanged\n"
    )
    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    return module, instance


def test_all_commands_share_original_project_and_both_compose_files(stack):
    _, instance = stack
    assert (
        instance.base[instance.base.index("--project-name") + 1] == "original-project"
    )
    assert sum(arg.endswith(".yml") for arg in instance.base) == 2
    assert not any("compose.env" in arg for arg in instance.base)


def test_shell_project_override_is_refused(stack, monkeypatch):
    _, instance = stack
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "different-empty-database")
    with pytest.raises(ValueError, match="original private env"):
        _ = instance.base


def test_existing_volume_without_private_env_does_not_generate_new_credentials(
    stack, monkeypatch
):
    module, instance = stack
    instance.env.unlink()
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0)
    )
    monkeypatch.setattr(
        instance, "run", lambda *a, **kw: pytest.fail("Created replacement credentials")
    )
    with pytest.raises(ValueError, match="original infrastructure"):
        instance.ensure()
    assert not instance.env.exists()


@pytest.mark.parametrize("setting", ["ENVIRONMENT=testnet", "CHAIN_ID=11155111"])
def test_public_network_settings_refused_before_docker_mutation(stack, setting):
    _, instance = stack
    with instance.env.open("a") as output:
        output.write(setting + "\n")
    with pytest.raises(ValueError, match="only for local"):
        instance.ensure()


def test_stale_network_recreates_containers_without_removing_volumes(
    stack, monkeypatch
):
    _, instance = stack
    calls = []

    def compose(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(
                1, args, output="network missing-id not found", stderr=""
            )
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(instance, "compose", compose)
    instance.start(["simulator"], dependencies=False)
    assert len(calls) == 2 and "--force-recreate" in calls[1]
    assert "--no-deps" in calls[1] and "--no-build" in calls[1]
    assert all("down" not in call and "-v" not in call for call in calls)


def test_simulate_starts_full_application_before_simulator(stack, monkeypatch):
    _, instance = stack
    calls = []
    for method in (
        "ensure",
        "artifacts",
        "stop_writers",
        "migrate",
        "configure",
        "checkpoint",
    ):
        monkeypatch.setattr(instance, method, lambda: None)
    monkeypatch.setattr(
        instance, "build", lambda *services: calls.append(("build", services))
    )
    monkeypatch.setattr(
        instance, "start", lambda services, **kw: calls.append(("start", services))
    )
    monkeypatch.setattr(instance, "status", lambda: {"state": "EMPTY"})
    monkeypatch.setattr(
        instance, "backend", lambda module: calls.append(("backend", module))
    )
    instance.up(simulate=True)
    starts = [services for action, services in calls if action == "start"]
    assert starts[-2] == ["api", "worker", "subscriber", "frontend"]
    assert starts[-1] == ["simulator"]


def test_missing_journal_does_not_redeploy_existing_contracts(stack, monkeypatch):
    _, instance = stack
    for method in ("ensure", "artifacts", "stop_writers", "migrate"):
        monkeypatch.setattr(instance, method, lambda: None)
    monkeypatch.setattr(instance, "build", lambda *args: None)
    monkeypatch.setattr(instance, "start", lambda *args, **kwargs: None)
    monkeypatch.setattr(instance, "status", lambda: {"state": "READY"})
    monkeypatch.setattr(
        instance, "backend", lambda *args: pytest.fail("Redeployed a live protocol")
    )
    with pytest.raises(ValueError, match="journal is missing"):
        instance.up(simulate=True)


def test_valid_live_contracts_are_not_reset_by_recovery(stack, monkeypatch):
    _, instance = stack
    for method in ("ensure", "artifacts", "stop_writers", "migrate", "ready"):
        monkeypatch.setattr(instance, method, lambda: None)
    monkeypatch.setattr(instance, "build", lambda *args: None)
    monkeypatch.setattr(instance, "start", lambda *args, **kw: None)
    monkeypatch.setattr(
        instance, "status", lambda: {"state": "READY", "genesis": "intact"}
    )
    monkeypatch.setattr(
        instance, "backup", lambda: pytest.fail("Attempted to replace live protocol")
    )
    monkeypatch.setattr(instance, "up", lambda **kw: None)
    instance.recover()


def test_recovery_starts_valid_stopped_chain_without_replacing_it(stack, monkeypatch):
    _, instance = stack
    for method in ("ensure", "artifacts", "stop_writers", "migrate"):
        monkeypatch.setattr(instance, method, lambda: None)
    monkeypatch.setattr(instance, "build", lambda *args: None)
    states = iter(
        [{"state": "RPC_UNAVAILABLE"}, {"state": "READY", "genesis": "original"}]
    )
    monkeypatch.setattr(instance, "status", lambda: next(states))
    monkeypatch.setattr(
        instance,
        "compose",
        lambda *a, **kw: SimpleNamespace(stdout='{"state":"valid"}'),
    )
    started = []
    monkeypatch.setattr(
        instance, "start", lambda services, **kw: started.append(services)
    )
    monkeypatch.setattr(instance, "up", lambda **kw: None)
    monkeypatch.setattr(
        instance, "backup", lambda: pytest.fail("Replaced a valid stopped chain")
    )
    instance.recover()
    assert ["anvil"] in started


@pytest.fixture
def supervisor(tmp_path, monkeypatch):
    module = load("anvil_supervisor", "infrastructure/docker/anvil_supervisor.py")
    monkeypatch.setattr(module, "STATE", tmp_path)
    return module


def test_invalid_primary_restores_previous_and_retains_corrupt_file(supervisor):
    module = supervisor
    original = b'{"accounts":{},"block":{}}'
    (module.STATE / "anvil.json").write_bytes(b'{"accounts": "truncated')
    (module.STATE / "anvil.previous.json").write_bytes(original)
    assert module.restore_previous()
    assert (module.STATE / "anvil.json").read_bytes() == original
    assert len(list((module.STATE / "archive").glob("*/anvil.invalid.json"))) == 1


def test_two_invalid_checkpoints_never_start_an_empty_chain(supervisor):
    for name in ("anvil.json", "anvil.previous.json"):
        (supervisor.STATE / name).write_text("truncated")
    with pytest.raises(SystemExit, match="make recover"):
        supervisor.restore_previous()
    assert (supervisor.STATE / "anvil.json").read_text() == "truncated"


def test_failed_checkpoint_does_not_replace_last_valid_state(supervisor, monkeypatch):
    import gzip

    original = b'{"accounts":{},"block":{}}'
    (supervisor.STATE / "anvil.json").write_bytes(original)
    monkeypatch.setattr(
        supervisor, "rpc", lambda *args: "0x" + gzip.compress(b"invalid").hex()
    )
    with pytest.raises(ValueError):
        supervisor.checkpoint()
    assert (supervisor.STATE / "anvil.json").read_bytes() == original


def test_atomic_replace_failure_preserves_completed_file(supervisor, monkeypatch):
    target = supervisor.STATE / "anvil.json"
    target.write_text("original")

    def full(*args):
        raise OSError("Disk full")

    monkeypatch.setattr(supervisor.os, "replace", full)
    with pytest.raises(OSError):
        supervisor.atomic_write(target, b"replacement")
    assert target.read_text() == "original"
    assert not list(supervisor.STATE.glob("*.tmp"))


def test_explicit_reset_archives_state_files(supervisor):
    for name in ("anvil.json", "anvil.previous.json", "checkpoint.json"):
        (supervisor.STATE / name).write_text(json.dumps({"retained": name}))
    supervisor.reset()
    assert len(list((supervisor.STATE / "archive").glob("*/*.json"))) == 3
    assert not (supervisor.STATE / "anvil.json").exists()


def test_low_disk_space_keeps_current_checkpoint(supervisor, monkeypatch):
    import gzip

    original = b'{"accounts":{},"block":{}}'
    (supervisor.STATE / "anvil.json").write_bytes(original)
    monkeypatch.setattr(
        supervisor, "rpc", lambda *a: "0x" + gzip.compress(original).hex()
    )
    monkeypatch.setattr(
        supervisor.shutil, "disk_usage", lambda *a: SimpleNamespace(free=0)
    )
    with pytest.raises(OSError, match="Insufficient space"):
        supervisor.checkpoint()
    assert (supervisor.STATE / "anvil.json").read_bytes() == original


def test_snapshot_load_keeps_original_genesis_instead_of_new_restart_headers(
    supervisor,
):
    def block(number, at):
        return {"header": {"number": hex(number), "timestamp": hex(at)}}

    saved, identity = supervisor.normalize_genesis(
        {"blocks": [block(0, 200), block(1, 101), block(0, 100)]}, {}
    )
    assert identity["timestamp"] == 100
    assert saved["blocks"] == [block(1, 101), block(0, 100)]
    saved, unchanged = supervisor.normalize_genesis(
        saved, {"timestamp": 100, "genesis": "original"}
    )
    assert unchanged["genesis"] == "original"


def test_snapshot_without_genesis_is_not_loaded_as_a_different_chain(supervisor):
    with pytest.raises(ValueError, match="no genesis identity"):
        supervisor.normalize_genesis({"blocks": []}, {})


def test_scenario_waits_for_a_complete_post_recovery_interval():
    from datetime import UTC, datetime

    module = load("demo_scenario_intervals", "scripts/demo_scenario.py")
    baseline = {"accounting_start": "2026-11-12T03:00:00+00:00"}
    with pytest.raises(ValueError, match="No complete post-recovery interval"):
        module.new_interval(datetime(2026, 11, 12, 3, 16, tzinfo=UTC), baseline)
    start, end = module.new_interval(
        datetime(2026, 11, 12, 3, 17, tzinfo=UTC), baseline
    )
    assert start.isoformat() == baseline["accounting_start"]
    assert (end - start).total_seconds() == 900


def test_scenario_continues_retained_counters_instead_of_resetting_them():
    from decimal import Decimal

    module = load("demo_scenario_counters", "scripts/demo_scenario.py")
    code = "SM-MS-001-001"
    baseline = {
        "meters": {code: {"grid_export": 5000, "grid_import": 300, "consumption": 900}}
    }
    first = module.counter_data(baseline, code, True, 0)
    last = module.counter_data(baseline, code, True, 1)
    assert Decimal(first["grid_export_energy_kwh"]) == 5
    assert (
        Decimal(last["grid_export_energy_kwh"])
        - Decimal(first["grid_export_energy_kwh"])
        == 5
    )
    assert last["grid_import_energy_kwh"] == first["grid_import_energy_kwh"]


def test_initializer_never_rewrites_existing_credentials(tmp_path, monkeypatch):
    module = load("local_initializer", "scripts/init_local_env.py")
    path = tmp_path / "private.env"
    path.write_text("# Original credentials\nSEED_PASSWORD=unchanged\n")
    monkeypatch.setattr(module, "TARGET", path)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("Initializer reached Docker"),
    )
    module.main()
    assert path.read_text() == "# Original credentials\nSEED_PASSWORD=unchanged\n"


def test_clean_removes_build_artifacts_without_touching_data_or_docker(
    tmp_path, monkeypatch
):
    import sys

    module = load("safe_stack_clean", "scripts/stack.py")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["stack.py", "clean"])
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **kw: pytest.fail("Clean invoked Docker")
    )
    for directory in ("contracts/out", "contracts/cache"):
        (tmp_path / directory).mkdir(parents=True)
        (tmp_path / directory / "compiled").write_text("rebuildable")
    retained = [
        "postgres/records",
        ".run/backups/database.dump",
        ".run/demo/registry.json",
        "contracts/broadcast/receipts.json",
    ]
    for name in retained:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("retain")
    module.main()
    assert not (tmp_path / "contracts/out").exists()
    assert not (tmp_path / "contracts/cache").exists()
    assert all((tmp_path / name).read_text() == "retain" for name in retained)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "environment,chain,actual",
    [
        ("testnet", 11155111, 11155111),
        ("development", 11155111, 31337),
        ("development", 31337, 11155111),
    ],
)
async def test_backend_recovery_refuses_nonlocal_settings_before_sql(
    environment, chain, actual, monkeypatch
):
    from src.core.config import Config
    from src.protocol.local_recovery import recover

    monkeypatch.setattr(Config, "ENVIRONMENT", environment)
    monkeypatch.setattr(Config, "CHAIN_ID", chain)

    def forbidden():
        pytest.fail("Public-chain recovery reached the database")

    with pytest.raises(ValueError, match="development Anvil"):
        await recover(
            forbidden,
            SimpleNamespace(eth=SimpleNamespace(chain_id=actual)),
            {},
            None,
            "",
            "",
        )


@pytest.mark.parametrize("returncode", [0, 1])
def test_database_scenario_uses_original_api_and_keeps_credentials_off_command_line(
    monkeypatch, returncode
):
    import sys

    module = load("database_scenario_transport", "scripts/demo_scenario.py")
    monkeypatch.setitem(
        sys.modules,
        "stack",
        SimpleNamespace(
            Stack=lambda: SimpleNamespace(
                base=["docker", "compose", "original-project"]
            )
        ),
    )
    messages = [{"credential": "private-test-credential"}]

    def execute(command, **kwargs):
        assert command[:3] == ["docker", "compose", "original-project"]
        assert command[3:7] == ["exec", "-T", "api", "python"]
        assert "private-test-credential" not in " ".join(command)
        assert json.loads(kwargs["input"]) == messages
        assert kwargs["capture_output"]
        return SimpleNamespace(
            returncode=returncode,
            stdout='{"inserted": 6, "duplicates": 0}',
            stderr="private-test-credential",
        )

    monkeypatch.setattr(module.subprocess, "run", execute)
    if returncode:
        with pytest.raises(RuntimeError, match="Database seed refused") as error:
            module.insert_database(messages)
        assert "private-test-credential" not in str(error.value)
    else:
        assert module.insert_database(messages) == {"inserted": 6, "duplicates": 0}


def test_container_database_url_preserves_encoded_credentials_database_and_options():
    from sqlalchemy.engine import URL, make_url
    from src.core.docker_database import database_url

    password = "private-test@:/#% password"
    original = URL.create(
        "postgresql+asyncpg",
        username="solar",
        password=password,
        host="localhost",
        port=55432,
        database="retained_database",
        query={"application_name": "existing-worker"},
    )
    adapted = make_url(
        database_url(
            {
                "DATABASE_URL": original.render_as_string(hide_password=False),
                "DATABASE_HOST_OVERRIDE": "timescaledb",
                "DATABASE_PORT_OVERRIDE": "5432",
            }
        )
    )
    assert adapted.password == password
    assert adapted.username == original.username
    assert adapted.database == original.database
    assert adapted.query == original.query
    assert adapted.host == "timescaledb" and adapted.port == 5432


@pytest.mark.parametrize(
    "url", ["private-test-invalid-url", "sqlite:///private-test-secret"]
)
def test_container_database_url_failure_does_not_print_credentials(url):
    from src.core.docker_database import database_url

    with pytest.raises(ValueError) as error:
        database_url({"DATABASE_URL": url, "DATABASE_HOST_OVERRIDE": "timescaledb"})
    assert "private-test" not in str(error.value)


@pytest.mark.parametrize("override", [True, False])
def test_actual_entrypoint_preserves_private_database_password(monkeypatch, override):
    import os
    import sys

    from sqlalchemy.engine import URL

    root = Path(__file__).resolve().parents[3]
    password = "private-test@:/#% password"
    original = URL.create(
        "postgresql+asyncpg",
        username="solar",
        password=password,
        host="localhost",
        port=55432,
        database="retained_database",
    )
    environment = os.environ.copy()
    environment.update(
        DATABASE_URL=original.render_as_string(hide_password=False),
        TEST_EXPECTED_DB_PASSWORD=password,
        PYTHONPATH=str(root / "apps/backend"),
        PATH=str(Path(sys.executable).parent) + os.pathsep + environment["PATH"],
        RUN_MIGRATIONS="false",
    )
    for key in ("DATABASE_HOST_OVERRIDE", "DATABASE_PORT_OVERRIDE"):
        environment.pop(key, None)
    if override:
        environment.update(
            DATABASE_HOST_OVERRIDE="timescaledb", DATABASE_PORT_OVERRIDE="5432"
        )
    check = (
        "import os; from sqlalchemy.engine import make_url; u=make_url(os.environ['DATABASE_URL']); assert u.password == os.environ['TEST_EXPECTED_DB_PASSWORD']; assert u.host == "
        + repr("timescaledb" if override else "localhost")
        + "; assert u.database == 'retained_database'"
    )
    result = subprocess.run(
        ["sh", str(root / "scripts/entry_point.sh"), sys.executable, "-c", check],
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, (
        "Entrypoint failed to preserve original DB credentials"
    )
    assert "private-test" not in result.stdout + result.stderr
