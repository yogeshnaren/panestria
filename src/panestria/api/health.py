"""Typed liveness and bounded readiness.

``/healthz`` reports process liveness only. ``/readyz`` reports probe facts.
This slice has no executor, so a probe cannot make executor status ready.

Probe policy:

- At most one forked child runs the probe. A second poll returns ``probe_busy``
  and does not queue another child.
- The child is started when the service is created. Request threads send a job
  over a pipe; they do not create a thread per poll.
- A child that misses the deadline is killed with ``SIGKILL`` and reaped.
  ``shutdown()`` also finishes within ``PROBE_SHUTDOWN_BUDGET_SECONDS`` (1s),
  which is the extra time a timed-out readiness call may spend after the deadline.
- Public reason codes are the finite set ``PUBLIC_HEALTH_REASONS``. Any other
  probe text is replaced with ``probe_failed`` and is not copied into the response.
- Without ``os.fork``, readiness does not run the probe in-process. It reports
  ``probe_failed``.
"""

from __future__ import annotations

import atexit
import os
import select
import signal
import threading
import time
from datetime import datetime, timezone
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from panestria import package_version
from panestria.config import PUBLIC_HEALTH_REASONS, ProfileRejected, ValidatedSettings

DependencyName = Literal["database", "executor"]
DependencyState = Literal["ready", "unavailable", "degraded", "not_configured"]
ReadinessState = Literal["ready", "not_ready", "degraded"]
PublicReason = Literal[
    "capacity_unknown",
    "database_unavailable",
    "deadline_exceeded",
    "not_implemented",
    "not_probed",
    "probe_busy",
    "probe_failed",
    "ready",
]
_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
PROBE_SHUTDOWN_BUDGET_SECONDS = 1.0
_MAX_RESULT_BYTES = 4096


class SecretBearingOutputRejected(Exception):
    """Serialized health output contained configured secret material."""

    code = "secret_bearing_output_rejected"
    message = "response rejected because it contained configured secret material"
    retryable = False

    def __init__(self) -> None:
        super().__init__(self.message)


class ProbeCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: DependencyName
    status: DependencyState
    reason: str = Field(max_length=256)


class ProbeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    checks: list[ProbeCheck]


class Liveness(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    status: Literal["live"]
    version: str
    profile: Literal["SYNTHETIC_DEV"]


class DependencyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: DependencyName
    status: DependencyState
    reason: PublicReason


class Readiness(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1]
    status: ReadinessState
    checks: list[DependencyCheck]


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: Literal["secret_bearing_output_rejected"]
    message: Literal["response rejected because it contained configured secret material"]
    correlation_id: str = Field(pattern=_UUID)
    retryable: Literal[False]


class ReadinessProbe(Protocol):
    def __call__(self, deadline: datetime) -> ProbeObservation: ...


class _ProbeSupervisor:
    """One killable child for an uncooperative probe. No per-poll thread."""

    def __init__(self, probe: ReadinessProbe) -> None:
        self._probe = probe
        self._lock = threading.Lock()
        self._busy = False
        self._closed = False
        self._pid: int | None = None
        self._to_child: int | None = None
        self._from_child: int | None = None
        self._generation = 0
        atexit.register(self.shutdown)
        self._start_locked()

    def run(self, deadline: datetime, remaining: float) -> ProbeObservation | Literal["deadline", "busy"] | None:
        with self._lock:
            if self._closed:
                return None
            if self._busy:
                return "busy"
            if not self._alive_locked():
                self._start_locked()
            if self._pid is None or self._to_child is None or self._from_child is None:
                return None
            self._busy = True
            generation = self._generation
            pid = self._pid
            to_child = self._to_child
            from_child = self._from_child
        try:
            try:
                _write_all(to_child, (deadline.isoformat() + "\n").encode())
            except OSError:
                self._kill_generation(generation, pid)
                return None
            line = _read_line(from_child, remaining)
            if line is None:
                self._kill_generation(generation, pid)
                return "deadline"
            if line == b"ERR" or not line.startswith(b"OK "):
                return None
            try:
                return ProbeObservation.model_validate_json(line[3:])
            except ValidationError:
                return None
        finally:
            with self._lock:
                self._busy = False

    def shutdown(self) -> None:
        started = time.monotonic()
        with self._lock:
            pid = self._pid
            generation = self._generation
            self._closed = True
        if pid is not None:
            _signal_and_reap(pid, max(0.0, PROBE_SHUTDOWN_BUDGET_SECONDS - (time.monotonic() - started)))
        with self._lock:
            if self._generation == generation:
                self._pid = None
                self._close_fds_locked()

    def _start_locked(self) -> None:
        if not hasattr(os, "fork") or self._closed:
            return
        self._close_fds_locked()
        parent_read, child_write = os.pipe()
        child_read, parent_write = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(parent_read)
                os.close(parent_write)
                _child_loop(child_read, child_write, self._probe)
            finally:
                os._exit(0)
        os.close(child_read)
        os.close(child_write)
        self._pid = pid
        self._to_child = parent_write
        self._from_child = parent_read
        self._generation += 1

    def _alive_locked(self) -> bool:
        if self._pid is None:
            return False
        try:
            got, _status = os.waitpid(self._pid, os.WNOHANG)
        except ChildProcessError:
            self._pid = None
            return False
        if got == 0:
            return True
        self._pid = None
        return False

    def _kill_generation(self, generation: int, pid: int) -> None:
        _signal_and_reap(pid, PROBE_SHUTDOWN_BUDGET_SECONDS)
        with self._lock:
            if self._generation == generation and self._pid == pid:
                self._pid = None
                self._close_fds_locked()

    def _close_fds_locked(self) -> None:
        for fd in (self._to_child, self._from_child):
            if fd is None:
                continue
            try:
                os.close(fd)
            except OSError:
                pass
        self._to_child = None
        self._from_child = None


def _child_loop(read_fd: int, write_fd: int, probe: ReadinessProbe) -> None:
    while True:
        line = _read_line_blocking(read_fd, 256)
        if line is None or line == b"STOP":
            return
        try:
            deadline = datetime.fromisoformat(line.decode())
            result = probe(deadline)
            if not isinstance(result, ProbeObservation):
                result = ProbeObservation.model_validate(result)
            payload = b"OK " + result.model_dump_json().encode()
        except Exception:
            payload = b"ERR"
        try:
            _write_all(write_fd, payload + b"\n")
        except OSError:
            return


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


def _read_line(fd: int, timeout: float) -> bytes | None:
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    total = 0
    while total <= _MAX_RESULT_BYTES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            readable, _, _ = select.select([fd], [], [], remaining)
        except (OSError, ValueError):
            return b""
        if not readable:
            return None
        try:
            chunk = os.read(fd, 256)
        except OSError:
            return b""
        if not chunk:
            break
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _read_line_blocking(fd: int, limit: int) -> bytes | None:
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        try:
            chunk = os.read(fd, 64)
        except OSError:
            return None
        if not chunk:
            return None
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
    return None


def _signal_and_reap(pid: int, budget: float) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + max(0.0, budget)
    while True:
        try:
            got, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return
        if got == pid:
            return
        if time.monotonic() >= deadline:
            return
        time.sleep(0.01)


class HealthService:
    def __init__(self, settings: ValidatedSettings, readiness_probe: ReadinessProbe) -> None:
        self._settings = settings
        self._probe = readiness_probe
        self._supervisor = _ProbeSupervisor(readiness_probe)

    def liveness(self) -> Liveness:
        body = Liveness(
            schema_version=1,
            status="live",
            version=package_version(),
            profile=self._settings.profile,
        )
        self._reject_secret_bearing(body.model_dump_json())
        return body

    def readiness(self, deadline: datetime) -> Readiness:
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            raise ProfileRejected("invalid_deadline", "deadline must be timezone-aware")
        remaining = (deadline.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            return self._bounded_not_ready("deadline_exceeded")
        observed = self._supervisor.run(deadline, remaining)
        if observed == "deadline":
            return self._bounded_not_ready("deadline_exceeded")
        if observed == "busy":
            return self._bounded_not_ready("probe_busy")
        if not isinstance(observed, ProbeObservation):
            return self._bounded_not_ready("probe_failed")
        database = _public_database(observed)
        if database is None:
            return self._bounded_not_ready("probe_failed")
        body = Readiness(
            schema_version=1,
            status=_overall(database.status),
            checks=[
                database,
                DependencyCheck(name="executor", status="not_configured", reason="not_implemented"),
            ],
        )
        self._reject_secret_bearing(body.model_dump_json())
        return body

    def shutdown(self) -> None:
        self._supervisor.shutdown()

    def _bounded_not_ready(self, reason: PublicReason) -> Readiness:
        body = Readiness(
            schema_version=1,
            status="not_ready",
            checks=[
                DependencyCheck(name="database", status="unavailable", reason=reason),
                DependencyCheck(name="executor", status="not_configured", reason="not_implemented"),
            ],
        )
        self._reject_secret_bearing(body.model_dump_json())
        return body

    def _reject_secret_bearing(self, payload: str) -> None:
        for secret in self._settings.secret_material():
            if secret and secret in payload:
                raise SecretBearingOutputRejected()


def _public_database(observation: ProbeObservation) -> DependencyCheck | None:
    databases = [check for check in observation.checks if check.name == "database"]
    if len(databases) != 1:
        return None
    found = databases[0]
    reason: PublicReason = found.reason if found.reason in PUBLIC_HEALTH_REASONS else "probe_failed"
    try:
        return DependencyCheck(name="database", status=found.status, reason=reason)
    except ValidationError:
        return None


def _overall(database_status: DependencyState) -> ReadinessState:
    if database_status == "degraded":
        return "degraded"
    return "not_ready"


def default_readiness_probe(deadline: datetime) -> ProbeObservation:
    """Report the database as unobserved. This probe does not open a connection."""
    del deadline
    return ProbeObservation(
        checks=[ProbeCheck(name="database", status="unavailable", reason="not_probed")]
    )


def secret_rejection_body(correlation_id: str) -> ErrorBody:
    return ErrorBody(
        code="secret_bearing_output_rejected",
        message="response rejected because it contained configured secret material",
        correlation_id=correlation_id,
        retryable=False,
    )
