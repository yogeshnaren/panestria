"""Local HMAC signatures detect modification; manifests are content-addressed history."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from panestria.contracts.hardware import HardwareManifest


def _canonical(manifest: HardwareManifest) -> bytes:
    return json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()


class ManifestStore:
    def __init__(self, directory: Path, signing_key: bytes) -> None:
        if len(signing_key) < 32:
            raise ValueError("signing_key_too_short")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or directory.stat().st_mode & 0o077:
            raise ValueError("manifest_store_permissions")
        self.directory, self.key = directory, signing_key

    def write(self, manifest: HardwareManifest) -> str:
        body = _canonical(manifest)
        digest = hashlib.sha256(body).hexdigest()
        envelope = {"body": manifest.model_dump(mode="json"), "signature": hmac.digest(self.key, body, "sha256").hex()}
        path = self.directory / f"{digest}.json"
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            self.read(digest)
            return digest
        with os.fdopen(descriptor, "w") as stream:
            json.dump(envelope, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        return digest

    def read(self, digest: str) -> HardwareManifest:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("manifest_digest_invalid")
        path = self.directory / f"{digest}.json"
        if path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError("manifest_invalid")
        envelope = json.loads(path.read_bytes())
        manifest = HardwareManifest.model_validate_json(json.dumps(envelope["body"]))
        body = _canonical(manifest)
        if hashlib.sha256(body).hexdigest() != digest or not hmac.compare_digest(
            hmac.digest(self.key, body, "sha256").hex(), envelope["signature"]
        ):
            raise ValueError("manifest_signature_mismatch")
        return manifest

    def changes(self, old_digest: str, new_digest: str) -> tuple[str, ...]:
        before, after = self.read(old_digest).model_dump(), self.read(new_digest).model_dump()
        return tuple(key for key in before if key != "observed_at" and before[key] != after[key])
