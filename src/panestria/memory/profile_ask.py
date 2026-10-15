"""Profile Ask manifests bind ciphertext, never unkeyed clear-profile hashes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from psycopg.types.json import Jsonb

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory.context import ContextPack
from panestria.memory.profile import ProfileSelection


def overlay(prompt: str, selection: ProfileSelection) -> str:
    body = json.loads(prompt)
    if not isinstance(body, dict) or "untrusted_owner_profile" in body:
        raise KernelDenied("profile_context_integrity_failed")
    body["untrusted_owner_profile"] = json.loads(selection.content.get_secret_value())
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def manifest(pack: ContextPack, selection: ProfileSelection) -> str:
    metadata = {
        "schema_version": 1,
        "render_version": 1,
        "general_context_sha256": pack.sha256,
        "owner_id": selection.owner_id,
        "project_id": selection.project_id,
        "profile_source": asdict(selection.source),
        "selection": selection.request.model_dump(),
        "policy_ref": selection.policy_ref,
        "label": "RESTRICTED",
        "offline": True,
    }
    return hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _values(selection: ProfileSelection, pack: ContextPack) -> tuple[object, ...]:
    source = selection.source
    return (
        source.revision_id,
        source.profile_id,
        source.revision,
        source.row_version,
        source.key_id,
        source.ciphertext_sha256,
        selection.request.model_dump(mode="json"),
        selection.request.sha256(),
        manifest(pack, selection),
        selection.policy_ref,
        1,
        "RESTRICTED",
    )


def record_binding(
    uow: UnitOfWork, actor: Actor, request_id: str, pack: ContextPack, selection: ProfileSelection
) -> None:
    values = list(_values(selection, pack))
    values[6] = Jsonb(values[6])
    uow.execute(
        "INSERT INTO panestria.ask_profile_context(request_id,owner_id,project_id,source_revision_id,profile_id,"
        "profile_version,row_version,key_id,ciphertext_sha256,request_body,selection_sha256,manifest_sha256,"
        "policy_ref,render_version,privacy_label) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (request_id, actor.owner_id, actor.project_id, *values),
    )


def require_binding(
    uow: UnitOfWork,
    actor: Actor,
    request_id: str,
    pack: ContextPack,
    selection: ProfileSelection | None,
) -> None:
    row = uow.execute(
        "SELECT source_revision_id::text,profile_id::text,profile_version,row_version,key_id::text,ciphertext_sha256,"
        "request_body,selection_sha256,manifest_sha256,policy_ref,render_version,privacy_label"
        " FROM panestria.ask_profile_context WHERE request_id=%s AND owner_id=%s AND project_id=%s",
        (request_id, actor.owner_id, actor.project_id),
    ).fetchone()
    if (selection is None and row is not None) or (
        selection is not None and (row is None or row != _values(selection, pack))
    ):
        raise KernelDenied("profile_context_integrity_failed")
