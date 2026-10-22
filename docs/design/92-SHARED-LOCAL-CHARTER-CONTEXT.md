# Shared charter in local Ask context

Structured profile Ask already included the fixed application-owned charter.
Ordinary offline Ask did not. The private local application setting
`assistant_charter: true` now opts both local paths into the same data-free
charter: honesty, calibrated uncertainty, factual/citation preservation,
respectful correction and no psychological inference or permission changes.
No private preference/example is loaded by enabling this setting.

The general ContextCompiler's new opt-in renderer stores only its version and
charter hash alongside existing source hashes/provenance. The complete prompt
stays ephemeral; its canonical pack hash pins all bytes before admission.
Current revalidation understands original packs (no new version metadata) and
renderer2 packs. Changing the server setting affects only new compiles. A
prepared request claims its original hash/prompt regardless of the current
compiler setting, without re-rendering or silently replacing it.

The existing private profile overlay retains its own renderer1/renderer2 audit
contract. Structured style reuses an exactly matching shared charter once;
it refuses a conflicting supplied charter. Existing profile selection,
ciphertext/purpose/version/current-authority bindings, local-only classification
and response/hash omissions remain required. For the new general renderer,
profile budget reservation uses the actual overlay byte delta to avoid charging
the same charter twice. An undersized context refuses before inference; neither
standing rules, a mandatory charter nor pinned references are silently truncated.

The default setting is false, preserving the previous general context layout
and budget. Default profile behavior remains its existing explicitly selected
overlay. The local launcher passes the setting to both general and qualified
profile Ask; authenticated local status reports the selected renderer without
reading keys/profile data or asserting runtime qualification. Mission Control
Ask and keyboard Ask use that same configured local API. No cloud/native
adapter, connection, memory export, new key, model selection or download is
enabled. It is presentation guidance, not a model-compliance guarantee.

Connected PG/crypto/HTTP checks exercise both settings, original/new prepared
contexts, restricted reference provenance, exact private profile overlay,
budget refusal, altered prompt denial and single-call HTTP receipt replay.
They use declared provider/process/key/capacity fixtures and are not model
quality, preference, OS-key/runtime qualification or release-gate evidence.
This delivers shared local context in MVP-X08; private examples, paired measured
style fidelity and ModelManifest compatibility/replacement remain unfinished.
