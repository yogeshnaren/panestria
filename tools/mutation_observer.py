"""Record actual failing test calls, not coverage guesses or raw exception data."""

import hashlib
import json
import os
from pathlib import Path

_calls = []
_errors = []


def pytest_sessionstart(session):
    _calls.clear()
    _errors.clear()


def pytest_runtest_logreport(report):
    if report.when == "call":
        _calls.append({"test": report.nodeid, "outcome": report.outcome, "seconds": report.duration})
    elif report.failed:
        _errors.append({"test": report.nodeid, "phase": report.when})


def pytest_sessionfinish(session, exitstatus):
    directory = os.environ.get("PANESTRIA_MUTATION_OBSERVATIONS")
    if not directory:
        return
    mutant = os.environ.get("MUTANT_UNDER_TEST", "baseline")
    identity = hashlib.sha256(mutant.encode()).hexdigest()
    # One child per mutant; fresh campaign directory prevents cache/stale mixing.
    path = Path(directory) / f"{identity}.json"
    path.write_text(json.dumps({"mutant": mutant, "exit_code": int(exitstatus), "calls": _calls, "errors": _errors}))
    path.chmod(0o600)
