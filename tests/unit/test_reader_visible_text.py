"""The HTML reader keeps visible text only; hidden markup cannot smuggle instructions."""

import re
from pathlib import Path

import pytest

from panestria.brokers.research.reader_worker import extract_html

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/reader"


@pytest.mark.parametrize("name", sorted(path.name for path in FIXTURES.glob("hidden-*.html")))
def test_hidden_markup_is_dropped_and_counted(name):
    source = (FIXTURES / name).read_text()
    text, dropped = extract_html(source)
    expected = set(re.findall(r"VISIBLE-\d+", source))
    assert expected and set(re.findall(r"VISIBLE-\d+", text)) == expected
    assert "SECRET" not in text
    assert dropped > 0


def test_invisible_and_bidirectional_controls_are_removed_and_counted():
    text, dropped = extract_html("<p>pay\u200bload \u202ereversed\u202c \ufeffend</p>")
    assert text == "\npayload reversed end\n"
    assert dropped == len("\u200b\u202e\u202c\ufeff".encode())


@pytest.mark.parametrize(
    ("markup", "expected", "dropped"),
    [
        # Frozen from the previous htmlparser-text-v1 extractor: visible-only
        # markup must produce exactly the same text under the new extractor.
        (
            "<html><head><title>T</title></head><body><h1>Title</h1><p>One <b>two</b></p><ul><li>a<li>b</ul>"
            "<table><tr><td>1<td>2<tr><td>3</table><br>x<hr>y</body></html>",
            "\nTitle\n\nOne two\n\n\na\nb\n\n\n1\n2\n\n3\nxy",
            len("T"),
        ),
        (
            "<div><p>para<div>inner</div>after</p></div><dl><dt>t<dd>d</dl><select><option>o1<option>o2</select>",
            "\n\npara\ninner\nafter\n\ntdo1o2",
            0,
        ),
        (
            "<p>a</p><p>b<p>c<pre>  code\n  more</pre><blockquote>q</blockquote>",
            "\na\n\nb\nc\n  code\n  more\n\nq\n",
            0,
        ),
        (
            "plain &amp; text &lt;tag&gt; <script>bad()</script> tail <style>.x{}</style> end <noscript>ns</noscript>",
            "plain & text <tag>  tail  end ",
            len("bad().x{}ns"),
        ),
        (
            "<article><section><h2>H</h2><p>P</p></section></article><img src=x alt=y>z<br/>w",
            "\n\n\nH\n\nP\n\n\nz\nw",
            0,
        ),
    ],
)
def test_visible_markup_text_is_unchanged_from_the_previous_extractor(markup, expected, dropped):
    assert extract_html(markup) == (expected, dropped)


def test_unterminated_script_is_still_refused():
    with pytest.raises(ValueError, match="unclosed_hidden_markup"):
        extract_html("<p>a</p><script>never closed")


def test_unclosed_hidden_element_hides_to_the_end_like_a_browser():
    text, dropped = extract_html("<p>VISIBLE</p><div hidden>SECRET tail")
    assert "VISIBLE" in text and "SECRET" not in text and dropped == len("SECRET tail")
