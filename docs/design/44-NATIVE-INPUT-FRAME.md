# Native input framing prerequisite

The current gateway snapshots a reviewed command and request into host temporary
files. A controller crash can leave that stage behind. Eliminating those files
may be simpler than introducing a second durable resource ledger. This task adds
only the data protocol needed to investigate that approach.

`sandbox/native_tool_input.py` accepts opaque bytes with the following wire form:

| Field | Encoding and constraint |
| --- | --- |
| Version | Exact ASCII `PANESTRIA-TOOL-1` followed by LF |
| Script length | Unsigned big-endian 32-bit integer, 1–262144 bytes |
| Request length | Unsigned big-endian 32-bit integer, 1–65536 bytes |
| Script | Exactly the declared number of bytes |
| Request | Exactly the declared number of bytes |
| End | EOF, with no trailing bytes |

The maximum frame is 327705 bytes. Decoder digests must be separate trusted
lowercase SHA256 bindings, never authority supplied by the frame. Reject an
unknown version, invalid sizes before body allocation, truncation, nonbinary or
overreading sources, trailing bytes and digest mismatches. Partial binary reads
are supported with bounded byte accumulation. Exceptions and the frame's repr
exclude payload bytes. The decoder neither parses JSON nor compiles or executes
the script; even syntactically invalid request data is opaque here.

The caller must enforce read/EOF deadlines and cancellation. A stream that never
closes can block the parser. No production launcher, runner, profile, dispatch,
database or approval behavior changes in this prerequisite.

## Validation and provenance

At clean source `58b56a36e5388ef982d351cc8793d7fb20f3a9a8`, 41 focused checks pass,
including six actual fixed Docker parser cases. Containers inspect nonroot,
network-none, read-only root/parser mount, dropped capabilities, no-new-privileges,
CPU/memory/pid/core bounds and interactive stdin flags. Maximum opaque bytes
pass; truncation, trailing bytes, version, length and digest faults reject.
Fixture cleanup checks the exact random name, purpose and ID. These use Docker's
default seccomp, not the production custom profile or a native certificate.
Source/artifact hashes and raw results: `evidence/native-input-frame-2026-10-18`.

The earlier unpublished Oct16 temporary clone, two local commits and three raw
JUnit artifacts disappeared before publication. Their checkpoint-reported
33-case results cannot be reverified from original bytes. This task recreates
the implementation and records fresh evidence; no original artifact is fabricated
or relabeled. Published prior specs and evidence remain intact.

## Required integration before removing host stages

Audit registered scripts for `__file__`/self-inspection and define an explicit
versioned execution interface. Bind the input channel to the approved profile,
effective Docker configuration and durable authority; preserve historical closed
stdin hashes or require new certificates. Add bounded nonblocking input/output
handling for early exit, blocked readers, pressure, timeout, cancellation and
controller death. Preserve fresh one-use claim, durable intent-before-create and
current-authority-before-start fences. Keep payloads out of argv, environment,
logs and PostgreSQL. Do not silently fall back to host staging.

Finally test the actual gateway's controller-death windows and recovery. The
existing host-stage leak remains unresolved. These component checks establish
no complete AOS003/AOS008/AOS010, G1/G2/G3 or R3 owner acceptance.

Run the focused checks with the frozen environment and cached pinned image:

```bash
uv run --frozen pytest -q tests/unit/test_native_input_frame.py tests/integration/test_native_input_frame_container.py
```
