# Native memory input and actual gateway recovery

**PASS_COMPONENT**, without runtime or release authority.

Clean `d71ec94` passes289 selected default checks/22 live excluded in121.47s.
Final clean `493078f` passes13 explicit OS cases in17.99s. Production/runtime
files are byte-identical between those sources; only crash-fixture witness
publication and foreign-attempt labeling changed. All source hashes, raw suite
attributes and nine separate observations are retained in `report.json`.

Eight actual NativeToolGateway/controller SIGKILL cases cover committed claim,
intent, created and running phases, with/without lease release. Protected scoped
recovery keeps UNKNOWN, refuses repeat claim, preserves actual task/approval
state and unrelated resources. Five existing explicit OS cases prove isolation,
both input-section tamper refusals and automatic durable claim/launch fencing.
These use fixed synthetic scripts and no vendor native authentication.

The original interface6PASS/1FAIL (invalid test column) and module1FAIL
(incorrect Python module identity) stay byte-exact. Corrected protected scope
checks and dataclass assertions pass. No source or artifact is relabeled.

Ruff/mypy198/11 imports/secret/diff checks pass. No provider/model/vendor CLI/SDK/
auth/new credentials/images or owner services are involved. Other lifecycle,
native/grant/semantic/release and actual owner trial requirements remain open.
