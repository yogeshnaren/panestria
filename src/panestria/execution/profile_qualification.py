"""Fixed, actual synthetic OS-key/CPU HTTP observations; no supplied report import."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from panestria.execution.native_qualification import QualificationUnavailable, _state, _stop
from panestria.execution.proposal_demo import _atomic, _lock, _private
from panestria.kernel.build import BuildEvidenceStore
from panestria.memory.keys import KeyStoreUnavailable
from panestria.memory.profile_runtime import NODES, SCOPE, ProfileQualification, runtime_inputs, validate_junit


def qualify_profiles(directory: Path, cache: Path, *, synthetic_local_smoke: bool) -> dict[str, object]:
    if synthetic_local_smoke is not True:
        raise QualificationUnavailable("explicit_synthetic_local_smoke_required")
    root = Path(__file__).resolve().parents[3]
    candidate = _state(root)
    if not cache.is_absolute() or cache.resolve() != cache or not cache.is_dir():
        raise QualificationUnavailable("existing_absolute_model_cache_required")
    if {p.name for p in cache.iterdir()} != {"blobs", "manifests"}:
        raise QualificationUnavailable("dedicated_model_cache_required")
    if not directory.is_absolute() or directory.resolve() != directory:
        raise QualificationUnavailable("private_absolute_qualification_directory_required")
    if directory.is_relative_to(cache) or cache.is_relative_to(directory):
        raise QualificationUnavailable("profile_qualification_cache_overlap")
    inputs = runtime_inputs()
    destination = _private(directory)
    with _lock(destination / "qualification.lock"):
        run = _private(destination / ("run-" + uuid4().hex))
        journal, xml, log = run / "result.json", run / "raw.xml", run / "pytest.log"
        _atomic(journal, {"status": "STARTED", "candidate_commit": candidate, "runtime_inputs": inputs})
        env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin:" + str(Path(sys.executable).parent),
            "HOME": str(Path.home()),
            "LANG": "C.UTF-8",
            "UV_OFFLINE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PANESTRIA_PROFILE_TEST_MODEL_CACHE": str(cache),
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
                deadline = time.monotonic() + 240
                while process.poll() is None:
                    if time.monotonic() >= deadline or log.stat().st_size > 1024 * 1024:
                        _stop(process)
                        raise QualificationUnavailable("profile_qualification_timeout_or_output_limit")
                    time.sleep(0.1)
            if process.returncode:
                raise QualificationUnavailable("profile_qualification_cases_failed")
            raw = xml.read_bytes()
            validate_junit(raw, candidate)
            if _state(root) != candidate or runtime_inputs() != inputs:
                raise QualificationUnavailable("profile_qualification_runtime_changed")
            blobs = BuildEvidenceStore(destination / "certificates")
            raw_sha = blobs.write_report(raw)
            now = datetime.now(UTC)
            proof = ProfileQualification(
                candidate_commit=candidate,
                runtime_inputs=inputs,
                observed_at=now,
                expires_at=now + timedelta(hours=24),
                raw_junit_sha256=raw_sha,
                cases=NODES,
            )
            digest = blobs.write_report(proof.model_dump_json().encode())
            result: dict[str, object] = {
                "status": "PASS",
                "scope": SCOPE,
                "candidate_commit": candidate,
                "qualification_directory": str(blobs.root),
                "qualification_sha256": digest,
                "raw_junit_sha256": hashlib.sha256(raw).hexdigest(),
                "expires_at": proof.expires_at.isoformat(),
                "release_gate": "NOT_EVALUATED",
            }
        except (Exception, KeyboardInterrupt) as error:
            reason = str(error) if isinstance(error, QualificationUnavailable) else "profile_qualification_unavailable"
            if isinstance(error, KeyStoreUnavailable):
                reason = error.code
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
            }
        _atomic(journal, result)
        _atomic(destination / "latest.json", {**result, "run": run.name})
        return result
