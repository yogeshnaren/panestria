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
    calls = []

    def fake(self, args, *, timeout=30):
        calls.append(args)
        state = states[min(len(calls) - 1, len(states) - 1)]
        return subprocess.CompletedProcess(args, 0, json.dumps([{"Id": CID, "State": state}]), "")

    monkeypatch.setattr(DockerSandbox, "_docker", fake)
    monkeypatch.setattr(runner, "OOM_SETTLE_POLL_SECONDS", 0.01)
    return calls


def test_oom_reported_after_several_reads_is_still_observed(tmp_path, monkeypatch):
    calls = reports(monkeypatch, [stopped(False)] * 8 + [stopped(True)])
    settled = DockerSandbox(tmp_path)._settle_killed_state(CID, stopped(False))
    assert settled["OOMKilled"] is True and len(calls) == 9


def test_no_oom_report_keeps_the_plain_kill_within_the_bound(tmp_path, monkeypatch):
    calls = reports(monkeypatch, [stopped(False)])
    monkeypatch.setattr(runner, "OOM_SETTLE_SECONDS", 0.2)
    settled = DockerSandbox(tmp_path)._settle_killed_state(CID, stopped(False))
    assert settled["OOMKilled"] is False and 1 <= len(calls) <= 20


def test_non_kill_exit_and_known_oom_do_not_poll(tmp_path, monkeypatch):
    calls = reports(monkeypatch, [stopped(True)])
    sandbox = DockerSandbox(tmp_path)
    assert sandbox._settle_killed_state(CID, stopped(False, code=1))["ExitCode"] == 1
    assert sandbox._settle_killed_state(CID, stopped(True))["OOMKilled"] is True
    assert calls == []


def test_changed_exit_state_is_never_inferred(tmp_path, monkeypatch):
    reports(monkeypatch, [stopped(False, code=1)])
    with pytest.raises(SandboxRejected, match="exit_state_unconfirmed"):
        DockerSandbox(tmp_path)._settle_killed_state(CID, stopped(False))
