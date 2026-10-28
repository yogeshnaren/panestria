"""Numeric-only procfs fixtures and refusal before any foreign container probe."""

import json

import pytest

from panestria.contracts.inference import InferenceUnavailable
from panestria.inference import process_memory
from panestria.inference.runtime import ModelRuntime


def proc(root, pid, rss, pss):
    directory = root / str(pid)
    directory.mkdir()
    (directory / "stat").write_text(f"{pid} (private command) " + " ".join(["0"] * 19 + ["123"]))
    (directory / "smaps_rollup").write_text(f"header\nRss: {rss} kB\nPss: {pss} kB\n")


def test_process_rss_is_independent_of_cgroup_memory_and_excludes_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(process_memory.os, "getpid", lambda: 5)
    proc(tmp_path, 1, 100, 80)
    proc(tmp_path, 3, 1000, 900)
    proc(tmp_path, 5, 500, 500)
    result = process_memory.observe(tmp_path)
    assert result == {
        "method": process_memory.METHOD,
        "process_count": 2,
        "rss_sum_bytes": 1100 * 1024,
        "pss_sum_bytes": 980 * 1024,
        "processes": [
            {"pid": 1, "rss_bytes": 100 * 1024, "pss_bytes": 80 * 1024},
            {"pid": 3, "rss_bytes": 1000 * 1024, "pss_bytes": 900 * 1024},
        ],
    }
    assert "private command" not in json.dumps(result)


@pytest.mark.parametrize("failure", ["missing", "malformed", "oversized", "duplicate-field"])
def test_incomplete_measurements_are_unavailable_not_zero(tmp_path, failure):
    proc(tmp_path, 1, 100, 80)
    path = tmp_path / "1/smaps_rollup"
    if failure == "missing":
        path.unlink()
    elif failure == "oversized":
        path.write_text("PRIVATE_SENTINEL" * 5000)
    elif failure == "duplicate-field":
        path.write_text("Rss: 100 kB\nRss: 200 kB\nPss: 80 kB\n")
    else:
        path.write_text("Rss: unknown kB\n")
    with pytest.raises(process_memory.MemoryObservationUnavailable, match="^process_memory_unavailable$"):
        process_memory.observe(tmp_path)


@pytest.mark.requires_nonroot
@pytest.mark.parametrize("wrong", ["runtime", "pid-namespace", "stopped"])
def test_runtime_probes_only_its_own_running_private_pid_namespace(tmp_path, monkeypatch, wrong):
    runtime = ModelRuntime(tmp_path / "models", tmp_path / "socket")
    runtime.id = "ab" * 32
    actual = {
        "Id": runtime.id,
        "State": {"Running": True},
        "Config": {"Labels": {"panestria.runtime": runtime.identity}, "User": f"{runtime.uid}:{runtime.gid}"},
        "HostConfig": {"PidMode": ""},
    }
    if wrong == "runtime":
        actual["Config"]["Labels"]["panestria.runtime"] = "other"
    elif wrong == "pid-namespace":
        actual["HostConfig"]["PidMode"] = "host"
    else:
        actual["State"]["Running"] = False
    calls = []

    def docker(args):
        calls.append(args)
        assert args == ["inspect", runtime.id]
        return json.dumps([actual])

    monkeypatch.setattr(runtime, "_docker", docker)
    with pytest.raises(InferenceUnavailable, match="^process_memory_unavailable$"):
        runtime.process_memory()
    assert len(calls) == 1
