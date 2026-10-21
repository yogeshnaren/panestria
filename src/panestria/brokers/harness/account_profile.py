"""Reuse pinned metadata transport, retaining only scoped pseudonymous identity.

No token file, prompt, private endpoint, raw auth output or billing setting is
read by this collector. The CLI can access its own existing private login.
"""

import json
import os
import re
from pathlib import Path
from uuid import UUID

from panestria.brokers.harness.cli_profile import (
    BinaryPin,
    CliProfileProbe,
    MetadataOutput,
    MetadataRunner,
    NativeProbeUnavailable,
    _auth_pairs,
    _invalid_number,
    run_metadata,
)
from panestria.contracts.build import canonical_sha256
from panestria.contracts.native_account import NativeAccountObservation
from panestria.contracts.quota import QuotaScope


class NativeAccountProbe:
    def __init__(self, archive: Path, *, runner: MetadataRunner = run_metadata) -> None:
        self.archive, self.runner = archive, runner

    def inspect(
        self, pin: BinaryPin, config: Path, *, owner_id: str, project_id: str, account_ref: str
    ) -> NativeAccountObservation:
        # Validate local scope before invoking even metadata-only commands.
        scope = QuotaScope(provider="claude-subscription", account_ref=account_ref, window_ref="session")
        salt = {"owner_id": owner_id, "project_id": project_id, "account_ref": scope.account_ref}
        for value in (owner_id, project_id):
            if str(UUID(value)) != value or UUID(value).version != 4:
                raise ValueError("native_account_scope_invalid")
        redacted: dict[str, str] = {}

        def collect(
            binary_fd: int,
            args: tuple[str, ...],
            cwd: Path,
            env: dict[str, str],
            deadline: float,
            config_fd: int | None,
        ) -> MetadataOutput:
            result = self.runner(binary_fd, args, cwd, env, deadline, config_fd)
            if args[-3:] != ("auth", "status", "--json") or config_fd is None:
                return result
            try:
                body = json.loads(result.stdout, object_pairs_hook=_auth_pairs, parse_constant=_invalid_number)
            except (ValueError, UnicodeError, RecursionError):
                raise NativeProbeUnavailable("auth_metadata_invalid") from None
            # The original probe separately verifies auth mode, private profile,
            # return code, pinned executable and unchanged held handles.
            if not isinstance(body, dict) or body.get("subscriptionType") not in ("pro", "max"):
                raise NativeProbeUnavailable("auth_metadata_invalid")
            identifier = body.get("accountId")
            basis = "ACCOUNT_ID"
            try:
                if not isinstance(identifier, str) or str(UUID(identifier)) != identifier:
                    raise ValueError
            except ValueError:
                identifier, basis = body.get("email"), "EMAIL"
                if (
                    not isinstance(identifier, str)
                    or not 3 <= len(identifier) <= 254
                    or re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", identifier)
                    is None
                ):
                    raise NativeProbeUnavailable("auth_metadata_invalid") from None
                identifier = identifier.lower()
            info = os.fstat(config_fd)
            redacted.update(
                identity_sha256=canonical_sha256({**salt, "basis": basis, "identity": identifier}),
                identity_basis=basis,
                profile_sha256=canonical_sha256(
                    {**salt, "directory": str(config), "device": info.st_dev, "inode": info.st_ino}
                ),
                subscription_type=body["subscriptionType"],
            )
            # Raw output is not retained on this object or placed in a report.
            return result

        compatibility = CliProfileProbe(self.archive, runner=collect).inspect(pin, config)
        if compatibility.status != "INSPECTED" or not redacted:
            raise NativeProbeUnavailable("auth_metadata_invalid")
        return NativeAccountObservation.model_validate(
            {
                **salt,
                **redacted,
                "observed_at": compatibility.observed_at,
                "binary_sha256": pin.sha256,
                "compatibility_sha256": canonical_sha256(compatibility.model_dump(mode="json")),
            }
        )
