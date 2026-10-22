# Local presentation with saved measurements

This optional pass can add bullet markers to a plain-paragraph local response
without changing its original content. It makes no second model call. It keeps
the original response when the layout is unsupported or ambiguous. Preserving
text does **not** establish that the model's claims are accurate.

Use an existing, currently qualified [private profile service](QUALIFIED_PROFILE_SERVICE.md)
and approved structured style selection from the [style terminal](PROFILE_STYLE_TERMINAL.md).
No key, profile, owner setting or service is created/changed by this feature's
implementation. Upgraded source requires current qualification; old proof is
never refreshed by adding a setting.

Add this field to that service's existing private local Ask JSON configuration,
preserving its other fields and private permissions:

```json
"lossless_presentation": true
```

Restart only your own server when convenient using the existing profile-service
command. Authenticated local status reports `STRUCTURED_PROFILE_ONLY`. This does
not enable profile storage or cloud access by itself. The
[shared charter setting](SHARED_LOCAL_CHARTER.md) is independent and optional.

In the style terminal, review/save `formatting: bullets` as a separately approved
local-context preference. Use the profile Ask terminal with the exact current
profile row/version and `STRUCTURED_RESPONSE_STYLE` purpose. For a plain response
containing multiple paragraphs, expect the original paragraphs with added `- `
markers. The text of facts, numbers, citations and uncertainty stays unchanged.
If the model already returns a list, table, code, indentation or ambiguous layout,
expect the original text and **ABSTAIN**. The pass does not translate or shorten.

The existing authenticated Ask receipt now saves the optional
`usage.presentation` observation in the same database:

- `state`: APPLIED, UNCHANGED or ABSTAIN;
- `elapsed_seconds`: local formatting time, separate from original model latency;
- `input_bytes` / `output_bytes`: exact UTF-8 lengths;
- `words`, `paragraphs`, `words_per_paragraph`: original content counts, excluding
  added layout markers;
- factual support, readability quality and owner preference: NOT_ASSESSED.

Inspect the receipt through the existing owner API/receipt workflow. No plaintext
answer, raw style preference or new content hash is retained. Receipt replay
returns those same observations without another inference. With the setting
false/omitted, or with an ordinary/non-structured Ask request, there is no pass and
no presentation observation. Late profile withdrawal prevents publication.

Focused component checks use disposable PostgreSQL, synthetic keys and a declared
mock local provider; they do not send private data or contact an inference API:

```bash
uv run pytest tests/unit/test_lossless_presentation.py \
  tests/integration/test_lossless_profile_presentation.py -q
```

Full style fidelity/readability/preference, broader model compatibility and the
original cumulative gates/owner trial remain required for R3 acceptance.
