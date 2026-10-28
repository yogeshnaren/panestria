"""A failed compute driver cannot silently start a requested GPU runtime on CPU."""

import subprocess
from pathlib import Path

import pytest

from panestria.contracts.inference import InferenceUnavailable
from panestria.inference import runtime
from panestria.resources.primary import PrimaryLease


@pytest.mark.parametrize(
    "code,out,err",
    [(1, b"", b""), (0, b"", b""), (0, b"CUDA_READY\n", b"synthetic-private-diagnostic")],
)
def test_failed_compute_probe_is_redacted(monkeypatch, code, out, err):
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, code, out, err))
    with pytest.raises(InferenceUnavailable, match="^gpu_initialization_unavailable$"):
        runtime.require_gpu_driver()


@pytest.mark.parametrize("error", [OSError("synthetic-private-path"), subprocess.TimeoutExpired("probe", 5)])
def test_unavailable_or_hung_driver_has_no_retry(monkeypatch, error):
    calls = []

    def run(*args, **kwargs):
        calls.append(1)
        raise error

    monkeypatch.setattr(runtime.subprocess, "run", run)
    with pytest.raises(InferenceUnavailable, match="^gpu_initialization_unavailable$"):
        runtime.require_gpu_driver()
    assert calls == [1]


def test_probe_never_inherits_credentials_proxy_or_loader_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "SYNTHETIC_MUST_NOT_PROPAGATE")
    monkeypatch.setenv("LD_PRELOAD", "SYNTHETIC_MUST_NOT_PROPAGATE")
    monkeypatch.setenv("HTTPS_PROXY", "SYNTHETIC_MUST_NOT_PROPAGATE")

    def run(argv, **kwargs):
        assert argv[:3] == [runtime.sys.executable, "-I", "-c"]
        assert kwargs == {
            "cwd": "/",
            "env": {"PATH": "/usr/bin:/bin"},
            "stdin": subprocess.DEVNULL,
            "capture_output": True,
            "timeout": 5,
            "check": False,
        }
        assert "cuInit" in argv[3] and "cuDeviceGetCount" in argv[3]
        return subprocess.CompletedProcess(argv, 0, b"CUDA_READY\n", b"")

    monkeypatch.setattr(runtime.subprocess, "run", run)
    runtime.require_gpu_driver()


@pytest.mark.requires_nonroot
def test_gpu_denial_preserves_containers_and_releases_primary(tmp_path, monkeypatch):
    model = runtime.ModelRuntime(tmp_path / "cache", tmp_path / "socket", gpu=True)
    model.primary = PrimaryLease(tmp_path / "primary")

    def denied():
        raise InferenceUnavailable("gpu_initialization_unavailable")

    def forbidden(*args, **kwargs):
        raise AssertionError("no Docker enumeration, reclamation, create or start after GPU denial")

    monkeypatch.setattr(runtime, "require_gpu_driver", denied)
    monkeypatch.setattr(model, "_docker", forbidden)
    with pytest.raises(InferenceUnavailable, match="^gpu_initialization_unavailable$"):
        model.start()
    assert model.id is None and model.primary.descriptor is None
    assert not (tmp_path / "socket").exists() and not (tmp_path / "cache").exists()
    # A failed GPU launch does not block a subsequent explicit owner launch.
    another = PrimaryLease(tmp_path / "primary")
    another.acquire()
    another.release()


@pytest.mark.requires_nonroot
def test_explicit_cpu_runtime_does_not_require_cuda(tmp_path: Path, monkeypatch):
    model = runtime.ModelRuntime(tmp_path / "cache", tmp_path / "socket", gpu=False)
    model.primary = PrimaryLease(tmp_path / "primary")

    def forbidden():
        raise AssertionError("explicit CPU startup must not initialize CUDA")

    def reached_existing_startup():
        raise InferenceUnavailable("existing_startup_reached")

    monkeypatch.setattr(runtime, "require_gpu_driver", forbidden)
    monkeypatch.setattr(model, "_reap_orphans", reached_existing_startup)
    with pytest.raises(InferenceUnavailable, match="^existing_startup_reached$"):
        model.start()
    assert model.primary.descriptor is None
