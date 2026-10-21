"""Profile-specific, expiring local observations; never a project/release grant."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretBytes, ValidationError, model_validator

from panestria.config_local import LocalApplicationRejected, read_private
from panestria.inference.runtime import IMAGE, MODEL, MODEL_DIGEST
from panestria.memory.keys import KeyStoreUnavailable, ProfileKeyHandle, ProfileKeyStore

ROOT = Path(__file__).resolve().parents[3]
SCOPE: Literal["ISOLATED_OS_KEYS_CPU_PROFILE_ASK_ONLY"] = "ISOLATED_OS_KEYS_CPU_PROFILE_ASK_ONLY"
NODES = (
    "tests/integration/test_profile_keys_live.py::test_isolated_secret_service_backend",
    "tests/integration/test_profile_runtime_live.py::test_actual_profile_runtime_boundary",
)
MODES = ("ACTUAL_ISOLATED_OS_SECRET_SERVICE", "ACTUAL_ISOLATED_OS_STORE_LOCAL_MODEL_LOOPBACK_HTTP")


@lru_cache(maxsize=4096)
def _file_hash(path: str, identity: tuple[int, ...]) -> str:
    # Cache public runtime bytes only. A changed inode/size/mtime/ctime invalidates
    # the entry; no 3GB library rehash on every profile key load.
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _hash(path: Path) -> str:
    info = path.stat()
    if not path.is_file():
        raise ValueError
    return _file_hash(str(path), (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))


def runtime_inputs() -> dict[str, str]:
    """Observe source, installed versions, OS boot and actual trusted binaries.

    The model's full blob hashes and effective Docker isolation are separately
    checked by ModelRuntime at each startup, never downloaded here. This is local
    operator evidence, not a signature or defense against a compromised host.
    """
    try:
        sources = [*sorted((ROOT / "src/panestria").rglob("*.py")), ROOT / "uv.lock"]
        sources += [ROOT / node.split("::")[0] for node in NODES]
        sources += [ROOT / "tests/fixtures" / name for name in ("profile_keyring_probe.py", "profile_runtime_probe.py")]
        sources += [ROOT / "tests/integration/conftest.py", ROOT / "tests/integration/test_ask_kernel.py"]
        source = hashlib.sha256()
        for path in sources:
            source.update(str(path.relative_to(ROOT)).encode() + b"\0" + _hash(path).encode())
        tools = {}
        for name in ("dbus-run-session", "gnome-keyring-daemon", "docker"):
            value = shutil.which(name)
            if value is None:
                raise ValueError
            tools[name] = _hash(Path(value).resolve())
        tools["python"] = _hash(Path(sys.executable).resolve())
        tools["ollama"] = _hash(Path("/usr/local/bin/ollama").resolve())
        libraries = Path("/usr/local/lib/ollama")
        if not libraries.is_dir():
            raise ValueError
        entries = sorted(libraries.rglob("*"))
        if not 1 <= len(entries) <= 4096:
            raise ValueError
        for path in entries:
            if path.is_file():
                tools["ollama/" + str(path.relative_to(libraries))] = _hash(path.resolve())
        versions = {d.metadata["Name"].lower(): d.version for d in importlib.metadata.distributions()}
        system = {
            "tools": tools,
            "installed_versions": versions,
            "kernel": platform.release(),
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "uid": os.getuid(),
        }
        return {
            "source_sha256": source.hexdigest(),
            "system_sha256": hashlib.sha256(json.dumps(system, sort_keys=True).encode()).hexdigest(),
            "image": IMAGE,
            "model": MODEL,
            "model_manifest_sha256": MODEL_DIGEST,
        }
    except (OSError, ValueError, KeyError):
        raise KeyStoreUnavailable("profile_runtime_inputs_unavailable") from None


class ProfileQualification(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal[1] = 1
    scope: Literal["ISOLATED_OS_KEYS_CPU_PROFILE_ASK_ONLY"] = SCOPE
    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    runtime_inputs: dict[str, str]
    observed_at: datetime
    expires_at: datetime
    raw_junit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[str, str]
    release_gate: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"

    @model_validator(mode="after")
    def bounded(self) -> ProfileQualification:
        if (
            self.observed_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or not timedelta(0) < self.expires_at - self.observed_at <= timedelta(hours=24)
            or self.cases != NODES
        ):
            raise ValueError("invalid_profile_qualification")
        return self


def validate_junit(raw: bytes, candidate: str) -> None:
    import xml.etree.ElementTree as ET

    try:
        if len(raw) > 32768 or b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
            raise ValueError
        cases = list(ET.fromstring(raw).iter("testcase"))
        expected = {
            tuple(node.replace("/", ".").replace(".py::", "::").split("::")): mode
            for node, mode in zip(NODES, MODES, strict=True)
        }
        seen = set()
        for case in cases:
            identity = (str(case.get("classname")), str(case.get("name")))
            if identity in seen or identity not in expected:
                raise ValueError
            seen.add(identity)
            props = {p.get("name"): p.get("value") for p in case.iter("property")}
            if (
                any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
                or props.get("candidate_commit") != candidate
                or props.get("worktree_state") != "clean"
                or props.get("execution_mode") != expected[identity]
                or "TEST_FIXTURE_NOT_LIVE" in json.dumps(props)
            ):
                raise ValueError
        if seen != set(expected):
            raise ValueError
    except (ValueError, TypeError, ET.ParseError):
        raise KeyStoreUnavailable("profile_qualification_evidence_incomplete") from None


class QualifiedProfileKeys:
    """Existing exact key handles only; expiry/source changes deny cleartext use.

    Suppression requires no key and remains available after qualification expires.
    No key provisioning, collection creation/unlock, certificate renewal or fallback.
    """

    def __init__(self, root: Path, digest: str, handles: tuple[ProfileKeyHandle, ...], keys: ProfileKeyStore) -> None:
        self.root, self.digest, self.handles, self.keys = root, digest, handles, keys

    def _blob(self, digest: str) -> bytes:
        import re

        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError
        if self.root.resolve() != self.root or not self.root.is_dir():
            raise ValueError
        info = self.root.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError
        raw = read_private(self.root / digest, 32768)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError
        return raw

    def validate(self) -> ProfileQualification:
        try:
            proof = ProfileQualification.model_validate_json(self._blob(self.digest))
            now = datetime.now(UTC)
            if not proof.observed_at <= now < proof.expires_at or proof.runtime_inputs != runtime_inputs():
                raise ValueError
            validate_junit(self._blob(proof.raw_junit_sha256), proof.candidate_commit)
            return proof
        except (ValueError, OSError, LocalApplicationRejected, ValidationError):
            raise KeyStoreUnavailable("profile_qualification_invalid_or_expired") from None

    def load(self, handle: ProfileKeyHandle) -> SecretBytes:
        if handle not in self.handles:
            raise KeyStoreUnavailable("profile_key_not_selected")
        self.validate()
        secret = self.keys.load(handle)
        self.validate()
        return secret
