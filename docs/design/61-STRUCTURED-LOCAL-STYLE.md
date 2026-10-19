# Opt-in encrypted style and assistant charter

MVP-X08 / AOS-017-S4 component. New explicit `STRUCTURED_RESPONSE_STYLE` purpose
connects a bounded `StyleProfile` to the existing encrypted profile → approved
field selection → restricted offline Ask overlay. It adds no provider, key
backend, profile field, credential, grant or default-on personal mode. Other
personal-platform work and full S4/TC05–08 remain incomplete.

The owner stores a version1 StyleProfile JSON string in the encrypted
`communication` field and independently approves it for local context. Language,
audience, detail, formatting and table preferences are bounded/closed; arbitrary
prompts, examples, scripts, action flags and extra fields are rejected. This new
purpose permits only that communication field, exact profile row version and
OFFLINE_LOCAL_MODEL. Malformed structured input abstains without freeform fallback.
Existing OWNER_ASSISTANCE/RESPONSE_STYLE values keep their original renderer.

Renderer2 separates approved private preferences, fixed application-owned charter
and presentation guidance. The charter requires honesty, calibrated uncertainty,
factual/citation preservation, respectful disagreement and correction; it prohibits
hidden psychological diagnoses/goals and permission changes. Style is guidance,
not a response rewrite or proof of faithful rendering. No facts are deleted or
rewritten by deterministic postprocessing. Paired faithfulness, readability and
owner-preference evaluation remain separate required work before full qualification.

The existing source-bound admission revalidates ciphertext revision/key/policy,
selected fields, expiry/suppression/correction, protected context and model limits.
General context remains free of private preferences; the overlay is ephemeral,
RESTRICTED and offline. Only ciphertext/source/request/policy identities plus
render_version2 enter the profile manifest. Neither plaintext preferences nor an
unkeyed input/output/style hash is persisted in Ask/context/learning audit. A new
purpose changes the request hash and cannot replace an already prepared request.

Migration0032 permits render_version1/2 in the existing immutable context table.
It rewrites no history and refuses downgrade while v2 audit exists. Plaintext
profile schema1, legacy renderer1, old request hashes and completed receipts remain
compatible. Application readiness requires the new schema; no owner database is
migrated or service restarted by this implementation. Existing qualified runtime
and explicit personal-mode setup remain prerequisites; historical qualification
is not relabeled for the changed package.

The operator path is the existing enabled v2 Ask API with the new explicit
selection purpose. Default ordinary Ask/TUI mode remains ordinary Ask. A profile
style editor/TUI selector, provenance-linked private example refs, portable model
manifests/replacement and conservative local presentation evaluation remain pending.
No profile/style bytes are exported to ChatGPT, native cloud workers or training.
Validation uses actual PG/crypto with synthetic test keys, migration guards,
legacy Ask regressions and separately marked actual CPU prompt smoke. Model
format acceptance is not a style/faithfulness or OS key-backend qualification.
