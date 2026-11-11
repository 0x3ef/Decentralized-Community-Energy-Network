"""Real local MQTT + HTTP + EVM demonstration, with resumable user action hashes."""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import paho.mqtt.client as mqtt
import requests
from dotenv import load_dotenv
from src.protocol.deployment import Deployment, artifacts_at, save_json
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]


def run():
    load_dotenv(ROOT / "infrastructure/docker/.env", override=False)
    directory = ROOT / ".run/demo"
    demo = json.loads((directory / "demo.json").read_text())
    w3 = Web3(
        Web3.HTTPProvider(os.environ.get("DEMO_RPC_URL", "http://127.0.0.1:8545"))
    )
    if (
        w3.eth.chain_id not in (31337, 1337)
        or os.environ.get("ENVIRONMENT", "development") != "development"
    ):
        raise ValueError("Automated scenario signatures/governance are local-only")
    if w3.eth.chain_id != demo["chain_id"]:
        raise ValueError("Demo chain mismatch")
    base = (
        os.environ.get("DEMO_API_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/v1"
    )
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if (
                requests.get(
                    base.removesuffix("/api/v1") + "/ready", timeout=5
                ).status_code
                == 200
            ):
                break
        except requests.RequestException:
            pass
        time.sleep(0.5)
    else:
        raise TimeoutError("Integrated services are not ready")
    cid = demo["community_id"]
    a, b = demo["members"][:2]
    actors = {}
    for name, member in [("producer", a), ("consumer", b)]:
        client = requests.Session()
        response = client.post(
            base + "/auth/login",
            json={"email": member["email"], "password": os.environ["SEED_PASSWORD"]},
            timeout=10,
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        actors[name] = client

    def api(actor, path, body=None):
        client = actors[actor]
        response = (
            client.get(base + path, timeout=10)
            if body is None
            else client.post(base + path, json=body, timeout=20)
        )
        response.raise_for_status()
        return response.json()

    def wait(read, condition, label):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            value = read()
            if condition(value):
                return value
            time.sleep(0.5)
        raise TimeoutError("Not confirmed: " + label)

    journal_path = directory / "scenario.json"
    if journal_path.exists():
        journal = json.loads(journal_path.read_text())
        if journal["community_id"] != cid:
            raise ValueError("Scenario journal belongs to another community")
    else:
        end = datetime.now(UTC).replace(second=0, microsecond=0)
        end = end.replace(minute=end.minute // 15 * 15) - timedelta(minutes=15)
        journal = {
            "community_id": cid,
            "interval_start": (end - timedelta(minutes=15)).isoformat(),
            "interval_end": end.isoformat(),
            "actions": {},
        }
        save_json(journal_path, journal)

    def transact(actor, action, **body):
        entry = journal["actions"].get(action + ":" + actor)
        if entry is None:
            prepared = api(
                actor, f"/communities/{cid}/native/prepare", {"action": action, **body}
            )
            expected = a["address"] if actor == "producer" else b["address"]
            if (
                prepared["chain_id"] != w3.eth.chain_id
                or prepared["from"].lower() != expected.lower()
            ):
                raise ValueError("Prepared wallet/network mismatch")
            tx = w3.eth.send_transaction(
                {
                    "from": expected,
                    "to": prepared["to"],
                    "data": prepared["data"],
                    "value": int(prepared["value"]),
                }
            )
            entry = {"transaction_hash": Web3.to_hex(tx)}
            journal["actions"][action + ":" + actor] = entry
            save_json(journal_path, journal)
        receipt = w3.eth.wait_for_transaction_receipt(
            entry["transaction_hash"], timeout=60
        )
        if receipt.status != 1:
            raise ValueError(
                "User operation reverted; explicit review required before retry"
            )
        api(
            actor,
            f"/communities/{cid}/native/transactions",
            {"action": action, "transaction_hash": entry["transaction_hash"]},
        )
        wait(
            lambda: api(
                actor, f"/communities/{cid}/native/transactions?limit=100&offset=0"
            ),
            lambda rows: any(
                x["transaction_hash"].lower() == entry["transaction_hash"].lower()
                and x["status"] == "CONFIRMED"
                for x in rows
            ),
            action,
        )
        return entry["transaction_hash"]

    print("Funding consumer deposit with a local test-wallet signature.", flush=True)
    transact("consumer", "deposit", amount_base_units=str(10**16))
    if not journal.get("published"):
        registry = json.loads((directory / "registry.json").read_text())
        bindings = dict(
            line.split("=", 1)
            for line in (directory / "simulator.env").read_text().splitlines()
        )
        publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        publisher.connect(
            os.environ.get("DEMO_MQTT_HOST", "127.0.0.1"),
            int(os.environ.get("DEMO_MQTT_PORT", "1883")),
        )
        publisher.loop_start()
        messages = []
        try:
            for seq, at in enumerate(
                (journal["interval_start"], journal["interval_end"]), 1
            ):
                for index, number in enumerate((1, 2)):
                    entry = registry[f"SM-MS-{number:03d}-001"]
                    f = seq - 1
                    message = {
                        "schema_version": "2.0",
                        "message_id": str(uuid5(NAMESPACE_URL, f"{cid}:{at}:{number}")),
                        "source": "SIMULATED",
                        "simulation_mode": "REALTIME",
                        "sequence_number": int(datetime.fromisoformat(at).timestamp())
                        * 4
                        + seq,
                        "measured_at": at,
                        "units": {
                            key: "kWh"
                            for key in [
                                "grid_export_energy_kwh",
                                "grid_import_energy_kwh",
                                "consumption_energy_kwh",
                            ]
                        },
                        "sensor_type": "smart_meter",
                        "credential": bindings[entry["credential_env"]],
                        **{
                            key: entry[key]
                            for key in [
                                "community_id",
                                "node_id",
                                "home_id",
                                "device_id",
                            ]
                        },
                        "data": {
                            "grid_export_energy_kwh": 5 * f if index == 0 else 0,
                            "grid_import_energy_kwh": 3 * f if index == 1 else 0,
                            "consumption_energy_kwh": 3 * f if index == 1 else 0,
                        },
                    }
                    messages.append(message)
            invalid = {
                **messages[0],
                "credential": "invalid-fixture-credential",
                "message_id": str(uuid5(NAMESPACE_URL, cid + ":invalid")),
            }
            for message in [invalid, *messages, *messages]:
                topic = (
                    f"solar/{cid}/{message['node_id']}/{message['device_id']}/telemetry"
                )
                publisher.publish(topic, json.dumps(message), qos=1).wait_for_publish(
                    timeout=10
                )
        finally:
            publisher.disconnect()
            publisher.loop_stop()
        journal["published"] = True
        save_json(journal_path, journal)
    print(
        "Waiting for authenticated MQTT ingestion, interval calculation and native batch submission.",
        flush=True,
    )

    def batch_list():
        return api("producer", f"/communities/{cid}/settlements?limit=100&offset=0")

    batches = wait(
        batch_list,
        lambda rows: any(
            datetime.fromisoformat(row["interval_start"])
            == datetime.fromisoformat(journal["interval_start"])
            for row in rows
        ),
        "calculation",
    )
    batch = next(
        row
        for row in batches
        if datetime.fromisoformat(row["interval_start"])
        == datetime.fromisoformat(journal["interval_start"])
    )
    assert (
        batch["injection_wh"],
        batch["consumption_wh"],
        batch["allocated_wh"],
        batch["unallocated_wh"],
        batch["total_due_wei"],
    ) == (5000, 3000, 3000, 2000, str(3 * 10**15))
    journal["batch_id"] = batch["id"]
    save_json(journal_path, journal)

    def read_batch():
        return api("producer", f"/communities/{cid}/settlements/{batch['id']}")

    current = wait(
        read_batch,
        lambda row: row["status"] in ("CHALLENGEABLE", "FINALIZED"),
        "submitted batch",
    )
    artifacts = artifacts_at(ROOT / "contracts/out")
    config = json.loads((directory / "deployment.json").read_text())["configuration"]
    deployment = Deployment(
        w3,
        artifacts,
        directory / "deployment.json",
        cid,
        config["deployer"],
        config["proposer"],
        config["executor"],
        config["oracle"],
    )
    contracts = deployment.deploy()
    settlement = contracts["CommunitySettlement"]
    sun = contracts["SUNToken"]
    vault = contracts["NativeSettlementVault"]
    if current["status"] != "FINALIZED":
        print(
            "Approving the reviewed local fixture through its timelock; never done automatically on Sepolia.",
            flush=True,
        )
        time.sleep(2)
        deployment.govern(
            settlement.functions.finalize(Web3.to_bytes(hexstr=batch["chain_batch_id"]))
        )
    wait(
        lambda: api("producer", f"/communities/{cid}/native-wallet"),
        lambda row: (
            int(row["sun_units"]) >= 5 * 10**18
            or "escrow_sun:producer" in journal["actions"]
        ),
        "SUN issuance",
    )
    transact("producer", "approve_sun", amount_base_units=str(5 * 10**18))
    transact("producer", "escrow_sun", amount_base_units=str(5 * 10**18))
    wait(
        lambda: api(
            "producer", f"/communities/{cid}/settlements/{batch['id']}/allocations"
        ),
        lambda rows: rows and all(row["status"] == "SETTLED" for row in rows),
        "atomic delivery and settlement",
    )
    claims = api(
        "consumer",
        f"/communities/{cid}/settlements/{batch['id']}/claims?kind=1&limit=100&offset=0",
    )
    claim = claims[0]
    if "retire:consumer" not in journal["actions"] and not claim["retirement_eligible"]:
        raise ValueError(
            "Delivered consumption has not been confirmed as retirement eligible"
        )
    transact("consumer", "approve_retirement", amount_base_units=str(3 * 10**18))
    transact(
        "consumer",
        "retire",
        amount_base_units="3000",
        batch_id=batch["chain_batch_id"],
        claim_id=claim["chain_claim_id"],
        node_id=claim["chain_node_id"],
        meter_id=claim["chain_meter_id"],
        proof=claim["proof"],
    )
    transact("producer", "withdraw_earnings", amount_base_units=str(3 * 10**15))
    consumer = wait(
        lambda: api("consumer", f"/communities/{cid}/settlement-statement"),
        lambda row: row["retired_wh"] == 3000,
        "retirement projection",
    )
    producer = wait(
        lambda: api("producer", f"/communities/{cid}/settlement-statement"),
        lambda row: row["withdrawn_earnings_wei"] == str(3 * 10**15),
        "withdrawal projection",
    )
    assert (
        consumer["available_wei"] == str(7 * 10**15)
        and producer["claimable_wei"] == "0"
    )
    assert sun.functions.totalSupply().call() == 2 * 10**18
    assert vault.functions.totalLiabilities().call() == 7 * 10**15
    assert (
        w3.eth.get_balance(vault.address) >= vault.functions.totalLiabilities().call()
    )
    report = {
        "status": "VERIFIED",
        "community_id": cid,
        "batch": read_batch(),
        "consumer_statement": consumer,
        "producer_statement": producer,
        "sun_supply_units": str(sun.functions.totalSupply().call()),
        "vault_liabilities_wei": str(vault.functions.totalLiabilities().call()),
        "transactions": journal["actions"],
        "notice": "Actual local MQTT, workers, confirmed test ETH and SUN. No physical routing or utility bill alteration.",
    }
    save_json(directory / "scenario-report.json", report)
    print(
        "VERIFIED: 5 kWh injection, 3 kWh allocated, 2 kWh unallocated, 0.003 ETH earned/withdrawn, 3 SUN retired. Report: .run/demo/scenario-report.json",
        flush=True,
    )


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        raise SystemExit(
            f"Scenario stopped ({type(error).__name__}). No unconfirmed success is claimed; inspect service readiness and the resumable public journal."
        ) from None
