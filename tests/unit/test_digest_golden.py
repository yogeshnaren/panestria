"""Frozen digest vectors: stored approvals, contracts and receipts must keep verifying."""

import hashlib
import json
from pathlib import Path

import pytest

from panestria.contracts.approval import ActionPreview, effect_digest, load_preview
from panestria.contracts.build import canonical_sha256
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.sandbox.profiles import SandboxProfile

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = json.loads((ROOT / "tests/fixtures/golden/digests-v1.json").read_text())


def test_canonical_encoding_matches_an_independent_byte_string():
    # Sorted keys, compact separators and raw UTF-8, written by hand.
    assert canonical_sha256({"b": 1, "a": [3, 2, 1]}) == hashlib.sha256(b'{"a":[3,2,1],"b":1}').hexdigest()
    assert canonical_sha256({"é": "☕"}) == hashlib.sha256('{"é":"☕"}'.encode()).hexdigest()


@pytest.mark.parametrize("case", GOLDEN["canonical_sha256"], ids=lambda case: case["sha256"][:12])
def test_canonical_sha256_vectors(case):
    assert canonical_sha256(case["value"]) == case["sha256"]


@pytest.mark.parametrize("case", GOLDEN["effect_digest"], ids=lambda case: f"loaded={case['loaded']}")
def test_effect_digest_vectors(case):
    preview = load_preview(case["preview"]) if case["loaded"] else ActionPreview.model_validate(case["preview"])
    assert effect_digest(preview) == case["sha256"]


def test_loaded_preview_sorts_checks_so_the_two_vectors_differ():
    stored, loaded = GOLDEN["effect_digest"]
    assert stored["sha256"] != loaded["sha256"]


@pytest.mark.parametrize("case", GOLDEN["contract_sha256"], ids=lambda case: case["path"])
def test_contract_sha256_vectors(case):
    contract = load_contract(json.loads((ROOT / case["path"]).read_text()))
    assert contract_sha256(contract) == case["sha256"]


@pytest.mark.parametrize("case", GOLDEN["sandbox_profile_sha256"], ids=lambda case: case["sha256"][:12])
def test_sandbox_profile_vectors(case):
    profile = SandboxProfile(**case["fields"])
    profile.validate()
    assert profile.sha256() == case["sha256"]
