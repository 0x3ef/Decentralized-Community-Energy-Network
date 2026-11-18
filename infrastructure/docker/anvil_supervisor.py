"""Local Anvil with bounded history and atomic, validated rotating checkpoints.

Only this process writes anvil.json. Anvil serves an immutable RPC dump; a failed
write never replaces the last good checkpoint. No PostgreSQL access is involved.
"""

import fcntl
import gzip
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

STATE = Path(os.environ.get("ANVIL_STATE_DIR", "/state"))
RPC = "http://127.0.0.1:8545"
MAX_BYTES = 128 * 1024 * 1024
INTERVAL = int(os.environ.get("ANVIL_CHECKPOINT_SECONDS", "30"))


def rpc(method, params=None):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    ).encode()
    request = urllib.request.Request(RPC, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(MAX_BYTES * 2 + 1)
    if len(raw) > MAX_BYTES * 2:
        raise ValueError("RPC checkpoint exceeds size limit")
    result = json.loads(raw)
    if "error" in result:
        raise ValueError("Anvil checkpoint RPC failed")
    return result["result"]


def validate(data):
    if len(data) > MAX_BYTES:
        raise ValueError("Checkpoint exceeds 128 MiB; archive it before local recovery")
    value = json.loads(data)
    if not isinstance(value, dict) or not {"accounts", "block"} <= value.keys():
        raise ValueError("Not an Anvil state checkpoint")
    return value


def atomic_write(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_checkpoint(path):
    with path.open("rb") as source:
        data = source.read(MAX_BYTES + 1)
    validate(data)
    return data


def restore_previous():
    current = STATE / "anvil.json"
    previous = STATE / "anvil.previous.json"
    if not current.exists() and not previous.exists():
        return False
    try:
        read_checkpoint(current)
        return True
    except (OSError, ValueError):
        pass
    try:
        data = read_checkpoint(previous)
    except (OSError, ValueError):
        raise SystemExit(
            "No valid Anvil checkpoint. PostgreSQL is untouched. Run make recover."
        ) from None
    archive = STATE / "archive" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    archive.mkdir(parents=True, mode=0o700)
    if current.exists():
        current.rename(archive / "anvil.invalid.json")
    atomic_write(current, data)
    print(
        "Recovered the previous valid Anvil checkpoint; recent unsaved transactions may need reconciliation.",
        flush=True,
    )
    return True


def checkpoint():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE / ".checkpoint.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        identity_path = STATE / "chain.json"
        if identity_path.exists():
            expected = json.loads(identity_path.read_text()).get("genesis")
            if (
                expected
                and rpc("eth_getBlockByNumber", ["0x0", False])["hash"] != expected
            ):
                raise ValueError(
                    "Chain identity changed; refusing to replace completed checkpoints"
                )
        compressed = bytes.fromhex(rpc("anvil_dumpState", [True])[2:])
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source:
            data = source.read(MAX_BYTES + 1)
        validate(data)
        if shutil.disk_usage(STATE).free < len(data) * 2 + 64 * 1024 * 1024:
            raise OSError(
                "Insufficient space for an atomic checkpoint; previous state retained"
            )
        current, previous = STATE / "anvil.json", STATE / "anvil.previous.json"
        if current.exists():
            # Link the complete old inode; never copy from a concurrently written file.
            pending = STATE / "anvil.previous.pending"
            pending.unlink(missing_ok=True)
            os.link(current, pending)
            os.replace(pending, previous)
        atomic_write(current, data)
        atomic_write(
            STATE / "checkpoint.json",
            json.dumps({"at": time.time(), "bytes": len(data)}).encode(),
        )


def reset():
    """Explicit local recovery archives every active checkpoint, never deletes it."""
    archive = STATE / "archive" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    archive.mkdir(parents=True, mode=0o700)
    for name in (
        "anvil.json",
        "anvil.previous.json",
        "checkpoint.json",
        "chain.json",
        "anvil.load.json",
    ):
        path = STATE / name
        if path.exists():
            path.rename(archive / name)
    print(f"Anvil checkpoints archived at {archive}; SQL data was not accessed.")


def normalize_genesis(saved, identity):
    """Keep the original block-zero timestamp across Foundry snapshot loads."""
    if "timestamp" not in identity:
        genesis_blocks = [
            b
            for b in (saved or {}).get("blocks", [])
            if int(b["header"]["number"], 16) == 0
        ]
        if saved is not None and not genesis_blocks:
            raise ValueError(
                "Checkpoint has no genesis identity; explicit recovery required"
            )
        identity["timestamp"] = (
            min(int(b["header"]["timestamp"], 16) for b in genesis_blocks)
            if genesis_blocks
            else int(time.time())
        )
    if saved is not None:
        # Foundry appends a newly constructed genesis when loading state. Old
        # dumps can contain several block-zero headers; keep the original one
        # and construct the identical header instead of a new wall-time genesis.
        saved["blocks"] = [
            b
            for b in saved.get("blocks", [])
            if int(b["header"]["number"], 16) != 0
            or int(b["header"]["timestamp"], 16) == identity["timestamp"]
        ]
    return saved, identity


def serve():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    loaded = restore_previous()
    identity_path = STATE / "chain.json"
    identity = json.loads(identity_path.read_text()) if identity_path.exists() else {}
    saved = validate(read_checkpoint(STATE / "anvil.json")) if loaded else None
    saved, identity = normalize_genesis(saved, identity)
    atomic_write(identity_path, json.dumps(identity).encode())
    load_path = STATE / "anvil.load.json"
    if saved is not None:
        atomic_write(load_path, json.dumps(saved, separators=(",", ":")).encode())
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    command = [
        "anvil",
        "--host",
        "0.0.0.0",
        "--chain-id",
        "31337",
        "--timestamp",
        str(identity["timestamp"]),
        "--block-time",
        "12",
        "--mixed-mining",
        "--prune-history",
        "128",
        "--silent",
    ]
    if loaded:
        command += ["--load-state", str(load_path)]
    child = subprocess.Popen(command)
    try:
        deadline = time.monotonic() + 60
        while child.poll() is None:
            try:
                if int(rpc("eth_chainId"), 16) == 31337:
                    break
            except Exception:
                pass
            if stop.wait(0.2) or time.monotonic() > deadline:
                raise RuntimeError("Anvil RPC did not become ready")
        if child.poll() is not None:
            raise RuntimeError("Anvil exited while loading state")
        genesis = rpc("eth_getBlockByNumber", ["0x0", False])["hash"]
        if identity.get("genesis") and identity["genesis"] != genesis:
            raise RuntimeError(
                "Genesis identity changed; completed checkpoints retained"
            )
        identity["genesis"] = genesis
        atomic_write(identity_path, json.dumps(identity).encode())
        load_path.unlink(missing_ok=True)
        # --timestamp anchors genesis but also initializes Anvil's mining clock.
        # Resume mining at wall time (or above the saved head), not at genesis.
        head = rpc("eth_getBlockByNumber", ["latest", False])
        next_time = max(int(time.time()), int(head["timestamp"], 16) + 1)
        rpc("evm_setNextBlockTimestamp", [next_time])
        rpc("evm_mine")
        checkpoint()
        print(
            "Anvil ready: bounded historical states, atomic checkpoints, same persistent volume.",
            flush=True,
        )
        while not stop.wait(INTERVAL):
            if child.poll() is not None:
                raise RuntimeError("Anvil process exited")
            checkpoint()
        checkpoint()
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if action == "inspect":
        paths = [STATE / name for name in ("anvil.json", "anvil.previous.json")]
        state = "empty" if not any(path.exists() for path in paths) else "invalid"
        for path in paths:
            try:
                read_checkpoint(path)
                state = "valid"
                break
            except (OSError, ValueError):
                pass
        print(json.dumps({"state": state}))
    elif action == "health":
        metadata = json.loads((STATE / "checkpoint.json").read_text())
        identity = json.loads((STATE / "chain.json").read_text())
        if (
            not identity.get("genesis")
            or identity["genesis"]
            != rpc("eth_getBlockByNumber", ["0x0", False])["hash"]
        ):
            raise SystemExit(1)
        if (
            int(rpc("eth_chainId"), 16) != 31337
            or time.time() - metadata["at"] > INTERVAL * 3 + 30
        ):
            raise SystemExit(1)
    elif action == "reset":
        reset()
    elif action == "checkpoint":
        checkpoint()
    elif action == "serve":
        serve()
    else:
        raise SystemExit("Expected serve, health, checkpoint, inspect or reset")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"Anvil supervisor stopped: {type(error).__name__}. Last completed checkpoints retained.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
