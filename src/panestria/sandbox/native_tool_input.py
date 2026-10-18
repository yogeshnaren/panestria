"""Bounded native input data framing, without execution or dispatch authority.

The caller must bound blocking reads and waiting for EOF. Digests must come from
the separate trusted binding, not the input stream. Production launchers do not
yet use this protocol; it does not change their input channel or sandbox profile.
"""

from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass, field
from typing import BinaryIO

MAGIC = b"PANESTRIA-TOOL-1\n"
MAX_SCRIPT_BYTES = 256 * 1024
MAX_REQUEST_BYTES = 64 * 1024
_LENGTHS = struct.Struct(">II")
MAX_FRAME_BYTES = len(MAGIC) + _LENGTHS.size + MAX_SCRIPT_BYTES + MAX_REQUEST_BYTES


class InputFrameRejected(Exception):
    """Content-free refusal of malformed or mismatched input data."""


@dataclass(frozen=True)
class NativeInputFrame:
    script: bytes = field(repr=False)
    request: bytes = field(repr=False)


def encode_frame(script: bytes, request: bytes) -> bytes:
    if (
        type(script) is not bytes
        or type(request) is not bytes
        or not 1 <= len(script) <= MAX_SCRIPT_BYTES
        or not 1 <= len(request) <= MAX_REQUEST_BYTES
    ):
        raise InputFrameRejected("native_input_invalid")
    return MAGIC + _LENGTHS.pack(len(script), len(request)) + script + request


def _read(source: BinaryIO, size: int) -> bytes:
    try:
        value = source.read(size)
    except (OSError, ValueError):
        raise InputFrameRejected("native_input_invalid") from None
    if type(value) is not bytes or len(value) > size:
        raise InputFrameRejected("native_input_invalid")
    return value


def _exact(source: BinaryIO, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        part = _read(source, size - len(data))
        if not part:
            raise InputFrameRejected("native_input_invalid")
        data.extend(part)
    return bytes(data)


def decode_frame(source: BinaryIO, *, script_sha256: str, request_sha256: str) -> NativeInputFrame:
    if any(
        type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in (script_sha256, request_sha256)
    ):
        raise InputFrameRejected("native_input_invalid")
    if _exact(source, len(MAGIC)) != MAGIC:
        raise InputFrameRejected("native_input_invalid")
    script_size, request_size = _LENGTHS.unpack(_exact(source, _LENGTHS.size))
    if not 1 <= script_size <= MAX_SCRIPT_BYTES or not 1 <= request_size <= MAX_REQUEST_BYTES:
        raise InputFrameRejected("native_input_invalid")
    script = _exact(source, script_size)
    request = _exact(source, request_size)
    if (
        _read(source, 1) != b""
        or hashlib.sha256(script).hexdigest() != script_sha256
        or hashlib.sha256(request).hexdigest() != request_sha256
    ):
        raise InputFrameRejected("native_input_invalid")
    return NativeInputFrame(script, request)
