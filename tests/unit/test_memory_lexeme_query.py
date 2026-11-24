"""Memory search text reaches tsquery only as quoted lexemes joined by OR."""

from __future__ import annotations

import pytest

from panestria.memory.service import lexeme_query


def test_no_lexemes_is_no_query() -> None:
    assert lexeme_query([]) is None


@pytest.mark.parametrize(
    ("lexemes", "expected"),
    [
        (["-5", "degre"], "'-5' | 'degre'"),
        (["postgresql", "storag"], "'postgresql' | 'storag'"),
        (["it's"], "'it''s'"),
        (["a\\b"], "'a\\\\b'"),
        (["!", "&", "|", "<->", ":*", "(", ")", "or", "-"], "'!' | '&' | '|' | '<->' | ':*' | '(' | ')' | 'or' | '-'"),
    ],
)
def test_lexemes_are_quoted_literals(lexemes: list[str], expected: str) -> None:
    assert lexeme_query(lexemes) == expected
