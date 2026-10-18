# Native gateway without host input staging

NativeToolGateway previously created a host temporary directory containing a
reviewed script and request before claiming dispatch. Controller death could
orphan those input files. The gateway now keeps both bounded snapshots in memory
and sends PR95's digest-checked frame through PR96's explicit stdin transport.
Only the installed read-only launcher and parser are mounted; there is no host
input directory, mounted request/script snapshot or file-mode fallback.

## Versioned execution and authority

ReviewedCommand declares `execution="python-memory-v1"`; the registry digest
includes that field. Unknown interfaces and old registry digests reject. The
gateway requires an explicit `native-frame-v1` profile rather than widening a
closed permit. Existing closed-profile hashes remain stable for other runners.

The container launcher validates lengths, EOF and separately supplied script/
request hashes before parsing the request or executing code. Python executes in
a temporary real `__main__` module with `__name__="__main__"`, a virtual absolute
`__file__`/argv0, and package/spec/loader/cache set to None. Installing that module
in `sys.modules` preserves annotations, dataclasses and `import __main__` behavior.
Direct source/file inspection is unsupported: the virtual file does not exist.
Scripts consume the bound `PANESTRIA_TOOL_REQUEST` dictionary. No request bytes
enter argv, environment, invocation records or events.

The concrete demo writer previously read `/runtime/native-request.json`; it is
explicitly migrated to the global request. Its SHA-addressed reviewed assets keep
historical versions intact. Runtime certificates include all source Python, so
old demo certificates correctly become stale. Controller-provided reviewed
commands must follow the new explicit interface; no general file compatibility
claim is made.

An authority advertising `runner_factory(permit)` supplies the default runner.
Actual DurableToolAuthority calls therefore receive the committed launch intent
and current-authority-before-start fences even when a caller omits an explicit
factory override. Explicit trusted test overrides and non-durable synthetic
authority seams remain available. RegisteredCheckController keeps its explicit
fenced factory. Fresh one-use claim, scope/registry/profile bindings and exact
historical reconciliation remain mandatory; replay never creates fresh authority.

## Validation and recovery

At clean `d71ec94a5592ab795855ca7a99dbcd8cd5727ea3`, 289 selected default checks
pass in121.47s, with22 existing live cases excluded. The final fixture-only
synchronization correction is at `493078ff27ad2baca8fc21829ac5a458459acda8`;
production/runtime hashes are unchanged. On that clean source,13 explicit OS
checks pass in17.99s: eight actual gateway/controller SIGKILL cases and five
existing synthetic gateway isolation/tamper/durable cases. Ruff, mypy198,
11 import contracts, secret scan and diff checks pass. Raw source-bound evidence:
`evidence/native-memory-input-2026-10-18`.

The real gateway runs under actual PostgreSQL and Docker. Kill its owned controller
after a committed claim, committed launch intent, created container or actual
script execution, each with and without lease release. Recover through protected
historical scope: mark a pre-launch claim UNKNOWN or reconcile the exact durable
launch resource. No second claim, task completion or approval change follows;
unrelated matching-attempt resources remain intact. Only fixed public synthetic
scripts execute. Test coordination files contain public phase/mount metadata;
they are not gateway input stages. A no-TemporaryDirectory guard and inspected
mounts assert the absence of the old input-staging path without scanning /tmp.

Original failures remain separate: one test queried a nonexistent schema column
before switching to the protected read API; an actual dataclass check failed
before proper Python module identity was installed. Assertions were preserved.

This removes the gateway's dynamic input resource. Other worker/verifier/demo
setup/workspace lifecycles, autonomous liveness, connected native auth/proxy/MCP,
GrantBroker and full G1/G2/G3 remain unfinished. No model, provider, vendor CLI,
SDK, credential or owner-service work was used. No exactly-once external effect,
native certificate or R3 owner acceptance is claimed.
