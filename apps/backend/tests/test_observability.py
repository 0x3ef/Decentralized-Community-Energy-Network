import json
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from src.core.observability import JsonFormatter, heartbeat, service_state
from src.core.redis import token_blocklist
from src.main import app


def test_structured_logs_do_not_serialize_sensitive_payloads_or_exception_arguments():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        "ingest", logging.ERROR, "", 0, "password=do-not-print", (), None
    )
    assert "do-not-print" not in formatter.format(record)
    record = logging.LogRecord(
        "ingest",
        logging.INFO,
        "",
        0,
        json.dumps(
            {"event": "ingest_batch_committed", "persisted": 4, "credential": "secret"}
        ),
        (),
        None,
    )
    assert "secret" not in formatter.format(record)
    record = logging.LogRecord(
        "worker",
        logging.ERROR,
        "",
        0,
        "iteration_failed",
        (),
        (ValueError, ValueError("private-key-must-not-log"), None),
    )
    output = json.loads(formatter.format(record))
    assert output["exception_type"] == "ValueError" and "private-key" not in str(output)


@pytest.mark.asyncio
async def test_missing_or_unhealthy_workers_are_not_ready():
    await token_blocklist.delete("solar:heartbeat:worker", "solar:heartbeat:subscriber")
    assert (await service_state("worker"))["state"] == "missing"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        result = await client.get("/ready")
        assert result.status_code == 503
    await heartbeat("worker", False, error_code="RECONCILIATION_REQUIRED")
    assert (await service_state("worker"))["state"] == "degraded"
    await token_blocklist.delete("solar:heartbeat:worker", "solar:heartbeat:subscriber")


def test_standalone_ingest_registers_all_sqlmodel_relationships():
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src.iot.mqtt_handler import MqttIngestWorker; from sqlalchemy.orm import configure_mappers; configure_mappers()",
        ],
        capture_output=True,
        text=True,
        env=os.environ,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_invalid_settings_do_not_render_secret_inputs():
    from pydantic import ValidationError
    from src.core.config import Settings

    with pytest.raises(ValidationError) as failure:
        Settings(
            _env_file=None,
            JWT_SECRET="hidden-short-jwt",
            BACKEND_PRIVATE_KEY="hidden-backend-key",
        )
    assert "hidden-short-jwt" not in str(failure.value)
    assert "hidden-backend-key" not in str(failure.value)
