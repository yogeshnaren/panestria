"""Narrow demo attestations are deliberately rejected by the general runtime store.

Only the fixed public demo controller installs this validator. It cannot certify
arbitrary repositories, private exports, native tools or the R1/G1 security gate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256
from panestria.contracts.native_proposal import PROFILE, PROMPT_SHA256
from panestria.contracts.policy import Action, TrustAxis
from panestria.kernel.build import BuildEvidenceStore
from panestria.policy.profiles import CertificateRejected, CertificateStore
from panestria.sandbox.profiles import DEFAULT_IMAGE

ASSETS = Path(__file__).with_name("demo_assets")
ACTIONS: list[Action] = ["read", "edit", "external-send", "merge"]
CASES = {"public-native-proposal": "NATIVE_NO_TOOLS", "public-apply": "OS_BOUNDARY", "public-verify": "OS_BOUNDARY"}


def runtime_versions() -> dict[str, str]:
    # A code edit invalidates this narrow attestation, including changes to the
    # parser, policy, controller, gateway, verifier or its reviewed assets.
    source = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*.py")):
        digest.update(str(path.relative_to(source)).encode() + b"\0" + path.read_bytes())
    return {
        "profile": PROFILE,
        "prompt_sha256": PROMPT_SHA256,
        "binary_sha256": PINNED_BINARY_SHA256,
        "source_sha256": digest.hexdigest(),
        "image": DEFAULT_IMAGE,
    }


class ProposalCertificateStore(CertificateStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root, runtime_versions())
        self.blobs = BuildEvidenceStore(root)

    def validate(self, trust: TrustAxis) -> None:
        if trust.profile == "SYNTHETIC_DEV":
            return super().validate(trust)
        try:
            if trust.profile != "PERSONAL_SANDBOX" or set(trust.allowed_actions) != set(ACTIONS):
                raise CertificateRejected("demo_scope_mismatch")
            digest = trust.runtime_certificate_sha256
            if digest is None:
                raise CertificateRejected("demo_unqualified")
            body = json.loads(self.blobs.read_blob(digest))
            expiry = datetime.fromisoformat(body["expires_at"])
            if (
                set(body) != {"purpose", "runtime_versions", "cases", "expires_at"}
                or body["purpose"] != PROFILE
                or body["runtime_versions"] != runtime_versions()
                or expiry.tzinfo is None
                or expiry <= datetime.now(UTC)
                or set(body["cases"]) != set(CASES)
            ):
                raise CertificateRejected("demo_attestation_mismatch")
            for key, mode in CASES.items():
                report = json.loads(self.blobs.read_blob(body["cases"][key]))
                if (report["case_id"], report["verdict"], report["execution_mode"], report["runtime_versions"]) != (
                    key,
                    "PASS",
                    mode,
                    body["runtime_versions"],
                ):
                    raise CertificateRejected("demo_attestation_not_live")
        except CertificateRejected:
            raise
        except Exception:
            raise CertificateRejected("demo_attestation_invalid") from None
