"""AI-P2d near-duplicate detection used to keep folds from straddling one question."""

import pytest

from panestria.learning.curation import near_duplicate


@pytest.mark.parametrize(
    "left,right",
    [
        ("How many sides does a triangle have?", "how many SIDES does a triangle have"),
        ("R\u00e9sum\u00e9 tips", "Re\u0301sume\u0301 tips"),
        ("Explain the CAP theorem in distributed systems briefly", "Explain the CAP theorem in distributed systems"),
    ],
)
def test_near_duplicates(left, right):
    assert near_duplicate(left, right)


@pytest.mark.parametrize(
    "left,right",
    [
        ("How many sides does a triangle have?", "How many sides does a hexagon have?"),
        ("What is 2+2?", "What is the capital of France?"),
    ],
)
def test_distinct_inputs(left, right):
    assert not near_duplicate(left, right)
