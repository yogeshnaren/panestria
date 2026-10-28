"""Fixed container-only tokenizer. Source data never selects code, files or URLs."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

HTML_EXTRACTOR = "htmlparser-visible-text-v2"
_BLOCK = frozenset(
    {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "section",
        "article",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "tr",
        "td",
        "th",
        "blockquote",
        "pre",
    }
)
_SKIP = frozenset({"script", "style", "head", "template", "noscript", "iframe", "object", "form", "svg", "math"})
_VOID = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)
# HTML implicit end tags: starting KEY closes the nearest open VALUE[0] unless a
# VALUE[1] boundary comes first. Starting any _CLOSES_P tag ends an open <p>.
_IMPLIED = {
    "li": ({"li"}, {"ul", "ol", "menu"}),
    "dt": ({"dt", "dd"}, {"dl"}),
    "dd": ({"dt", "dd"}, {"dl"}),
    "tr": ({"tr", "td", "th"}, {"table", "thead", "tbody", "tfoot"}),
    "td": ({"td", "th"}, {"tr", "table"}),
    "th": ({"td", "th"}, {"tr", "table"}),
    "option": ({"option"}, {"select", "datalist", "optgroup"}),
}
_CLOSES_P = frozenset(
    {
        "address", "article", "aside", "blockquote", "details", "dialog", "div", "dl", "fieldset", "figcaption",
        "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "main", "menu",
        "nav", "ol", "p", "pre", "section", "table", "ul",
    }
)  # fmt: skip
# Invisible formatting and bidirectional controls can hide or reorder text.
_INVISIBLE = dict.fromkeys(
    map(ord, "\u200b\u200c\u200d\u2060\ufeff\u180e\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
)


def _zero(value: str) -> bool:
    number = value.strip().rstrip("%").removesuffix("px").removesuffix("em").removesuffix("rem").removesuffix("pt")
    try:
        return float(number) == 0
    except ValueError:
        return False


def _far_negative(value: str) -> bool:
    try:
        return float(value.strip().removesuffix("px").removesuffix("em").removesuffix("rem")) <= -999
    except ValueError:
        return False


def _hides(attrs: list[tuple[str, str | None]]) -> bool:
    """Inline markup that renders nothing visible. Stylesheet classes are not resolved."""
    values = {name.lower(): (value or "") for name, value in attrs}
    if "hidden" in values or values.get("aria-hidden", "").strip().lower() == "true":
        return True
    style: dict[str, str] = {}
    for declaration in values.get("style", "").split(";"):
        name, separator, value = declaration.partition(":")
        if separator:
            style[name.strip().lower()] = value.lower().replace("!important", "").strip()
    color = style.get("color", "")
    background = style.get("background-color", style.get("background", ""))
    return (
        style.get("display") == "none"
        or style.get("visibility") in {"hidden", "collapse"}
        or any(_zero(style[key]) for key in ("opacity", "font-size") if key in style)
        or any(_far_negative(style[key]) for key in ("left", "top", "right", "bottom", "text-indent") if key in style)
        or style.get("transform", "").replace(" ", "") in {"scale(0)", "scale(0,0)"}
        or "inset(50%" in style.get("clip-path", "")
        or "inset(100%" in style.get("clip-path", "")
        or (
            style.get("overflow") in {"hidden", "clip"}
            and any(_zero(style[key]) for key in ("width", "height", "max-width", "max-height") if key in style)
        )
        or color == "transparent"
        or (color != "" and color == background)
    )


class _Visible(HTMLParser):
    """Visible text only: skipped containers, hidden attributes and invisible inline styles are dropped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.open: list[tuple[str, bool]] = []  # (tag, hides its content)
        self.hidden_bytes = 0
        self.tags = 0

    @property
    def hidden(self) -> bool:
        return any(hides for _, hides in self.open)

    def _close_to(self, index: int, *, newline: bool = True) -> None:
        tag = self.open[index][0]
        del self.open[index:]
        if newline and not self.hidden and tag in _BLOCK:
            self.parts.append("\n")

    def _imply_end(self, tag: str) -> None:
        if tag in _CLOSES_P:
            for index in range(len(self.open) - 1, -1, -1):
                if self.open[index][0] == "p":
                    self._close_to(index, newline=False)
                    break
                if self.open[index][0] not in {"b", "i", "em", "strong", "span", "a", "small", "code"}:
                    break
        closes, boundary = _IMPLIED.get(tag, (set(), set()))
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] in boundary:
                break
            if self.open[index][0] in closes:
                self._close_to(index, newline=False)
                break

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags += 1
        if self.tags > 100_000 or len(self.open) > 4096:
            raise ValueError("parser_limit")
        self._imply_end(tag)
        if tag in _VOID:
            if not self.hidden and tag in _BLOCK:
                self.parts.append("\n")
            return
        hides = tag in _SKIP or _hides(attrs)
        if not self.hidden and not hides and tag in _BLOCK:
            self.parts.append("\n")
        self.open.append((tag, hides))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Void markup cannot hide following text; attributes never run or fetch.
        self.tags += 1
        if not self.hidden and tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] == tag:
                self._close_to(index)
                return
        if not self.hidden and tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.hidden:
            self.hidden_bytes += len(data.encode("utf-8"))
            return
        visible = data.translate(_INVISIBLE)
        self.hidden_bytes += len(data.encode("utf-8")) - len(visible.encode("utf-8"))
        self.parts.append(visible)

    def unclosed_skip(self) -> bool:
        # An unterminated script/style/template would otherwise swallow or leak the rest.
        return any(tag in _SKIP for tag, _ in self.open)


def extract_html(text: str) -> tuple[str, int]:
    """Return visible text and the UTF-8 byte count of dropped hidden or invisible text."""
    parser = _Visible()
    parser.feed(text)
    parser.close()
    if parser.unclosed_skip():
        raise ValueError("unclosed_hidden_markup")
    return "".join(parser.parts), parser.hidden_bytes


def main() -> None:
    result: dict[str, object] = {"outcome": "ERROR", "reason": "reader_error"}
    try:
        digest, content_type, raw_length, text_limit = sys.argv[1:]
        maximum = int(text_limit)
        raw = Path("/runtime/source.bin").read_bytes()
        if len(raw) != int(raw_length) or len(raw) > 2 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("input_mismatch")
        if unicodedata.unidata_version != "15.0.0" or not 1 <= maximum <= 512 * 1024:
            raise ValueError("reader_version_or_limit")
        result = {"outcome": "UNSUPPORTED", "reason": "extractor_unsupported"}
        if content_type in {"text/plain", "text/html"}:
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeError:
                result = {"outcome": "ERROR", "reason": "decoder_error"}
            else:
                extractor = "strict-utf8-v1"
                hidden_bytes = None
                if content_type == "text/html":
                    text, hidden_bytes = extract_html(text)
                    extractor = HTML_EXTRACTOR
                canonical = unicodedata.normalize("NFC", text).encode("utf-8", errors="strict")
                if len(canonical) > maximum:
                    result = {"outcome": "TRUNCATED", "reason": "text_byte_limit"}
                else:
                    tokenizer = Path(inspect.getsourcefile(HTMLParser) or "")
                    result = {
                        "outcome": "COMPLETE",
                        "reason": "extracted_text_only",
                        "raw_sha256": digest,
                        "raw_size": len(raw),
                        "text_sha256": hashlib.sha256(canonical).hexdigest(),
                        "text_size": len(canonical),
                        "text_b64": base64.b64encode(canonical).decode("ascii"),
                        "extractor_version": extractor,
                        "normalization_version": "nfc-utf8-v1",
                        "unicode_version": unicodedata.unidata_version,
                        "tokenizer_sha256": hashlib.sha256(tokenizer.read_bytes()).hexdigest(),
                    }
                    if hidden_bytes is not None:
                        result["hidden_bytes_dropped"] = hidden_bytes
    except Exception:
        result = {"outcome": "ERROR", "reason": "reader_error"}
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
