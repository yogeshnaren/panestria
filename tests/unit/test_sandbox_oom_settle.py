"""A late daemon OOM report still classifies a SIGKILL exit as memory_limit."""

from __future__ import annotations

import json
import subprocess

import pytest

import panestria.sandbox.runner as runner
from panestria.sandbox.profiles import SandboxRejected
from panestria.sandbox.runner import DockerSandbox

CID = "ab" * 32


def stopped(oom: bool, code: int = 137) -> dict:
    return {"Running": False, "Status": "exited", "OOMKilled": oom, "ExitCode": code}


def reports(monkeypatch, states):
    calls, sleeps = [], []

    def fake(self, args, *, timeout=30):
        calls.append(args)
        state = states[min(len(calls) - 1, len(states) - 1)]
        return subprocess.CompletedProcess(args, 0, json.dumps([{"Id": CID, "State": state}]), "")

    monkeypatch.setattr(DockerSandbox, "_docker", fake)
    monkeypatch.setattr(runner.time, "sleep", sleeps.append)
    return calls, sleeps


def test_reads_back_off_across_more_than_a_second_and_stay_bounded(tmp_path, monkeypatch):
    calls, sleeps = reports(monkeypatch, [stopped(False)])
    settled = DockerSandbox(tmp_path)._settle_killed_state(CID, stopped(False))
    assert settled["OOMKilled"] is False
    assert len(calls) == 4 and sum(sleeps) >= 1.2 and sleeps == sorted(sleeps)


def test_oom_reported_on_the_last_read_is_still_observed(tmp_path, monkeypatch):
    calls, _ = reports(monkeypatch, [stopped(False)] * 3 + [stopped(True)])
    assert DockerSandbox(tmp_path)._settle_killed_state(CID, stopped(False))["OOMKilled"] is True
    assert len(calls) == 4


def test_non_kill_exit_and_known_oom_do_not_poll(tmp_path, monkeypatch):
    calls, _ = reports(monkeypatch, [stopped(True)])
    sandbox = DockerSandbox(tmp_path)
    assert sandbox._settle_killed_state(CID, stopped(False, code=1))["ExitCode"] == 1
    assert sandbox._settle_killed_state(CID, stopped(True))["OOMKilled"] is True
    assert calls == []


def test_changed_exit_state_is_never_inferred(tmp_path, monkeypatch):
    reports(monkeypatch, [stopped(False, code=1)])
    with pytest.raises(SandboxRejected, match="exit_state_unconfirmed"):
        DockerSandbox(tmp_path)._settle_killed_state(CID, stopped(False))
