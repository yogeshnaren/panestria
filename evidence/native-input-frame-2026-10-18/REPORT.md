# Native input framing component observation

Result: **PASS_COMPONENT**, with no runtime or release authority.

Clean source `58b56a36e5388ef982d351cc8793d7fb20f3a9a8` passes 41 focused checks
in 8.30 seconds: 35 deterministic protocol guards and six actual fixed parser
containers. Ruff, mypy (198 source files), all 11 import contracts, the secret
scan and source diff check pass. The earlier uncommitted recreation run also
passes 41 checks; its separate raw XML remains byte-exact.

The fixed containers receive only public synthetic opaque bytes and a read-only
parser module. They exercise maximum input/EOF and five rejection cases without
executing supplied code or parsing requests. Effective Docker configuration and
exact fixture cleanup are asserted. No database, provider, native vendor CLI,
model, authentication, paid SDK, image download or owner-service work is involved.

`report.json` binds source hashes, exact raw artifacts, observed test suite
attributes, coverage and limits. The previous temporary checkout and original
Oct16 33-case artifacts are unavailable. Those historical results are not
recreated, relabeled or used as the current qualification.

Production input transport is unchanged. Caller deadlines, custom-profile
conformance, execution semantics, actual gateway crash recovery, remaining native
authority boundaries and full G1/G2/G3 remain required. See
`docs/design/44-NATIVE-INPUT-FRAME.md` for the next integration obligations.
