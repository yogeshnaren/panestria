# Pinned local model manifests

R3 MVP-X08/AOS-017-S6 needs an application-owned model identity connected to
actual work. The private `pin_model_manifest` setting starts disabled. On the
supported CPU/raw-text local launcher it describes the already verified cached
model after normal startup/isolation checks, then binds the provider once.
There is no download, automatic selection, in-place replacement or GPU/JSON
manifest rollout. Existing unbound routes retain their legacy behavior.

The versioned public manifest identifies the pinned Ollama bundle, weights,
template/system layers, quantization from the verified configuration, runtime
image, actual engine/library/bridge byte hashes, text/no-tool capability, context
bound, fixed generation profile, capacity policy and license artifact references.
The tokenizer identity is explicitly its GGUF containing artifact; its independent
identity/equivalence has not been extracted. Evaluation remains NOT_EVALUATED.
Capacity references describe the enforced profile, not a measured fit/latency
certificate; per-request foreground admission still runs. Hashes are local
observations, not protection against a compromised host or in-place host updates.
Runtime file hashing is cached by inode/size/mtime/ctime, shared with the existing
profile boundary observer. Startup still checks every model blob independently.

At prepare, Ask stores the full manifest in existing immutable context-pack
metadata, and pins its digest in the ephemeral inference request. No question,
profile plaintext, response or new private content hash enters this manifest.
General/profile prompt renderers, scope and provenance remain application-owned.
At claim the retained record, prepared manifest and inference digest must match.
Changed tokenizer/template/system/quantization/tools/modalities/context rules
deny reconstruction. Context-compatible runtime identities still cannot repin
an old request: the provider requires its exact digest before HTTP and again
before returning a completed result. Its binding cannot be changed in place.

Completion checks the actual returned identity against the retained manifest
before writing completion/usage. A new-work default cannot rewrite an existing
attempt's receipt or authorize a different model for it. Existing cancel,
deadline, policy/session/profile revalidation and no-extra-spend rules remain.
Metadata/status and canonical receipts expose public model identity; restricted
profile response/hash omission is unchanged. Receipt replay performs no inference.

The existing immutable context records supply persistence and rollback: no new
table, migration, second prompt store or destructive downgrade is needed. Refusing
an incompatible replacement leaves original context/memory/deadlines intact.
Restoring the original supported provider/configuration can consume the original
pin; it never transfers embeddings/KV caches or silently rerenders an active
attempt. Replacing new-work defaults requires a separate reviewed implementation
and applicable compatibility/quality/runtime evidence. Adaptive selection is R4.

Connected checks cover replacement refusal/rollback, tampered/missing pin, late
wrong-identity publication, startup wiring, one-call receipt replay and encrypted
profile separation. Their model/process/capacity identities are explicit fixtures.
The optional live case uses only an explicitly selected existing read-only cache,
an actual CPU container/Unix socket, disposable PG and ASGI HTTP; it claims neither
physical TCP nor factual/style quality. Original required cases/gates/trial remain.
