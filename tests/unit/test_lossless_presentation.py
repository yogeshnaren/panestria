"""Paired source/output fixtures assert actual byte retention and abstention."""

import re

import pytest

from panestria.contracts.style import StyleProfile
from panestria.memory.presentation import present


def test_plain_layout_keeps_every_fact_number_citation_uncertainty_and_unicode_byte():
    source = "Cost may be €1.25 [S1].\n\nLatency is unconfirmed at 42 ms [S2].\n"
    result = present(source, StyleProfile(formatting="bullets", language="fr", detail="concise"))
    assert result.text == "- Cost may be €1.25 [S1].\n\n- Latency is unconfirmed at 42 ms [S2].\n"
    assert re.sub(r"(?m)^- ", "", result.text) == source
    assert result.observation.state == "APPLIED"
    assert result.observation.input_bytes == len(source.encode())
    assert result.observation.output_bytes == len(result.text.encode())
    assert result.observation.paragraphs == 2
    assert result.observation.words == len(source.split())
    assert result.observation.factual_support == result.observation.owner_preference == "NOT_ASSESSED"
    assert source not in repr(result)
    assert present(source, StyleProfile(formatting="paragraphs")).text == source
    # Presentation never translates, summarizes, repairs or verifies these facts.
    assert "unconfirmed" in result.text and "€1.25" in result.text
    partial = present(source, StyleProfile(formatting="bullets"), complete=False)
    assert partial.text == source and partial.observation.state == "ABSTAIN"


@pytest.mark.parametrize(
    "source",
    [
        "```python\nassert value == 42\n```",
        "| Fact | Source |\n| 42 | [S1] |",
        "- Existing item [S1]\n- Existing item [S2]",
        "    protected indentation 42 [S1]",
        "[S1]: https://example.invalid/source",
        "<script>untrusted()</script>",
    ],
)
def test_structured_or_ambiguous_output_abstains_without_a_semantic_rewrite(source):
    result = present(source, StyleProfile(formatting="bullets"))
    assert result.text == source and result.observation.state == "ABSTAIN"
    assert result.observation.input_bytes == result.observation.output_bytes
    assert result.observation.factual_support == "NOT_ASSESSED"
