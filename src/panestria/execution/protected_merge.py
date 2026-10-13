"""Local protected-ref CAS and durable effect witness, after kernel revalidation."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from panestria.execution.outbox import Confirmed, NoEffect, Unknown
from panestria.kernel.effects import DispatchClaim

_HEX = re.compile(r"^[0-9a-f]{40}$")
_REF = re.compile(r"^refs/heads/[A-Za-z0-9_/-]+$")


@dataclass(frozen=True)
class MergeSpec:
    destination: str
    base_commit: str
    candidate_commit: str
    candidate_tree: str
    evidence_sha256: str

    def validate(self) -> None:
        if not _REF.fullmatch(self.destination) or ".." in self.destination or "//" in self.destination:
            raise ValueError("invalid_destination_ref")
        if not all(_HEX.fullmatch(s) for s in (self.base_commit, self.candidate_commit, self.candidate_tree)):
            raise ValueError("invalid_git_object")
        if not re.fullmatch(r"[0-9a-f]{64}", self.evidence_sha256):
            raise ValueError("invalid_evidence_hash")


class ProtectedGitTarget:
    def __init__(
        self,
        protected_root: Path,
        repository: Path,
        revalidate: Callable[[DispatchClaim], MergeSpec],
        lookup: Callable[[DispatchClaim], MergeSpec],
    ) -> None:
        self.root, self.repo = protected_root.resolve(), repository.resolve()
        if repository.is_symlink() or self.repo == self.root or not self.repo.is_relative_to(self.root):
            raise ValueError("protected_repository_scope")
        self.revalidate, self.lookup = revalidate, lookup
        if self._git(["rev-parse", "--is-bare-repository"]).stdout.strip() != "true":
            raise ValueError("protected_destination_must_be_bare")

    def _git(self, args: list[str], *, body: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HOME": str(self.root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_ALLOW_PROTOCOL": "file",
        }
        process = subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.fsmonitor=false",
                "--git-dir",
                str(self.repo),
                *args,
            ],
            input=body,
            text=True,
            capture_output=True,
            timeout=10,
            env=env,
            check=False,
        )
        if check and process.returncode:
            raise ValueError("protected_git_operation_failed")
        return process

    def _witness(self, claim: DispatchClaim) -> str:
        if not re.fullmatch(r"[0-9a-f-]{36}", claim.effect_id):
            raise ValueError("invalid_effect_identity")
        return f"refs/panestria/effects/{claim.effect_id}"

    def dispatch(self, claim: DispatchClaim) -> str:
        spec = self.revalidate(claim)  # Current scope/policy/checkset/expiry; no model-approved boolean.
        spec.validate()
        if claim.target != f"{spec.destination}@{spec.candidate_commit}":
            raise ValueError("merge_target_mismatch")
        actual_tree = self._git(["rev-parse", "--verify", f"{spec.candidate_commit}^{{tree}}"]).stdout.strip()
        if actual_tree != spec.candidate_tree:
            raise ValueError("candidate_tree_mismatch")
        ancestor = self._git(["merge-base", "--is-ancestor", spec.base_commit, spec.candidate_commit], check=False)
        if ancestor.returncode:
            raise ValueError("candidate_not_based_on_destination")
        witness = self._witness(claim)
        # Git performs both ref updates as one transaction. A lost response can be
        # attributed to this effect even if another approved merge later moves HEAD.
        transaction = (
            f"start\nupdate {spec.destination} {spec.candidate_commit} {spec.base_commit}\n"
            f"create {witness} {spec.candidate_commit}\nprepare\ncommit\n"
        )
        self._git(["update-ref", "--stdin"], body=transaction)
        return f"git-effect:{claim.effect_id}:{spec.candidate_commit}:{spec.evidence_sha256}"

    def query(self, claim: DispatchClaim) -> Confirmed | NoEffect | Unknown:
        # Historical lookup does not demand that an already applied action's old
        # approval is still live. It must match the immutable effect fingerprint.
        spec = self.lookup(claim)
        spec.validate()
        if claim.target != f"{spec.destination}@{spec.candidate_commit}":
            return Unknown("merge_target_mismatch")
        found = self._git(["rev-parse", "--verify", self._witness(claim)], check=False)
        if found.returncode == 0:
            if found.stdout.strip() != spec.candidate_commit:
                return Unknown("effect_witness_mismatch")
            return Confirmed(f"git-effect:{claim.effect_id}:{spec.candidate_commit}:{spec.evidence_sha256}")
        current = self._git(["rev-parse", "--verify", spec.destination], check=False)
        if current.returncode == 0 and current.stdout.strip() == spec.base_commit:
            return NoEffect()
        return Unknown("destination_changed_without_effect_witness")
