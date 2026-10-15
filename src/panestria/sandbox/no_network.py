"""Trusted x86-64 launcher: stack an Internet-socket denial over Docker's seccomp.

This standalone file runs with Python -I inside the container. The filter is
inherited across exec/fork. AF_UNIX remains available; AF_INET/AF_INET6 do not.
"""

from __future__ import annotations

import ctypes
import os
import platform
import sys


def main() -> None:
    if platform.machine() != "x86_64" or len(sys.argv) < 2:
        raise SystemExit(125)

    class Filter(ctypes.Structure):
        _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte), ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint32)]

    class Program(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("filters", ctypes.POINTER(Filter))]

    # seccomp_data: nr at offset 0, arch at 4, first syscall argument at 16.
    # Reject alternate architectures/x32, then deny socket(AF_INET/AF_INET6).
    instructions = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, 0xC000003E),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
        (0x35, 0, 1, 0x40000000),
        (0x06, 0, 0, 0x00050026),
        (0x15, 0, 4, 41),
        (0x20, 0, 0, 16),
        (0x15, 1, 0, 2),
        (0x15, 0, 1, 10),
        (0x06, 0, 0, 0x00050001),
        (0x06, 0, 0, 0x7FFF0000),
    ]
    filters = (Filter * len(instructions))(*(Filter(*row) for row in instructions))
    program = Program(len(instructions), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:
        raise SystemExit(125)
    os.execv(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
