"""Disposable real Mosquitto: TLS, authentication and cross-community ACL denial."""

import importlib.util
import json
import queue
import socket
import subprocess
import time
from pathlib import Path
from threading import Event
from uuid import uuid4

import paho.mqtt.client as mqtt


def test_tls_broker_requires_auth_and_rejects_cross_community_publish(tmp_path):
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "mqtt_acl", root / "scripts/provision_mqtt_acl.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entry = {
        "community_id": str(uuid4()),
        "node_id": str(uuid4()),
        "device_id": str(uuid4()),
    }
    username = "meter-" + entry["device_id"]
    allowed = f"solar/{entry['community_id']}/{entry['node_id']}/{entry['device_id']}/telemetry"
    forbidden = f"solar/{uuid4()}/{entry['node_id']}/{entry['device_id']}/telemetry"
    (tmp_path / "acl").write_text(module.render({"meter": entry}))
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=IP:127.0.0.1,DNS:localhost",
            "-keyout",
            str(tmp_path / "server.key"),
            "-out",
            str(tmp_path / "server.crt"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    image = "eclipse-mosquitto:2.0"
    mount = f"{tmp_path}:/run/test:rw"
    # Deliberately public ephemeral test passwords, never environment credentials.
    for index, user in enumerate((username, "solar-subscriber")):
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--user",
                "0",
                "-v",
                mount,
                image,
                "mosquitto_passwd",
                *(["-c"] if index == 0 else []),
                "-b",
                "/run/test/passwords",
                user,
                "public-test-password",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    (tmp_path / "broker.conf").write_text(
        "user root\nlistener 8883\nallow_anonymous false\npassword_file /run/test/passwords\nacl_file /run/test/acl\ncertfile /run/test/server.crt\nkeyfile /run/test/server.key\nlog_dest stdout\n"
    )
    name = "solar-acl-test-" + uuid4().hex[:12]
    clients = []
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--user",
                "0",
                "-p",
                "127.0.0.1::8883",
                "-v",
                mount,
                image,
                "mosquitto",
                "-c",
                "/run/test/broker.conf",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        binding = subprocess.check_output(
            ["docker", "port", name, "8883/tcp"], text=True
        ).strip()
        port = int(binding.rsplit(":", 1)[1])
        deadline = time.monotonic() + 10
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                assert time.monotonic() < deadline, (
                    "Disposable TLS broker did not start"
                )
                time.sleep(0.1)
        inbox = queue.Queue()
        subscribed = Event()

        def client(user=None):
            instance = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=uuid4().hex,
                protocol=mqtt.MQTTv5,
            )
            instance.tls_set(ca_certs=str(tmp_path / "server.crt"))
            if user:
                instance.username_pw_set(user, "public-test-password")
            clients.append(instance)
            return instance

        subscriber = client("solar-subscriber")
        subscriber.on_connect = lambda c, *args: c.subscribe("solar/#", qos=1)
        subscriber.on_subscribe = lambda *args: subscribed.set()
        subscriber.on_message = lambda c, u, m: inbox.put(
            (m.topic, json.loads(m.payload))
        )
        subscriber.connect("127.0.0.1", port)
        subscriber.loop_start()
        assert subscribed.wait(5)
        connected = Event()
        publisher = client(username)
        publisher.on_connect = lambda *args: connected.set()
        publisher.connect("127.0.0.1", port)
        publisher.loop_start()
        assert connected.wait(5)
        info = publisher.publish(allowed, '{"accepted":true}', qos=1)
        info.wait_for_publish(timeout=5)
        assert inbox.get(timeout=5)[0] == allowed
        denied = Event()
        publisher.on_publish = lambda c, u, mid, reason, properties: (
            denied.set() if reason.is_failure else None
        )
        publisher.publish(forbidden, '{"forbidden":true}', qos=1)
        assert denied.wait(5), "Broker must refuse a principal's cross-community write"
        assert inbox.empty()
        refused = Event()
        anonymous = client()
        anonymous.on_connect = lambda c, u, f, reason, p: (
            refused.set() if reason.is_failure else None
        )
        anonymous.connect("127.0.0.1", port)
        anonymous.loop_start()
        assert refused.wait(5), "Anonymous TLS client must not authenticate"
    finally:
        for c in clients:
            c.disconnect()
            c.loop_stop()
        subprocess.run(
            ["docker", "rm", "-f", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
