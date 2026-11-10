"""Publish an authenticated cumulative smart-meter sample to the local broker.

DEVICE_CREDENTIAL is required and never printed. Use registered UUID identities.
Counter values are kWh; publish a baseline followed by interval-aligned readings.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
import paho.mqtt.client as mqtt

parser = argparse.ArgumentParser()
parser.add_argument("--device-id", type=UUID, required=True)
parser.add_argument("--home-id", type=UUID, required=True)
parser.add_argument("--sequence", type=int, required=True)
parser.add_argument("--measured-at", type=datetime.fromisoformat, required=True)
for field in ("export", "import", "consumption"):
    parser.add_argument("--" + field, dest=field + "_kwh", type=Decimal, required=True)
parser.add_argument("--host", default="127.0.0.1")
args = parser.parse_args()
if (
    args.measured_at.tzinfo is None
    or args.sequence < 0
    or any(getattr(args, k + "_kwh") < 0 for k in ("export", "import", "consumption"))
):
    parser.error(
        "Use UTC-aware timestamps, nonnegative sequence and cumulative counters"
    )
credential = os.environ.get("DEVICE_CREDENTIAL")
if not credential or len(credential) < 32:
    parser.error("Set DEVICE_CREDENTIAL to the registered device credential")
payload = {
    "schema_version": "1.0",
    "device_id": str(args.device_id),
    "home_id": str(args.home_id),
    "sensor_type": "smart_meter",
    "sequence_number": args.sequence,
    "measured_at": args.measured_at.astimezone(timezone.utc).isoformat(),
    "credential": credential,
    "data": {
        "grid_export_energy_kwh": str(args.export_kwh),
        "grid_import_energy_kwh": str(args.import_kwh),
        "consumption_energy_kwh": str(args.consumption_kwh),
    },
}
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(args.host, 1883)
client.loop_start()
try:
    result = client.publish(
        f"solar/{args.home_id}/{args.device_id}/telemetry", json.dumps(payload), qos=1
    )
    result.wait_for_publish(timeout=10)
    if not result.is_published():
        raise RuntimeError("Broker acknowledgement timed out")
finally:
    client.disconnect()
    client.loop_stop()
print("Broker acknowledged the sample; query telemetry history for acceptance status.")
