"""Explicit operator qualification of the pinned split-role PUBLIC Bash runtime.

Run a fixed reviewed source conformance set, not arbitrary project tests. A
certificate enables no project policy and never constitutes G1 or owner acceptance.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from panestria.contracts.native_model import NativeModel, validate_native_model
from panestria.contracts.policy import Action, TrustAxis
from panestria.execution.native_build import runtime_versions
from panestria.execution.proposal_demo import DemoUnavailable, _atomic, _lock, _private
from panestria.kernel.build import BuildEvidenceStore
from panestria.policy.profiles import CertificateStore

NODES = (
    "tests/integration/test_aos_008.py::test_os_effective_uid_mounts_egress_and_limits",
    "tests/integration/test_aos_008.py::test_resource_pressure_is_contained",
    "tests/integration/test_aos_008.py::test_readonly_profile_and_private_paths",
    "tests/integration/test_aos_008.py::test_sandbox_failure_cleanup",
    "tests/integration/test_sandbox_cancellation.py::test_actual_worker_cancellation_stops_and_removes_only_its_container",
    "tests/integration/test_scoped_bash.py::test_bash_exec_inherits_os_network_mount_and_secret_limits",
    "tests/integration/test_scoped_bash.py::test_actual_claude_subscription_bash_build_and_exact_review",
)
EXPECTED = {
    ("tests.integration.test_aos_008", "test_os_effective_uid_mounts_egress_and_limits"),
    *(
        ("tests.integration.test_aos_008", f"test_resource_pressure_is_contained[{case}]")
        for case in ("memory-memory_limit", "output-output_limit", "time-deadline_exceeded", "pids-completed")
    ),
    ("tests.integration.test_aos_008", "test_readonly_profile_and_private_paths"),
    ("tests.integration.test_aos_008", "test_sandbox_failure_cleanup"),
    *(
        (
            "tests.integration.test_sandbox_cancellation",
            f"test_actual_worker_cancellation_stops_and_removes_only_its_container[{case}]",
        )
        for case in ("False", "True")
    ),
    ("tests.integration.test_scoped_bash", "test_bash_exec_inherits_os_network_mount_and_secret_limits"),
    ("tests.integration.test_scoped_bash", "test_actual_claude_subscription_bash_build_and_exact_review"),
}
ACTIONS: list[Action] = ["read", "edit", "external-send", "merge"]


class QualificationUnavailable(ValueError):
    pass


def validate_report(raw: bytes, candidate: str, native_model: NativeModel | None = None) -> list[dict[str, str]]:
    try:
        if type(raw) is not bytes or len(raw) > 1024 * 1024 or b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
            raise ValueError
        root = ET.fromstring(raw)
        observed = []
        seen = set()
        for case in root.iter("testcase"):
            identity = (case.get("classname"), case.get("name"))
            if (
                identity in seen
                or identity not in EXPECTED
                or any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
            ):
                raise ValueError
            seen.add(identity)
            props = {item.get("name"): item.get("value") for item in case.iter("property")}
            if props.get("candidate_commit") != candidate or props.get("worktree_state") != "clean":
                raise ValueError
            if "TEST_FIXTURE_NOT_LIVE" in json.dumps(props):
                raise ValueError
            if native_model is not None and identity == (
                "tests.integration.test_scoped_bash",
                "test_actual_claude_subscription_bash_build_and_exact_review",
            ):
                observation = json.loads(props.get("native_observation") or "null")
                if (
                    observation["requested_model"] != native_model
                    or observation["process"]["result"]["reported_init_model"] != native_model
                ):
                    raise ValueError
            observed.append({"module": str(identity[0]), "test": str(identity[1])})
        if seen != EXPECTED:
            raise ValueError
        return sorted(observed, key=lambda row: (row["module"], row["test"]))
    except (ValueError, TypeError, KeyError, ET.ParseError):
        raise QualificationUnavailable("qualification_evidence_incomplete") from None


def _state(root: Path) -> str:
    env = {
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    prefix = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(root)]
    try:
        commit = subprocess.run(
            [*prefix, "rev-parse", "HEAD"], env=env, capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            [*prefix, "status", "--porcelain"], env=env, capture_output=True, timeout=5, check=True
        ).stdout
        if not re.fullmatch(r"[0-9a-f]{40}", commit) or dirty:
            raise ValueError
        return commit
    except (OSError, subprocess.SubprocessError, ValueError):
        raise QualificationUnavailable("clean_qualification_checkout_required") from None


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    # Give pytest KeyboardInterrupt so its exact fixture-owned DB/container
    # finalizers run. Never guess ownership from all containers created meanwhile.
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        process.wait(timeout=5)
        return
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        raise QualificationUnavailable("qualification_cleanup_unconfirmed") from None


def qualify(
    directory: Path, *, public_subscription_smoke: bool, native_model: NativeModel | None = None
) -> dict[str, object]:
    try:
        return _qualify(directory, public_subscription_smoke=public_subscription_smoke, native_model=native_model)
    except DemoUnavailable:
        raise QualificationUnavailable("private_qualification_directory_unavailable") from None


def _qualify(
    directory: Path, *, public_subscription_smoke: bool, native_model: NativeModel | None = None
) -> dict[str, object]:
    if public_subscription_smoke is not True:
        raise QualificationUnavailable("explicit_public_subscription_smoke_required")
    validate_native_model(native_model)
    root = Path(__file__).resolve().parents[3]
    if (root / "src/panestria").resolve() != Path(__file__).resolve().parents[1] or not (root / "uv.lock").is_file():
        raise QualificationUnavailable("qualification_source_checkout_required")
    candidate = _state(root)
    versions = runtime_versions(native_model) if native_model is not None else runtime_versions()
    uv = shutil.which("uv")
    if uv is None:
        raise QualificationUnavailable("frozen_qualification_runtime_required")
    destination = _private(directory)
    with _lock(destination / "qualification.lock"):
        run = _private(destination / ("run-" + uuid4().hex))
        journal = run / "result.json"
        _atomic(journal, {"status": "STARTED", "candidate_commit": candidate, "runtime_versions": versions})
        log, xml = run / "pytest.log", run / "raw.xml"
        env = {
            "PATH": str(Path(uv).parent) + ":/usr/local/bin:/usr/bin:/bin",
            "HOME": str(Path.home()),
            "LANG": "C.UTF-8",
            "UV_OFFLINE": "1",
            "UV_CACHE_DIR": str(Path.home() / ".cache/uv"),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            **({"PANESTRIA_QUALIFICATION_NATIVE_MODEL": native_model} if native_model is not None else {}),
        }
        command = [sys.executable, "-I", "-m", "pytest", *NODES, "-q", "--maxfail=1", "--junitxml=" + str(xml)]
        process = None
        try:
            with log.open("xb") as output:
                log.chmod(0o600)
                process = subprocess.Popen(
                    command,
                    cwd=root,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                deadline = time.monotonic() + 300
                while process.poll() is None:
                    if time.monotonic() >= deadline or log.stat().st_size > 1024 * 1024:
                        _stop(process)
                        raise QualificationUnavailable("qualification_timeout_or_output_limit")
                    time.sleep(0.1)
            if process.returncode:
                raise QualificationUnavailable("qualification_cases_failed")
            raw = xml.read_bytes()
            observations = validate_report(raw, candidate, native_model)
            current = runtime_versions(native_model) if native_model is not None else runtime_versions()
            if _state(root) != candidate or current != versions:
                raise QualificationUnavailable("qualification_source_changed")
            blobs = BuildEvidenceStore(destination / "certificates")
            # Raw XML remains in the private run directory. The protected report
            # pins its bytes and exact case set, source, runtime and role split.
            report = blobs.write_report(
                json.dumps(
                    {
                        "purpose": "PUBLIC_BASH_RUNTIME_ONLY",
                        "candidate_commit": candidate,
                        "runtime_versions": versions,
                        "cases": observations,
                        "raw_junit_sha256": hashlib.sha256(raw).hexdigest(),
                        "native_auth_role": "trusted-host-process",
                        "tool_role": "secret-free-OS-boundary",
                        "release_gate": "NOT_EVALUATED",
                        "owner_acceptance": "NOT_GRANTED",
                    },
                    sort_keys=True,
                ).encode()
            )
            expires = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
            certificate = {
                "schema_version": 1,
                "profile": "PERSONAL_SANDBOX",
                "verdict": "PASS",
                "runtime_versions": versions,
                "candidate_commit": candidate,
                "allowed_actions": ACTIONS,
                "expires_at": expires,
                "cases": [
                    {"case_id": case, "verdict": "PASS", "execution_mode": "OS_BOUNDARY", "report_sha256": report}
                    for case in ("AOS-008-TC03", "AOS-010-TC03")
                ],
                "scope": "PUBLIC_BASH_RUNTIME_ONLY_NO_PROJECT_GRANT_OR_RELEASE_PROMOTION",
            }
            digest = blobs.write_report(json.dumps(certificate, sort_keys=True).encode())
            CertificateStore(blobs.root, versions).validate(
                TrustAxis(
                    version=1,
                    profile="PERSONAL_SANDBOX",
                    allowed_actions=ACTIONS,
                    runtime_certificate_sha256=digest,
                )
            )
            result: dict[str, object] = {
                "status": "PASS",
                "scope": "PUBLIC_BASH_RUNTIME_ONLY",
                "candidate_commit": candidate,
                "certificate_sha256": digest,
                "expires_at": expires,
                "cases": len(observations),
                "release_gate": "NOT_EVALUATED",
            }
            _atomic(journal, result)
            _atomic(destination / "latest.json", {**result, "run": run.name})
            return result
        except (Exception, KeyboardInterrupt) as error:
            reason = (
                str(error)
                if isinstance(error, QualificationUnavailable)
                else "qualification_interrupted_or_unavailable"
            )
            if process is not None and process.poll() is None:
                try:
                    _stop(process)
                except (OSError, subprocess.SubprocessError, QualificationUnavailable):
                    reason = "qualification_cleanup_unconfirmed"
            result = {
                "status": "UNAVAILABLE",
                "reason": reason,
                "candidate_commit": candidate,
                "release_gate": "NOT_EVALUATED",
                "run": run.name,
            }
            _atomic(journal, result)
            _atomic(destination / "latest.json", result)
            return result
