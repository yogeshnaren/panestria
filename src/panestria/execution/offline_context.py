"""Exact original selected-context reconstruction and offline checking, never authority."""

import hashlib
import json
from pathlib import Path
from typing import Any

from panestria.contracts.invocation import InvocationBinding
from panestria.contracts.native_context import NativeContextManifest
from panestria.kernel.errors import KernelDenied
from panestria.verification.git_snapshot import SnapshotRejected, protected_git


def context_parts(index: int) -> tuple[str, str, str]:
    return f"native-context-{index}", f"native-binding-{index}", f"native-receipt-{index}"


def _manifest(binding: InvocationBinding, receipt: dict[str, Any]) -> NativeContextManifest:
    if (
        binding.kind != "native-proposal"
        or receipt.get("kind") != "admitted-native-build"
        or receipt.get("context_sha256") != binding.request_sha256
        or receipt.get("scope_sha256") != binding.scope.sha256()
    ):
        raise KernelDenied("offline_context_receipt_binding_mismatch")
    manifest = NativeContextManifest.model_validate_json(json.dumps(receipt["selected_context_manifest"]))
    if manifest.header.assignment is not None and manifest.header.assignment.task_id != str(binding.scope.task_id):
        raise KernelDenied("offline_context_assignment_mismatch")
    return manifest


def verify_context(binding: InvocationBinding, receipt: dict[str, Any], context: bytes) -> NativeContextManifest:
    try:
        manifest = _manifest(binding, receipt)
        if (
            len(context) > 16384
            or hashlib.sha256(context).hexdigest() != binding.request_sha256
            or NativeContextManifest.from_context(context.decode("utf-8")) != manifest
        ):
            raise ValueError("original_context_mismatch")
        return manifest
    except (KeyError, TypeError, ValueError, RecursionError):
        raise KernelDenied("offline_context_unavailable_or_mismatched") from None


def reconstruct_context(
    repository: Path, binding: InvocationBinding, receipt: dict[str, Any], *, deadline: float
) -> bytes:
    try:
        manifest = _manifest(binding, receipt)
        contents = {
            f.path: protected_git(
                repository,
                ("cat-file", "blob", f"{manifest.header.source_tree}:{f.path}"),
                limit=f.size_bytes + 1024,
                deadline=deadline,
            )
            for f in manifest.files
        }
        context = manifest.render(contents)
        verify_context(binding, receipt, context)
        return context
    except (KeyError, TypeError, ValueError, RecursionError, SnapshotRejected):
        raise KernelDenied("offline_context_unavailable_or_mismatched") from None
