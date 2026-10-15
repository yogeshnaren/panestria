"""Runs only as a child of the live test's isolated dbus-run-session."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from jeepney.bus_messages import message_bus
from jeepney.io.blocking import Proxy
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.memory.keys import KeyStoreUnavailable, ProfileKeyHandle, SecretServiceProfileKeys, _BoundedConnection


def stop(daemon: subprocess.Popen[bytes]) -> None:
    if daemon.poll() is None:
        daemon.terminate()
        try:
            daemon.wait(timeout=3)
        except subprocess.TimeoutExpired:
            daemon.kill()
            daemon.wait(timeout=3)


def wait_name(expected: bool) -> None:
    deadline = time.monotonic() + 8
    while True:
        # NameHasOwner does not activate a competing Secret Service daemon.
        with _BoundedConnection(time.monotonic() + 1) as connection:
            ready = Proxy(message_bus, connection).NameHasOwner("org.freedesktop.secrets")[0]
        if bool(ready) == expected:
            return
        if time.monotonic() >= deadline:
            raise AssertionError("isolated_keyring_lifecycle_failed")
        time.sleep(0.05)


def main() -> None:
    root = Path(sys.argv[1]).resolve(strict=True)
    # The launcher provides a new bus and these private directories. Refuse an
    # accidental invocation with an ordinary desktop environment.
    assert os.environ.get("PANESTRIA_ISOLATED_KEYRING") == str(root)
    assert os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    for name, directory in (("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"), ("XDG_RUNTIME_DIR", "runtime")):
        target = root / directory
        assert os.environ.get(name) == str(target)
        assert target.stat().st_mode & 0o077 == 0
    password = secrets.token_bytes(32).hex().encode() + b"\n"

    def start() -> subprocess.Popen[bytes]:
        daemon = subprocess.Popen(
            [
                sys.argv[2],
                "--foreground",
                "--unlock",
                "--components=secrets",
                f"--control-directory={root / 'control'}",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert daemon.stdin is not None
        daemon.stdin.write(password)
        daemon.stdin.close()
        return daemon

    daemon = start()
    try:
        store = SecretServiceProfileKeys(timeout_seconds=1)
        reference = ProfileKeyHandle(**{field: str(uuid4()) for field in ProfileKeyHandle.model_fields})
        wait_name(True)
        args = [
            value for name, value in reference.model_dump().items() for value in ("--" + name.replace("_", "-"), value)
        ]
        runner = CliRunner()
        for operation in ("key-create", "key-check"):
            result = runner.invoke(app, ["profile", operation, *args])
            assert result.exit_code == 0, "isolated_key_cli_failed"
            assert json.loads(result.output) == {
                "schema_version": 1,
                "status": "PRESENT",
                "handle": reference.model_dump(),
            }
        key = store.load(reference)
        store.provision(reference)
        assert key.get_secret_value() == store.load(reference).get_secret_value()
        # A different scope cannot find the existing key.
        for field in ProfileKeyHandle.model_fields:
            wrong = reference.model_copy(update={field: str(uuid4())})
            try:
                store.load(wrong)
            except KeyStoreUnavailable as exc:
                assert exc.code == "key_handle_missing"
            else:
                raise AssertionError("cross_scope_key_visible")
        other = reference.model_copy(update={"key_id": str(uuid4())})
        store.provision(other)
        assert store.load(other).get_secret_value() != key.get_secret_value()
        assert len(key.get_secret_value()) == 32 and "**********" in repr(key)
        keyrings = list((root / "data" / "keyrings").glob("*.keyring"))
        assert keyrings, "persistent_test_keyring_missing"
        assert all(key.get_secret_value() not in path.read_bytes() for path in keyrings)
        # Lock only the collection reached on this isolated child bus.
        with store._collection() as collection:
            collection.lock()
        try:
            store.load(reference)
        except KeyStoreUnavailable as exc:
            assert exc.code == "key_store_locked"
        else:
            raise AssertionError("locked_keyring_key_visible")
        stop(daemon)
        wait_name(False)
        daemon = start()
        wait_name(True)
        assert store.load(reference).get_secret_value() == key.get_secret_value()
        assert store.load(other).get_secret_value() != key.get_secret_value()
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "scopes": 4,
                    "persistent_test_keyring": True,
                    "locked_denied": True,
                    "daemon_restart_preserved_keys": True,
                    "cli_setup_checked": True,
                }
            )
        )
    finally:
        stop(daemon)


if __name__ == "__main__":
    main()
