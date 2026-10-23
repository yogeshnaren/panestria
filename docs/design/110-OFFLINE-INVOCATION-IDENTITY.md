# Original invocation identity in offline Build references

Revision-3 MVP-X11 / AOS-012-S6 requires task/context/model/version lineage.
Confirmed Build archives already retain protected binding/receipt digests, but
omit the binding's request/configuration hashes. Native init frames report a
model name that the existing parser discards. Preserve these existing observations
in new captures without inventing identity for historical data.

## Data and behavior

New captures use offline-reference schema2. Each invocation retains its original
`request_sha256` and `configuration_sha256` from the scope-checked canonical
binding, beside its existing binding/receipt/controller-source hashes. For an
admitted native Build, the request hash identifies the exact selected context
JSON. Other invocation kinds identify their own request, not necessarily a prompt.
Neither hash reconstructs omitted content or identifies a full model context,
tokenizer, template, weights, server-side prompt or provider routing.

The existing native check/Build launcher records `requested_model` from the same
constant used for its `--model` argument. The parser carries a bounded
`reported_init_model` from a validated init frame into the process result. These
are different facts: requested alias versus CLI startup report. Neither proves
the model that generated every response, fallback absence, usage, billing,
semantic correctness or release qualification. A result still has no acceptance
authority. No CLI capability, tool allowance, model selection or invocation limit
is widened. Rejected/incomplete streams do not acquire a successful result.

Capture extracts model metadata only from the original protected admitted-native-
Build receipt after matching its context/scope hashes to the canonical binding.
Missing observations remain null, including legacy receipts recaptured by new
code. It never consults today's launcher/model/configuration as historical proof.
The legacy generic `model` field stays null; use the two explicitly qualified
fields. No raw stream, prompt, response, session ID, auth or path is newly copied.
Names are bounded inert labels, never instructions or tool/model grants.

Schema1 archives remain readable offline with unknown new fields; they are not
rewritten. Schema1 rejects attached non-null schema2 identities. Schema2 requires
both invocation hashes. Explicitly recapturing an old confirmed goal can produce
a new schema2 manifest using original canonical bindings/receipts; that creates a
new archive identity and does not mutate the old manifest or refresh its evidence.
Existing capture/history limits and purpose/rights rules stay in force. There is
no database migration, model/provider call, automatic recapture or evidence repair.

## Validation and limits

Exercise real subprocess/parser transport with synthetic frames, actual isolated
PG/Git/Docker Build completion and capture with mixed known/legacy receipt
metadata, byte-deduplicated recapture, copied-archive CLI reads without DB/auth,
legacy schema/unknown preservation and existing recall/suppression behavior.
Synthetic native frames do not qualify live Claude or provider identity.
Existing historical native observations stay bound to their original source.
Portable hashes verify retained bytes/lineage; they are not a signature or a
recreation of absent external receipts, model internals or configuration content.

This completes one capture metadata outcome, not S6, TC08/09, G3 or R3 acceptance.
Other capture modes, full model manifests/context reconstruction, private/provider
data rights and cumulative qualification remain separate work.
