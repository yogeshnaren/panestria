# Explicit reviewed native Build model

Revision3 MVP-X11 requires a preferred model. The prior launcher always requested
`haiku`; an account/configuration hash alone did not make another choice visible
to its owner. This component adds a deliberate foreground selection, preserving
the legacy default. It does not complete model-scoped background scheduling.

Private Build settings may explicitly select `claude-haiku-4-5-20251001`,
`claude-sonnet-5` or `claude-opus-5`. These closed request identifiers are not
availability, subscription entitlement, provider weights, billing or quality
evidence. No floating/hybrid/Fable selection, provider change, download or CLI
upgrade is introduced. Omitted settings retain original serialization and behavior.

An explicit selection needs a schema3 `claude-public-bash/model-context-v2`
declaration with a visible exact requested model. The trusted intersection compares
that field independently of its configuration hash at preflight, reservation,
monitoring, tools and final publication. Schema1/2 declarations cannot acquire
that permission by reinterpretation. Existing conservative shared call/context/
wall reservations, current policy/account, revocation and expiry still apply.
Changing model or grant in an active controller invalidates retained authority.
The review terminal states that availability/billing/weights are unverified.

The request is included in the runtime identity, worker profile/inventory,
native invocation binding and protected return receipt. A different or legacy
certificate/inventory cannot qualify it. `native qualify-build --model ID` retains
the original complete OS/native case set and requires its actual original native
observation to match requested and reported startup model before issuing a
model-specific expiring certificate. Ordinary tests, template/config editing and
connection decisions issue no certificate.

The isolated launcher passes the exact ID and explicit settings containing one
`availableModels` entry, an empty `fallbackModel` chain and
`switchModelsOnFlag: false`. Native tools, repository config, hooks, credentials
and environment restrictions remain unchanged. Startup, assistant-model and
result model-usage metadata must stay on that ID; mismatch stops processing and
never starts another Panestria model/provider attempt. Reported identity does
not prove underlying weights or all physical traffic. The observed disabled-fast-
mode reason `model_not_allowed` is allowed only with an explicit selection and
fast mode off; unknown reasons and fast mode still refuse.

Primary compatibility references read2026-10-23: [Claude model configuration](https://code.claude.com/docs/en/model-config)
and this workstation's checksum-pinned CLI2.1.273 `--help`. Documentation describes
exact IDs, noninteractive switch refusal, allowlists and alias/client changes;
it does not establish account access or billing. Two actual empty-auth zero-turn
startup checks cover Sonnet5/Opus5 metadata and hostile configuration isolation
without owner login, inference or tool execution. Full conformance remains required.

Existing background policies remain immutable and fixed-model. They refuse an
explicit foreground selection rather than upgrading queued work. Preferred-model
policy/window/account/run integration is next; stale billing/consent is not renewed.
Offline Build references already retain separate requested/reported model fields
and UNKNOWN training rights. No original gate or extension case is promoted.
