"""Actual encrypted PG/HTTP/PTY and scoped prompt; synthetic owner keys/model only."""

import hashlib
import json
import os
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr, ValidationError
from test_ask_tui import terminal
from test_profile_ask import ask_profile as ask_profile  # noqa: F401
from test_profile_style import styled as styled  # noqa: F401
from test_profile_style_terminal import style_server as style_server  # noqa: F401
from test_profile_vault import profile as profile  # noqa: F401

from panestria.cli.profile_client import ProfileClient, StyleSource, style_document
from panestria.contracts.profile import ProfileDocument
from panestria.contracts.style import StyleExample, StyleProfile
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork
from panestria.memory.style import compile_style

INPUT = "OWNER_PRIVATE_EXAMPLE_INPUT"
RESPONSE = "OWNER_PRIVATE_EXAMPLE_REPLY 42 [1]; uncertainty remains."


def example_style():
    return StyleProfile(
        examples=(StyleExample(reference="reviewed-one", input=SecretStr(INPUT), response=SecretStr(RESPONSE)),)
    )


@pytest.fixture
def r1_task(r1_migration_task):
    return r1_migration_task


def test_private_example_is_ciphertext_pinned_and_never_general_context_or_audit(styled):  # noqa: F811
    dsn, actor, handle, _, vault, service, request, _ = styled
    style = example_style()
    with psycopg.connect(dsn) as c:
        vault.revise(
            UnitOfWork(c),
            actor,
            handle,
            1,
            ProfileDocument(
                fields={"communication": SecretStr(style.private_json())},
                approved_for_local_context=("communication",),
            ),
            consent_ref=str(uuid4()),
        )
    request = request.model_copy(update={"profile": request.profile.model_copy(update={"expected_row_version": 2})})
    with psycopg.connect(dsn) as c:
        ready = service.prepare(UnitOfWork(c), actor, request)
    private = json.loads(ready.inference.prompt)["untrusted_owner_profile"]["structured_style"][
        "untrusted_private_examples"
    ]
    assert private["examples"] == [{"reference": "reviewed-one", "input": INPUT, "response": RESPONSE}]
    assert private["policy_authority"] == "NONE" and private["training_permission"] == "NOT_GRANTED"
    assert ready.inference.offline and ready.inference.label == "RESTRICTED"
    assert INPUT not in ready.context.prompt and RESPONSE not in ready.context.prompt
    forbidden = (
        INPUT,
        RESPONSE,
        hashlib.sha256(INPUT.encode()).hexdigest(),
        hashlib.sha256(ready.inference.prompt.encode()).hexdigest(),
    )
    with psycopg.connect(dsn) as c:
        for table in ("context_pack", "ask_request", "ask_profile_context", "profile_revision", "learning_record"):
            rows = c.execute(f"SELECT row_to_json(t)::text FROM panestria.{table} t").fetchall()
            assert all(all(value not in row[0] for value in forbidden) for row in rows)
        # Correction/suppression cannot silently replace a previously prepared prompt.
        vault.revise(
            UnitOfWork(c),
            actor,
            handle,
            2,
            ProfileDocument(
                fields={"communication": SecretStr(StyleProfile().private_json())},
                approved_for_local_context=(),
            ),
            consent_ref=str(uuid4()),
        )
    with psycopg.connect(dsn) as c, pytest.raises(KernelDenied):
        service.claim(UnitOfWork(c), actor, ready)


def test_terminal_requires_full_example_review_then_one_encrypted_save(style_server, tmp_path):  # noqa: F811
    f = style_server
    path = tmp_path / "private-examples.json"
    sample = {**example_style().examples[0].private_data(), "response": RESPONSE + "\n" + "line\n" * 24}
    path.write_text(json.dumps({"examples": [sample]}))
    path.chmod(0o600)
    args = (
        "--profile-id",
        f.handle.profile_id,
        "--key-id",
        f.handle.key_id,
        "--owner-review",
        "--examples-file",
        str(path),
    )
    original = path.read_bytes()
    with terminal(f.path, entry=("profile", "style-tui"), arguments=args) as t:
        t.until(b"Private examples: 1")
        assert INPUT.encode() not in t.transcript
        os.write(t.master, b"sy")
        t.until(b"No write sent")
        assert f.state.writes == 0
        os.write(t.master, b"v")
        t.until(INPUT.encode())
        t.until(RESPONSE.encode(), after=0)
        t.until(b"More below", after=0)
        # Seeing the first screen alone cannot acknowledge a longer example.
        mark = len(t.transcript)
        os.write(t.master, b"aqsy")
        t.until(b"No write sent", after=mark)
        assert f.state.writes == 0
        os.write(t.master, b"v" + b"j" * 40)
        t.until(b"END: a acknowledges", after=0)
        os.write(t.master, b"asysy")
        t.until(b"SAVED row version 0")
        os.write(t.master, b"q")
    assert f.state.writes == 1 and path.read_bytes() == original
    source = ProfileClient(f.path).source(f.handle.profile_id, 0)
    assert source.style.examples[0].response.get_secret_value() == sample["response"]
    assert not source.approved  # Local-context consent is still a separate choice.
    with psycopg.connect(f.dsn) as c:
        _, doc = f.vault.read(UnitOfWork(c), f.actor, f.handle.profile_id)
        assert StyleProfile.model_validate_json(doc.fields["communication"].get_secret_value()) == source.style
        assert (
            INPUT
            not in c.execute(
                "SELECT row_to_json(r)::text FROM panestria.profile_revision r WHERE profile_id=%s",
                (f.handle.profile_id,),
            ).fetchone()[0]
        )


def test_bounds_masking_and_legacy_compilation_and_snapshot_preservation():
    style = example_style()
    assert INPUT not in repr(style) and RESPONSE not in style.model_dump_json()
    assert StyleProfile.model_validate_json(style.private_json()) == style
    old = (
        '{"schema_version":1,"language":"en","audience":"general","detail":"balanced",'
        '"formatting":"auto","tables":"when-useful"}'
    )
    assert StyleProfile().private_json() == old
    assert "untrusted_private_examples" not in compile_style(old)
    assert compile_style(old)["preferences"] == json.loads(old)
    source = StyleSource(
        str(uuid4()),
        str(uuid4()),
        0,
        document=ProfileDocument(fields={"background": SecretStr("KEEP")}, approved_for_local_context=("background",)),
    )
    doc = style_document(source, style, True)
    assert doc.fields["background"].get_secret_value() == "KEEP"
    assert set(doc.approved_for_local_context) == {"background", "communication"}
    assert StyleProfile.model_validate_json(doc.fields["communication"].get_secret_value()) == style
    for data in (
        {"examples": [style.examples[0].private_data()] * 2},
        {"examples": [{"reference": "one", "input": "é" * 129, "response": RESPONSE}]},
        {"examples": [{"reference": "one", "input": INPUT, "response": " "}]},
        {"examples": [{"reference": "one", "input": INPUT, "response": RESPONSE, "authority": "PERMIT"}]},
        {"examples": [style.examples[0].private_data()] * 3},
        {"examples": [{"reference": "one", "input": INPUT, "response": "bad\x1b[0m"}]},
    ):
        with pytest.raises(ValidationError) as caught:
            StyleProfile.model_validate_json(json.dumps(data))
        assert INPUT not in str(caught.value) and RESPONSE not in str(caught.value)
