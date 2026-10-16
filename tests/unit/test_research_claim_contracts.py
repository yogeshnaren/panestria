"""Closed claim inputs and bounded quote/reference sets; no source or model authority."""

from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from panestria.contracts.research import ClaimDraft, PassageRef
from panestria.contracts.research_claims import ClaimEvidenceDraft, QuotedPassage


def reference():
    return PassageRef(snapshot_id=str(uuid4()), request_id=str(uuid4()), text_sha256="ab" * 32, start=0, end=4)


@pytest.mark.parametrize("field", ["approved", "support_status", "verdict", "claim_id"])
def test_client_cannot_supply_authority_fields(field):
    with pytest.raises(ValidationError):
        ClaimEvidenceDraft.model_validate(
            {"claim": {"text": SecretStr("synthetic"), "kind": "FACT", "passages": ()}, field: True}
        )


def test_duplicate_or_unlisted_quote_references_are_rejected():
    ref = reference()
    claim = ClaimDraft(text=SecretStr("synthetic"), kind="FACT", passages=(ref,))
    quoted = QuotedPassage(reference=ref, quote=SecretStr("text"))
    for candidate in (
        {"claim": claim.model_copy(update={"passages": (ref, ref)})},
        {"claim": claim, "quotes": (quoted, quoted)},
        {"claim": claim, "quotes": (quoted.model_copy(update={"reference": reference()}),)},
    ):
        with pytest.raises(ValidationError):
            ClaimEvidenceDraft(**candidate)


def test_utf8_quote_byte_cap_is_independent_from_character_count():
    with pytest.raises(ValidationError):
        QuotedPassage(reference=reference(), quote=SecretStr("中" * 4096))
