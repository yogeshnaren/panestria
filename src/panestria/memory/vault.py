"""Trusted local, opt-in ciphertext service; callers own the DB transaction."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, SecretBytes, ValidationError

from panestria.contracts.profile import ProfileDocument
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.keys import KeyStoreUnavailable, ProfileKeyHandle, ProfileKeyStore

_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class ProfileEnvelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    owner_id: str = Field(pattern=_UUID)
    project_id: str = Field(pattern=_UUID)
    profile_id: str = Field(pattern=_UUID)
    key_id: str = Field(pattern=_UUID)
    revision_id: str = Field(pattern=_UUID)
    version: int = Field(ge=1, le=1024)
    schema_version: Literal[1] = 1
    algorithm: Literal["A256GCM"] = "A256GCM"
    privacy_label: Literal["RESTRICTED"] = "RESTRICTED"
    consented_by: str = Field(pattern=_UUID)
    consent_ref: str = Field(pattern=_UUID)
    nonce: bytes = Field(min_length=12, max_length=12, repr=False)
    ciphertext: bytes = Field(min_length=17, max_length=32784, repr=False)
    ciphertext_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def aad(self) -> bytes:
        return _aad(self.model_dump(exclude={"nonce", "ciphertext", "ciphertext_sha256"}))


def _aad(identity: dict[str, object]) -> bytes:
    return json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class ProfileRef:
    profile_id: str
    revision_id: str
    revision: int
    row_version: int
    key_id: str
    ciphertext_sha256: str


class ProfileVault:
    def __init__(self, keys: ProfileKeyStore, *, enabled: bool = False) -> None:
        self.keys, self.enabled = keys, enabled

    def _enabled(self) -> None:
        if not self.enabled:
            raise KernelDenied("profile_disabled")

    def _handle(self, actor: Actor, handle: ProfileKeyHandle) -> None:
        self._enabled()
        if (handle.owner_id, handle.project_id) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")

    def _key(self, handle: ProfileKeyHandle) -> SecretBytes:
        try:
            secret = self.keys.load(handle)
        except KeyStoreUnavailable as exc:
            raise KernelDenied(exc.code) from None
        if len(secret.get_secret_value()) != 32:
            raise KernelDenied("key_material_invalid")
        return secret

    def _seal(
        self, actor: Actor, handle: ProfileKeyHandle, version: int, document: ProfileDocument, consent_ref: str
    ) -> ProfileEnvelope:
        identity = {
            **handle.model_dump(),
            "revision_id": str(uuid4()),
            "version": version,
            "schema_version": 1,
            "algorithm": "A256GCM",
            "privacy_label": "RESTRICTED",
            "consented_by": actor.owner_id,
            "consent_ref": consent_ref,
        }
        # SecretStr masks ordinary serialization. Only this explicit encryption
        # boundary unwraps values, then validates the complete bounded snapshot.
        raw = {
            **document.model_dump(mode="json"),
            "fields": {name: value.get_secret_value() for name, value in document.fields.items()},
        }
        payload = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        try:
            ProfileDocument.model_validate_json(payload)
            if len(payload) > 32768:
                raise ValueError
            # Validate routing metadata before touching a key.
            ProfileEnvelope(**identity, nonce=b"0" * 12, ciphertext=b"0" * 17, ciphertext_sha256="0" * 64)
        except (ValidationError, ValueError):
            raise KernelDenied("invalid_profile") from None
        key = self._key(handle)
        nonce = os.urandom(12)
        ciphertext = AESGCM(key.get_secret_value()).encrypt(nonce, payload, _aad(identity))
        return ProfileEnvelope(
            **identity, nonce=nonce, ciphertext=ciphertext, ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest()
        )

    def _store(self, uow: UnitOfWork, envelope: ProfileEnvelope) -> None:
        uow.execute(
            "INSERT INTO panestria.profile_revision (id,profile_id,owner_id,project_id,version,key_id,"
            "schema_version,algorithm,privacy_label,consented_by,consent_ref,nonce,ciphertext,ciphertext_sha256)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            tuple(
                getattr(envelope, field)
                for field in (
                    "revision_id",
                    "profile_id",
                    "owner_id",
                    "project_id",
                    "version",
                    "key_id",
                    "schema_version",
                    "algorithm",
                    "privacy_label",
                    "consented_by",
                    "consent_ref",
                    "nonce",
                    "ciphertext",
                    "ciphertext_sha256",
                )
            ),
        )

    @staticmethod
    def _ref(envelope: ProfileEnvelope, row_version: int) -> ProfileRef:
        return ProfileRef(
            envelope.profile_id,
            envelope.revision_id,
            envelope.version,
            row_version,
            envelope.key_id,
            envelope.ciphertext_sha256,
        )

    def create(
        self, uow: UnitOfWork, actor: Actor, handle: ProfileKeyHandle, document: ProfileDocument, *, consent_ref: str
    ) -> ProfileRef:
        self._handle(actor, handle)
        # Serialize the bounded project inventory without enumerating other scopes.
        project = uow.execute(
            "SELECT id FROM panestria.project WHERE id=%s AND owner_id=%s FOR UPDATE",
            (actor.project_id, actor.owner_id),
        ).fetchone()
        if project is None:
            raise KernelDenied("not_found")
        if (
            uow.execute(
                "SELECT id FROM panestria.profile WHERE id=%s AND owner_id=%s AND project_id=%s",
                (handle.profile_id, actor.owner_id, actor.project_id),
            ).fetchone()
            is not None
        ):
            raise KernelDenied("version_conflict")
        count = uow.execute(
            "SELECT count(*) FROM panestria.profile WHERE owner_id=%s AND project_id=%s",
            (actor.owner_id, actor.project_id),
        ).fetchone()
        if count is None or count[0] >= 32:
            raise KernelDenied("profile_capacity_reached")
        envelope = self._seal(actor, handle, 1, document, consent_ref)
        uow.execute(
            "INSERT INTO panestria.profile(id,owner_id,project_id) VALUES(%s,%s,%s)",
            (handle.profile_id, actor.owner_id, actor.project_id),
        )
        self._store(uow, envelope)
        return self._ref(envelope, 0)

    def revise(
        self,
        uow: UnitOfWork,
        actor: Actor,
        handle: ProfileKeyHandle,
        expected_version: int,
        document: ProfileDocument,
        *,
        consent_ref: str,
    ) -> ProfileRef:
        self._handle(actor, handle)
        row = uow.execute(
            "SELECT current_revision,row_version FROM panestria.profile"
            " WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (handle.profile_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[1] != expected_version:
            raise KernelDenied("version_conflict")
        if row[0] >= 1024:
            raise KernelDenied("profile_capacity_reached")
        envelope = self._seal(actor, handle, int(row[0]) + 1, document, consent_ref)
        self._store(uow, envelope)
        uow.execute(
            "UPDATE panestria.profile SET current_revision=%s,row_version=row_version+1,status='ACTIVE'"
            " WHERE id=%s AND owner_id=%s AND project_id=%s",
            (envelope.version, handle.profile_id, actor.owner_id, actor.project_id),
        )
        return self._ref(envelope, expected_version + 1)

    def read(
        self, uow: UnitOfWork, actor: Actor, profile_id: str, *, expected_version: int | None = None
    ) -> tuple[ProfileRef, ProfileDocument]:
        self._enabled()
        row = uow.execute(
            "SELECT h.row_version,h.status,r.id::text,r.profile_id::text,r.owner_id::text,r.project_id::text,"
            "r.version,r.key_id::text,r.schema_version,r.algorithm,r.privacy_label,r.consented_by::text,"
            "r.consent_ref::text,r.nonce,r.ciphertext,r.ciphertext_sha256"
            " FROM panestria.profile h JOIN panestria.profile_revision r ON"
            " (r.profile_id,r.owner_id,r.project_id,r.version)=(h.id,h.owner_id,h.project_id,h.current_revision)"
            " WHERE h.id=%s AND h.owner_id=%s AND h.project_id=%s FOR SHARE OF h",
            (profile_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[1] != "ACTIVE":
            raise KernelDenied("profile_suppressed")
        if expected_version is not None and row[0] != expected_version:
            raise KernelDenied("version_conflict")
        fields = (
            "revision_id",
            "profile_id",
            "owner_id",
            "project_id",
            "version",
            "key_id",
            "schema_version",
            "algorithm",
            "privacy_label",
            "consented_by",
            "consent_ref",
            "nonce",
            "ciphertext",
            "ciphertext_sha256",
        )
        try:
            envelope = ProfileEnvelope.model_validate(dict(zip(fields, row[2:], strict=True)))
            if envelope.consented_by != actor.owner_id or not hmac.compare_digest(
                envelope.ciphertext_sha256, hashlib.sha256(envelope.ciphertext).hexdigest()
            ):
                raise ValueError
        except (ValidationError, ValueError):
            raise KernelDenied("profile_integrity_failed") from None
        handle = ProfileKeyHandle(**{field: getattr(envelope, field) for field in ProfileKeyHandle.model_fields})
        key = self._key(handle)
        try:
            payload = AESGCM(key.get_secret_value()).decrypt(envelope.nonce, envelope.ciphertext, envelope.aad())
            document = ProfileDocument.model_validate_json(payload)
        except (InvalidTag, ValueError, ValidationError):
            raise KernelDenied("profile_integrity_failed") from None
        now = uow.execute("SELECT clock_timestamp()").fetchone()
        if now is None or (document.valid_until is not None and document.valid_until <= now[0]):
            raise KernelDenied("profile_expired")
        return self._ref(envelope, int(row[0])), document

    def suppress(self, uow: UnitOfWork, actor: Actor, profile_id: str, expected_version: int) -> int:
        self._enabled()
        row = uow.execute(
            "SELECT row_version,status FROM panestria.profile WHERE id=%s AND owner_id=%s AND project_id=%s FOR UPDATE",
            (profile_id, actor.owner_id, actor.project_id),
        ).fetchone()
        if row is None:
            raise KernelDenied("not_found")
        if row[0] != expected_version:
            raise KernelDenied("version_conflict")
        if row[1] == "SUPPRESSED":
            return int(row[0])
        uow.execute(
            "UPDATE panestria.profile SET status='SUPPRESSED',row_version=row_version+1"
            " WHERE id=%s AND owner_id=%s AND project_id=%s",
            (profile_id, actor.owner_id, actor.project_id),
        )
        return expected_version + 1
