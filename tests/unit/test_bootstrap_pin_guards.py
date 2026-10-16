"""Actual filesystem guard checks, no Docker/native CLI/inference."""

import os
import threading

import pytest

from native_bootstrap_support import synthetic_pin
from panestria.brokers.harness import native_bootstrap as bootstrap
from panestria.brokers.harness.cli_profile import BinaryPin


@pytest.mark.parametrize(
    "mutation",
    [
        "digest",
        "relative",
        "alias",
        "alias-loop",
        "hardlink",
        "group-write",
        "not-executable",
        "empty",
        "fifo",
        "directory",
        "missing",
        "oversize",
    ],
)
def test_invalid_or_changed_executable_never_reaches_container(tmp_path, monkeypatch, mutation):
    pin = synthetic_pin(tmp_path, monkeypatch)
    if mutation == "digest":
        pin = BinaryPin(pin.path, "0" * 64)
    elif mutation == "relative":
        pin = BinaryPin(type(pin.path)("relative"), pin.sha256)
    elif mutation == "alias":
        alias = tmp_path / "alias"
        alias.symlink_to(pin.path)
        pin = BinaryPin(alias, pin.sha256)
    elif mutation == "alias-loop":
        pin.path.unlink()
        pin.path.symlink_to(pin.path)
    elif mutation == "hardlink":
        os.link(pin.path, tmp_path / "extra-link")
    elif mutation == "group-write":
        pin.path.chmod(0o720)
    elif mutation == "not-executable":
        pin.path.chmod(0o600)
    elif mutation == "empty":
        pin.path.write_bytes(b"")
    elif mutation == "fifo":
        pin.path.unlink()
        os.mkfifo(pin.path)
    elif mutation == "directory":
        pin.path.unlink()
        pin.path.mkdir()
    elif mutation == "missing":
        pin.path.unlink()
    elif mutation == "oversize":
        with pin.path.open("r+b") as file:
            file.truncate(bootstrap.MAX_BINARY + 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid_pin_reached_runtime")

    monkeypatch.setattr(bootstrap.DockerSandbox, "run", forbidden)
    with pytest.raises(bootstrap.NativeBootstrapUnavailable):
        bootstrap.NativeBootstrap().inspect(pin)


@pytest.mark.parametrize("seconds", [True, 0, 16, float("nan"), float("inf"), "10"])
def test_invalid_metadata_deadline_cannot_widen_execution(tmp_path, monkeypatch, seconds):
    pin = synthetic_pin(tmp_path, monkeypatch)
    with pytest.raises(bootstrap.NativeBootstrapUnavailable, match="invalid_native_bootstrap_reference"):
        bootstrap.NativeBootstrap().inspect(pin, wall_seconds=seconds)


def test_pre_cancel_and_unsupported_host_never_start_native_process(tmp_path, monkeypatch):
    pin = synthetic_pin(tmp_path, monkeypatch)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(bootstrap.NativeBootstrapUnavailable, match="native_bootstrap_cancelled"):
        bootstrap.NativeBootstrap().inspect(pin, cancel=cancel)
    monkeypatch.setattr(bootstrap.platform, "machine", lambda: "unsupported-fixture")
    with pytest.raises(bootstrap.NativeBootstrapUnavailable, match="native_bootstrap_platform_unavailable"):
        bootstrap.NativeBootstrap().inspect(pin)


def test_api_accepts_no_prompt_environment_config_command_or_network(tmp_path, monkeypatch):
    pin = synthetic_pin(tmp_path, monkeypatch)
    for keyword in ("prompt", "env", "config", "argv", "network", "image", "workspace"):
        with pytest.raises(TypeError):
            bootstrap.NativeBootstrap().inspect(pin, **{keyword: "synthetic"})


def test_replaced_path_is_denied_even_while_original_descriptor_remains_open(tmp_path, monkeypatch):
    pin = synthetic_pin(tmp_path, monkeypatch)
    original = bootstrap._snapshot

    def replace(pin, descriptor, destination, deadline):
        pin.path.rename(tmp_path / "original-still-held")
        pin.path.write_bytes(b"synthetic-replacement")
        pin.path.chmod(0o700)
        original(pin, descriptor, destination, deadline)

    monkeypatch.setattr(bootstrap, "_snapshot", replace)
    with pytest.raises(bootstrap.NativeBootstrapUnavailable, match="native_bootstrap_unavailable"):
        bootstrap.NativeBootstrap().inspect(pin)
