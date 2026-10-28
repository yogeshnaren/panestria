"""AI-P2d: owner attestation cannot relabel a recorded model answer, a secret or a near-duplicate."""

from __future__ import annotations

import random
import string
from uuid import uuid4

import psycopg
import pytest
from test_example_curation import accepted, files
from test_example_curation import curation as curation  # noqa: F401

from panestria.contracts.ask import AskSubmission
from panestria.contracts.inference import InferenceResult, Usage
from panestria.kernel.ask import AskService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork
from panestria.resources.catalog import STEWARD


def _record_answer(f, text: str) -> None:
    service = AskService()
    submission = AskSubmission(request_id=str(uuid4()), project_id=f.actor.project_id, question="synthetic question")
    with psycopg.connect(f.dsn) as c:
        uow = UnitOfWork(c)
        prepared = service.prepare(uow, f.actor, submission)
        service.claim(uow, f.actor, prepared)
        service.finish(
            uow, f.actor, submission.request_id, InferenceResult(STEWARD.model_ref, text, Usage(1, 1, 0), 0.1, 0.1)
        )


def test_ai_p2d_recorded_model_output_cannot_be_attested_as_owner_authored(curation):
    f = curation
    candidate, proofs = files(f, answer="A triangle has three sides.")
    before = f.service.prepare(candidate, proofs)
    assert before["preview"]["proposed_eligibility"] == "ALLOWED"
    _record_answer(f, "A triangle has three sides.")
    after = f.service.prepare(candidate, proofs)
    assert after["preview"]["proposed_eligibility"] == "DENIED"
    assert after["preview"]["reasons"] == ["recorded_model_output_lineage"]
    # The earlier review cannot be recorded against current lineage.
    with pytest.raises(KernelDenied, match="curation_exact_review_required|curation_current_evidence_required"):
        f.service.record(
            candidate,
            proofs,
            before["review_sha256"],
            confirm_owner_review=True,
            accept_training_data_purpose=True,
        )


def test_ai_p2d_lineage_is_rechecked_at_export(curation):
    f = curation
    candidate, proofs = files(f, answer="Four sides make a quadrilateral.")
    review = accepted(f, candidate, proofs)
    _record_answer(f, "Four sides make a quadrilateral.")
    with pytest.raises(KernelDenied, match="curation_current_eligibility_required"):
        f.service.export((review,), f.directory / "export.json")


def test_ai_p2d_secret_material_is_denied_without_echoing_it(curation):
    f = curation
    token = "gh" + "p_" + "".join(random.Random(7).choice(string.ascii_letters + string.digits) for _ in range(36))
    candidate, proofs = files(f, answer=f"Use {token} to log in.")
    preview = f.service.prepare(candidate, proofs)
    assert preview["preview"]["proposed_eligibility"] == "DENIED"
    assert preview["preview"]["reasons"] == ["secret_material_in_example"]


def test_ai_p2d_near_duplicate_inputs_cannot_share_an_export(curation):
    f = curation
    first = accepted(f, *files(f, question="How many sides does a triangle have?", answer="Three."))
    second = accepted(f, *files(f, question="how many SIDES does a triangle have", answer="3"))
    distinct = accepted(f, *files(f, question="What is the boiling point of water at sea level?", answer="100 C."))
    with pytest.raises(KernelDenied, match="curation_near_duplicate_input"):
        f.service.export((first, second), f.directory / "near.json")
    saved = f.service.export((first, distinct), f.directory / "ok.json")
    assert saved["examples"] == 2
