"""Closed data protocol checks; these do not launch or authorize a native tool."""

import hashlib
import io
import struct

import pytest

from panestria.sandbox.native_tool_input import (
    MAGIC,
    MAX_FRAME_BYTES,
    MAX_REQUEST_BYTES,
    MAX_SCRIPT_BYTES,
    InputFrameRejected,
    decode_frame,
    encode_frame,
)

SCRIPT = b"raise RuntimeError('MUST_NOT_EXECUTE')"
BODY = b"PUBLIC_SYNTHETIC_DATA_NOT_JSON"
SCRIPT_HASH = hashlib.sha256(SCRIPT).hexdigest()
BODY_HASH = hashlib.sha256(BODY).hexdigest()


def decode(data: bytes):
    return decode_frame(io.BytesIO(data), script_sha256=SCRIPT_HASH, request_sha256=BODY_HASH)


def test_roundtrip_opaque_data_without_execution_or_json_parsing():
    value = decode(encode_frame(SCRIPT, BODY))
    assert value.script == SCRIPT and value.request == BODY
    assert repr(value) == "NativeInputFrame()"
    with pytest.raises(AttributeError):
        value.script = b"replacement"


@pytest.mark.parametrize(
    "script,body",
    [
        (b"", BODY),
        (SCRIPT, b""),
        (b"x" * (MAX_SCRIPT_BYTES + 1), BODY),
        (SCRIPT, b"x" * (MAX_REQUEST_BYTES + 1)),
        (bytearray(SCRIPT), BODY),
        (SCRIPT, memoryview(BODY)),
        ("code", BODY),
        (SCRIPT, None),
    ],
)
def test_encoder_rejects_nonbytes_and_out_of_bounds(script, body):
    with pytest.raises(InputFrameRejected, match="^native_input_invalid$"):
        encode_frame(script, body)


class Partial(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.sizes = []

    def read(self, size=-1):
        assert 0 < size <= MAX_SCRIPT_BYTES
        self.sizes.append(size)
        return super().read(min(size, 17))


def test_maximum_frame_accepts_partial_reads_with_bounded_requests():
    script = b"x" * MAX_SCRIPT_BYTES
    body = b"y" * MAX_REQUEST_BYTES
    encoded = encode_frame(script, body)
    assert len(encoded) == MAX_FRAME_BYTES
    source = Partial(encoded)
    value = decode_frame(
        source, script_sha256=hashlib.sha256(script).hexdigest(), request_sha256=hashlib.sha256(body).hexdigest()
    )
    assert value.script == script and value.request == body
    assert len(source.sizes) > MAX_FRAME_BYTES // 17 and source.sizes[-1] == 1


@pytest.mark.parametrize(
    "script_size,body_size",
    [
        (0, 1),
        (1, 0),
        (MAX_SCRIPT_BYTES + 1, 1),
        (1, MAX_REQUEST_BYTES + 1),
        (0xFFFFFFFF, 0xFFFFFFFF),
    ],
)
def test_invalid_lengths_rejected_before_body_read(script_size, body_size):
    header = MAGIC + struct.pack(">II", script_size, body_size)
    source = io.BytesIO(header + b"do-not-read")
    with pytest.raises(InputFrameRejected):
        decode_frame(source, script_sha256=SCRIPT_HASH, request_sha256=BODY_HASH)
    assert source.tell() == len(header)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"PANESTRIA-TOOL-2\n" + struct.pack(">II", 1, 1) + b"ab",
        MAGIC[:-1],
        MAGIC + b"\x00" * 7,
        encode_frame(SCRIPT, BODY)[: -len(BODY) - 1],
        encode_frame(SCRIPT, BODY)[:-1],
        encode_frame(SCRIPT, BODY) + b"x",
    ],
)
def test_truncation_version_and_trailing_bytes_rejected(data):
    with pytest.raises(InputFrameRejected, match="^native_input_invalid$"):
        decode(data)


@pytest.mark.parametrize(
    "script_hash,body_hash",
    [
        ("0" * 64, BODY_HASH),
        (SCRIPT_HASH, "0" * 64),
        (SCRIPT_HASH.upper(), BODY_HASH),
        (SCRIPT_HASH, "f" * 63),
        (SCRIPT_HASH, "g" * 64),
        (None, BODY_HASH),
    ],
)
def test_binding_digest_closed_format_and_exact_match(script_hash, body_hash):
    with pytest.raises(InputFrameRejected):
        decode_frame(io.BytesIO(encode_frame(SCRIPT, BODY)), script_sha256=script_hash, request_sha256=body_hash)


@pytest.mark.parametrize("result", [None, "text", bytearray(b"x"), b"x" * (len(MAGIC) + 1)])
def test_nonbinary_or_overreading_source_rejected(result):
    class BadSource:
        def read(self, size):
            return result

    with pytest.raises(InputFrameRejected):
        decode_frame(BadSource(), script_sha256=SCRIPT_HASH, request_sha256=BODY_HASH)


@pytest.mark.parametrize("error", [OSError("PRIVATE_TEST_MARKER"), ValueError("PRIVATE_TEST_MARKER")])
def test_io_error_does_not_expose_source_content(error):
    class FailingSource:
        def read(self, size):
            raise error

    with pytest.raises(InputFrameRejected) as refused:
        decode_frame(FailingSource(), script_sha256=SCRIPT_HASH, request_sha256=BODY_HASH)
    assert str(refused.value) == "native_input_invalid"
    assert refused.value.__suppress_context__ and refused.value.__cause__ is None


def test_one_byte_limits_are_inclusive():
    value = decode_frame(
        io.BytesIO(encode_frame(b"x", b"y")),
        script_sha256=hashlib.sha256(b"x").hexdigest(),
        request_sha256=hashlib.sha256(b"y").hexdigest(),
    )
    assert value.script == b"x" and value.request == b"y"
