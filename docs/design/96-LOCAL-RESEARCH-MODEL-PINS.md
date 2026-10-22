# Model identity before a retained research draft

Extend [the opt-in CPU JSON expectation](95-LOCAL-BUILD-MODEL-PINS.md) to local
query proposals and synthesis drafts. The existing public identity export is
reused; private SynthesisSettings may name `model_manifest_file`. A shared strict
loader reads that file only for genuinely new work, after prior-intent handling
and before the acknowledged STARTED event. Configuration loading, inspection and
canonical replay do not open today's model-selection file.

The original request digest and immutable STARTED payload bind the selected
manifest before startup/generation. LocalDraftModel receives that exact snapshot;
it cannot select another file after acknowledgment. Actual owned CPU startup
describes/binds its JSON runtime, then the existing current-source guard runs
before inference. Wrong request or returned identity refuses publication without
fallback, retry or output. Existing current policy/task/source checks remain.

The retained output includes the original public manifest and inspection compares
it to the original STARTED record, independently of current defaults. None/legacy
fields are omitted so historical canonical bytes/hashes and private SecretStr
serialization remain unchanged. The same protected CAS/events remain the store;
there is no migration, shadow lifecycle or new export of private profile data.

Query quality/factual support remain NOT_ASSESSED; citations are not verified
claims, and no web/task/training/approval authority follows from model identity.
Actual search remains owner-deferred. Connected evidence distinguishes real
PG/CAS/isolated-reader/intent/replay checks from declared generation/HTTPS/runtime
fixtures. This is partial S6 compatibility, not general replacement, model quality,
full original gates or the real owner trial.
