"""Exercise the real CLI wiring as well as continuous-loop configuration."""

import os
import subprocess
import sys
from pathlib import Path


def test_module_starts_and_generates_telemetry(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "simulator.main"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "USE_GRPC": "false",
            "PUBLISHER": "console",
            "DEVICE_REGISTRY": "",
            "HOME_CATALOGUE_FILE": "",
            "CHECKPOINT_PATH": "",
            "SIMULATION_MODE": "REALTIME",
            "SIMULATION_SPEED": "1",
            "SIMULATION_START": "",
            "FAULT_SCENARIO": "none",
            "INTERVAL_SECONDS": "15",
            "ACCOUNTING_INTERVAL_SECONDS": "60",
            "MAX_CYCLES": "1",
            "LOG_LEVEL": "INFO",
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "Generated telemetry:" in result.stderr
    assert '"source": "SIMULATED"' in result.stderr
    assert "Shutting down multi-home IoT simulator" in result.stdout


def test_main_passes_accounting_interval_to_continuous_simulator(monkeypatch):
    from config.settings import Settings
    from simulator import main as entrypoint

    monkeypatch.setattr(
        entrypoint,
        "Settings",
        lambda: Settings(
            _env_file=None,
            use_grpc=False,
            publisher="console",
            device_registry=None,
            home_catalogue_file=None,
            checkpoint_path=None,
            max_cycles=None,
            simulation_mode="REALTIME",
            simulation_speed=1,
            simulation_start=None,
            fault_scenario="none",
            accounting_interval_seconds=60,
        ),
    )
    seen = []
    monkeypatch.setattr(
        entrypoint.Simulator,
        "run",
        lambda simulator, stop_event: seen.append(simulator._config),
    )
    entrypoint.main()
    assert len(seen) == 1
    assert seen[0].accounting_interval_seconds == 60
