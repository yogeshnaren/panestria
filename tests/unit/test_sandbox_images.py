"""Trusted worker-image setup pulls only the pinned digest and reports typed failures."""

from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.sandbox import images
from panestria.sandbox.profiles import DEFAULT_IMAGE


class _Docker:
    def __init__(self, *, present: bool, pull_ok: bool = True, appears: bool = True) -> None:
        self.present, self.pull_ok, self.appears = present, pull_ok, appears
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["check"] is False and isinstance(kwargs["timeout"], int)
        self.calls.append(argv)
        if argv[1:3] == ["image", "inspect"]:
            code = 0 if self.present else 1
        else:
            code = 0 if self.pull_ok else 1
            self.present = self.pull_ok and self.appears
        return subprocess.CompletedProcess(argv, code, b"", b"")


def test_present_image_is_not_pulled(monkeypatch: pytest.MonkeyPatch) -> None:
    docker = _Docker(present=True)
    monkeypatch.setattr(images.subprocess, "run", docker)
    assert images.prepare_worker_image() == "present"
    assert docker.calls == [["docker", "image", "inspect", DEFAULT_IMAGE]]


def test_missing_image_is_pulled_by_its_pinned_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    docker = _Docker(present=False)
    monkeypatch.setattr(images.subprocess, "run", docker)
    assert "@sha256:" in DEFAULT_IMAGE
    assert images.prepare_worker_image() == "pulled"
    assert docker.calls == [
        ["docker", "image", "inspect", DEFAULT_IMAGE],
        ["docker", "pull", DEFAULT_IMAGE],
        ["docker", "image", "inspect", DEFAULT_IMAGE],
    ]


@pytest.mark.parametrize("docker", [_Docker(present=False, pull_ok=False), _Docker(present=False, appears=False)])
def test_failed_pull_is_typed(monkeypatch: pytest.MonkeyPatch, docker: _Docker) -> None:
    monkeypatch.setattr(images.subprocess, "run", docker)
    with pytest.raises(images.ImageUnavailable) as failed:
        images.prepare_worker_image()
    assert failed.value.code == "worker_image_pull_failed"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (FileNotFoundError("docker"), "docker_unavailable"),
        (subprocess.TimeoutExpired("docker", 1), "worker_image_timeout"),
    ],
)
def test_docker_errors_are_typed(monkeypatch: pytest.MonkeyPatch, error: Exception, code: str) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(images.subprocess, "run", fail)
    with pytest.raises(images.ImageUnavailable) as failed:
        images.prepare_worker_image()
    assert failed.value.code == code


def test_cli_reports_status_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr(images.subprocess, "run", _Docker(present=True))
    ok = runner.invoke(app, ["sandbox", "prepare-image"])
    assert ok.exit_code == 0
    assert json.loads(ok.stdout) == {"status": "present", "image": DEFAULT_IMAGE}
    monkeypatch.setattr(images.subprocess, "run", _Docker(present=False, pull_ok=False))
    failed = runner.invoke(app, ["sandbox", "prepare-image"])
    assert failed.exit_code == 1
    assert json.loads(failed.stderr) == {"code": "worker_image_pull_failed", "image": DEFAULT_IMAGE}
