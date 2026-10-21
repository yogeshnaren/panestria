"""Owner-only metadata collection and bounded private account-link evidence."""

import json
import re
from typing import TYPE_CHECKING, Any

from panestria.brokers.harness.account_profile import NativeAccountProbe
from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256
from panestria.brokers.harness.cli_profile import BinaryPin, NativeProbeUnavailable
from panestria.execution.proposal_demo import _lock, _private
from panestria.kernel.background_account import BackgroundAccountService
from panestria.kernel.build import BuildEvidenceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork

if TYPE_CHECKING:
    from panestria.execution.owner_build import OwnerBuild


def account_reports(owner: "OwnerBuild") -> BuildEvidenceStore:
    _private(owner.settings.root)
    return BuildEvidenceStore(owner.settings.root / "account-observations")


def probe_account(owner: "OwnerBuild", item_id: str) -> dict[str, Any]:
    reports = account_reports(owner)
    with owner.connect() as c:
        service, uow = BackgroundAccountService(reports), UnitOfWork(c)
        binding = service.binding(uow, owner.actor, item_id)
    digest = collect_account(owner, binding.request.policy.quota_windows[0].account_ref)
    observed = BackgroundAccountService(reports).observation(digest)
    with owner.connect() as c:
        link = BackgroundAccountService(reports).prepare(UnitOfWork(c), owner.actor, item_id, digest)
    return {
        "status": "REVIEW_ONLY",
        "observation": observed.model_dump(mode="json"),
        "observation_sha256": digest,
        "link": link.model_dump(mode="json"),
        "link_sha256": link.sha256(),
        "billing_verified": False,
        "inference_verified": False,
        "execution_authority": "NONE",
    }


def collect_account(owner: "OwnerBuild", account_ref: str) -> str:
    reports = account_reports(owner)
    try:
        observed = NativeAccountProbe(owner.settings.skills_archive).inspect(
            BinaryPin(owner.settings.native_binary, PINNED_BINARY_SHA256),
            owner.settings.native_config,
            owner_id=owner.actor.owner_id,
            project_id=owner.actor.project_id,
            account_ref=account_ref,
        )
    except NativeProbeUnavailable as exc:
        raise KernelDenied(exc.code) from None
    raw = json.dumps(
        observed.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    with _lock(owner.settings.root / "account-observations.lock"):
        entries = list(reports.root.iterdir())
        if len(entries) >= 512 or any(
            re.fullmatch(r"[0-9a-f]{64}", p.name) is None or p.is_symlink() or not p.is_file() for p in entries
        ):
            raise KernelDenied("background_account_archive_limit_or_unexpected_entry")
        if sum(p.stat().st_size for p in entries) + len(raw) > 1024 * 1024:
            raise KernelDenied("background_account_archive_limit")
        digest = reports.write_report(raw)
    return digest
