"""Fixed container-only PDF text layer reader. Never call main on the host."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import sys
import unicodedata
from pathlib import Path
from typing import Any

BUNDLE_SHA256 = "d990ef5d2b271b795faa3c37345890cb9dfaa914d4532d7364f8825d021508a1"
LIMITATIONS = ("pdf-text-layer-only", "pdf-no-ocr", "pdf-layout-unverified")
SEPARATOR = b"\n\f\n"


class UnsupportedPdf(ValueError):
    pass


class TruncatedPdf(ValueError):
    pass


def _check_graph(root: Any) -> None:
    # Additional conservative content restriction; not a PDF security certificate.
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

    denied_keys = {
        "/OpenAction", "/AA", "/A", "/JS", "/JavaScript", "/EmbeddedFiles", "/EF",
        "/AcroForm", "/XFA", "/RichMediaContent", "/Annots", "/XObject", "/F",
    }
    denied_names = {"/JavaScript", "/Launch", "/Filespec", "/EmbeddedFile", "/RichMedia", "/GoToR"}
    pending = [(root, 0)]
    seen: set[tuple[int, int]] = set()
    nodes = 0
    while pending:
        item, depth = pending.pop()
        if isinstance(item, IndirectObject):
            identity = (item.idnum, item.generation)
            if identity in seen:
                continue
            seen.add(identity)
            item = item.get_object()
        nodes += 1
        if nodes > 10_000 or depth > 32:
            raise ValueError("pdf_graph_limit")
        if isinstance(item, DictionaryObject):
            if len(item) > 256:
                raise ValueError("pdf_dictionary_limit")
            if denied_keys.intersection(item):
                raise UnsupportedPdf("pdf_feature_unsupported")
            pending.extend((value, depth + 1) for value in item.values())
        elif isinstance(item, ArrayObject):
            if len(item) > 2048 or len(pending) + len(item) > 10_000:
                raise ValueError("pdf_array_limit")
            pending.extend((value, depth + 1) for value in item)
        elif isinstance(item, NameObject) and item in denied_names:
            raise UnsupportedPdf("pdf_feature_unsupported")


def _extract(raw: bytes, maximum: int) -> tuple[bytes, list[list[int]]]:
    # This import exists only in a fresh network-none Docker interpreter with a
    # minimal immutable source/license bundle. No host PDF object parsing.
    sys.path.insert(0, "/runtime/pdf-deps")
    import pypdf

    if pypdf.__version__ != "6.21.2":
        raise ValueError("pdf_version")
    manifest = Path("/runtime/pdf-deps/manifest.json").read_bytes()
    if hashlib.sha256(manifest).hexdigest() != BUNDLE_SHA256:
        raise ValueError("pdf_bundle")
    limit = 2 * 1024 * 1024
    config = pypdf.Configuration(
        maximum_declared_stream_length=limit,
        array_based_stream_maximum_output_length=limit,
        jbig2_maximum_output_length=limit,
        lzw_maximum_output_length=limit,
        run_length_maximum_output_length=limit,
        zlib_maximum_output_length=limit,
        zlib_maximum_recovery_input_length=0,
        brotli_maximum_output_length=limit,
        flate_maximum_columns=8192,
        flate_maximum_row_length=64 * 1024,
        image_maximum_buffer_size=limit,
        stream_filters_maximum_length=4,
        stream_decoding_work_maximum_length=4 * limit,
        xmp_maximum_input_length=64 * 1024,
        xmp_maximum_element_count=1024,
        outline_maximum_entries=128,
        outline_maximum_depth=16,
        page_tree_maximum_entries=128,
        page_tree_maximum_depth=16,
        xform_maximum_invocations_per_extraction=64,
        jbig2dec_binary=None,
        disable_legacy_handling=True,
    )
    with pypdf.apply_configuration(config):
        reader = pypdf.PdfReader(io.BytesIO(raw), strict=True, root_object_recovery_limit=64)
        if reader.is_encrypted:
            raise UnsupportedPdf("pdf_encrypted")
        _check_graph(reader.root_object)
        count = len(reader.pages)
        if count > 32:
            raise TruncatedPdf("pdf_page_limit")
        if count == 0:
            raise UnsupportedPdf("pdf_no_text")
        result = bytearray()
        spans: list[list[int]] = []
        decoded_total = 0
        for page in reader.pages:
            content = page.get_contents()
            if content is not None:
                decoded = content.get_data()
                decoded_total += len(decoded)
                if len(decoded) > limit or decoded_total > 4 * limit:
                    raise ValueError("pdf_stream_limit")
            canonical = unicodedata.normalize("NFC", page.extract_text(extraction_mode="plain")).encode("utf-8")
            if not canonical.strip():
                raise UnsupportedPdf("pdf_no_text")
            if spans:
                result.extend(SEPARATOR)
            start = len(result)
            if start + len(canonical) > maximum:
                raise TruncatedPdf("text_byte_limit")
            result.extend(canonical)
            spans.append([start, len(result)])
        return bytes(result), spans


def main() -> None:
    # Upstream parse warnings may contain source text. Emit only fixed closed
    # outcomes; strict parsing, bounds and the actual container stay mandatory.
    logging.disable(logging.CRITICAL)
    result: dict[str, object] = {"outcome": "ERROR", "reason": "reader_error"}
    try:
        digest, content_type, raw_length, text_limit = sys.argv[1:]
        maximum = int(text_limit)
        raw = Path("/runtime/source.bin").read_bytes()
        if (
            content_type != "application/pdf"
            or not raw.startswith(b"%PDF-")
            or len(raw) != int(raw_length)
            or len(raw) > 2 * 1024 * 1024
            or hashlib.sha256(raw).hexdigest() != digest
            or unicodedata.unidata_version != "15.0.0"
            or not 1 <= maximum <= 512 * 1024
        ):
            raise ValueError("pdf_input")
        canonical, spans = _extract(raw, maximum)
        result = {
            "outcome": "COMPLETE", "reason": "extracted_text_only",
            "raw_sha256": digest, "raw_size": len(raw),
            "text_sha256": hashlib.sha256(canonical).hexdigest(), "text_size": len(canonical),
            "text_b64": base64.b64encode(canonical).decode("ascii"),
            "extractor_version": "pypdf-6.21.2-text-v1",
            "normalization_version": "nfc-utf8-v1", "unicode_version": unicodedata.unidata_version,
            "tokenizer_sha256": BUNDLE_SHA256, "pdf_bundle_sha256": BUNDLE_SHA256,
            "page_spans": spans, "limitations": LIMITATIONS,
        }
    except UnsupportedPdf as error:
        result = {"outcome": "UNSUPPORTED", "reason": str(error)}
    except TruncatedPdf as error:
        result = {"outcome": "TRUNCATED", "reason": str(error)}
    except Exception:
        pass
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
