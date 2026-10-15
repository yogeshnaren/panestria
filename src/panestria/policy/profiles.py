"""Security certificates are read from a protected, content-addressed store."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from panestria.contracts.policy import TrustAxis


class CertificateRejected(Exception):
    pass


class CertificateStore:
    def __init__(self, root: Path, runtime_versions: dict[str, str]) -> None:
        self.root = root.resolve()
        self.runtime_versions = dict(runtime_versions)

    def validate(self, trust: TrustAxis) -> None:
        if trust.profile == "SYNTHETIC_DEV":
            if set(trust.allowed_actions) - {"read", "edit", "merge"}:
                raise CertificateRejected("synthetic_capability_denied")
            return
        digest = trust.runtime_certificate_sha256
        if digest is None or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise CertificateRejected("runtime_uncertified")
        path = self.root / digest
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 256_000:
            raise CertificateRejected("certificate_missing")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise CertificateRejected("certificate_corrupt")
        try:
            body = json.loads(raw)
            cases = {entry["case_id"]: entry for entry in body["cases"]}
            expiry = datetime.fromisoformat(body["expires_at"])
            if (
                body["schema_version"] != 1
                or body["profile"] != trust.profile
                or body["verdict"] != "PASS"
                or body["runtime_versions"] != self.runtime_versions
                or expiry.tzinfo is None
                or expiry <= datetime.now(UTC)
                or not re.fullmatch(r"[0-9a-f]{40}", body["candidate_commit"])
                or not set(trust.allowed_actions).issubset(body["allowed_actions"])
            ):
                raise CertificateRejected("certificate_mismatch")
            for case in ("AOS-008-TC03", "AOS-010-TC03"):
                entry = cases[case]
                if entry["verdict"] != "PASS" or entry["execution_mode"] != "OS_BOUNDARY":
                    raise CertificateRejected("certificate_not_live")
                if not re.fullmatch(r"[0-9a-f]{64}", entry["report_sha256"]):
                    raise CertificateRejected("certificate_report_invalid")
                report = self.root / entry["report_sha256"]
                if (
                    report.is_symlink()
                    or not report.is_file()
                    or report.stat().st_size > 10_000_000
                    or hashlib.sha256(report.read_bytes()).hexdigest() != entry["report_sha256"]
                ):
                    raise CertificateRejected("certificate_report_corrupt")
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise CertificateRejected("certificate_invalid") from exc
