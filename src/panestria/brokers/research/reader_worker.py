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


class _Visible(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden: list[str] = []
        self.tags = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags += 1
        if self.tags > 100_000 or len(self.hidden) > 256:
            raise ValueError("parser_limit")
        if self.hidden or tag in _SKIP:
            self.hidden.append(tag)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Void markup cannot hide following text; attributes never run or fetch.
        self.tags += 1
        if not self.hidden and tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.hidden:
            if tag in self.hidden:
                index = len(self.hidden) - 1 - self.hidden[::-1].index(tag)
                del self.hidden[index:]
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


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
                if content_type == "text/html":
                    parser = _Visible()
                    parser.feed(text)
                    parser.close()
                    if parser.hidden:
                        raise ValueError("unclosed_hidden_markup")
                    text, extractor = "".join(parser.parts), "htmlparser-text-v1"
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
    except Exception:
        result = {"outcome": "ERROR", "reason": "reader_error"}
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
