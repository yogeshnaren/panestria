"""Public search needs its own source/configuration-bound OS qualification.

A native Build certificate, a fixture report or a policy privacy grant alone
cannot enable it. Issuing a live public-search certificate is a separate operator
qualification; no certificate is minted by admission or transport code.
"""

import hashlib
import json
import os
import re

from panestria.contracts.policy import TrustAxis
from panestria.policy.profiles import CertificateRejected, CertificateStore
from panestria.policy.research import RESEARCH_CASES, RESEARCH_PROFILE, RESEARCH_PURPOSE

SEARCH_PROFILE = "public-search-v1"


class PublicSearchCertificateStore(CertificateStore):
    def validate(self, trust: TrustAxis) -> None:
        if (
            self.root.is_symlink()
            or not self.root.is_dir()
            or self.root.stat().st_uid != os.getuid()
            or self.root.stat().st_mode & 0o077
        ):
            raise CertificateRejected("private_public_search_certificate_store_required")
        super().validate(trust)
        if trust.profile == "SYNTHETIC_DEV":
            raise CertificateRejected("public_search_runtime_uncertified")
        try:
            assert trust.runtime_certificate_sha256 is not None
            body = json.loads((self.root / trust.runtime_certificate_sha256).read_bytes())
            profile = self.runtime_versions.get("profile")
            if (profile, body.get("purpose")) not in (
                (SEARCH_PROFILE, "PUBLIC_SEARCH_RUNTIME_ONLY"),
                (RESEARCH_PROFILE, RESEARCH_PURPOSE),
            ):
                raise CertificateRejected("public_search_runtime_uncertified")
            for identifier in RESEARCH_CASES if profile == RESEARCH_PROFILE else ("AOS-019-TC04",):
                case = next(case for case in body["cases"] if case["case_id"] == identifier)
                digest = case["report_sha256"]
                if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    raise CertificateRejected("public_search_report_invalid")
                report = self.root / digest
                if (
                    case["verdict"] != "PASS"
                    or case["execution_mode"] != "OS_BOUNDARY"
                    or report.is_symlink()
                    or not report.is_file()
                    or report.stat().st_size > 10_000_000
                    or hashlib.sha256(report.read_bytes()).hexdigest() != digest
                ):
                    raise CertificateRejected("public_search_runtime_uncertified")
        except (KeyError, TypeError, ValueError, OSError, StopIteration) as exc:
            raise CertificateRejected("public_search_certificate_invalid") from exc
