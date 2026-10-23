# Review research claims and sources in a terminal

Use this after a draft has been retained by [local synthesis](LOCAL_RESEARCH_SYNTHESIS.md).
You can inspect its question, exact passages and claims, enter your judgments and
save them with separate confirmation. This command does not run a model, search,
create a grant or mark a task passed. Your assessment is OWNER_REPORTED; automatic
semantic support remains NOT_QUALIFIED.

Use a current private checkout with frozen dependencies and the existing database
URL in `PANESTRIA_DATABASE_URL`. Keep the same private synthesis configuration and
retained research store used to create the draft. Model cache bytes need not be
present for review, but the configured private paths/scope must still be valid.
Do not copy fixtures or use the owner's database for component tests.

```bash
uv run --frozen panestria research review-draft REQUEST_UUID \
  --config /absolute/private/synthesis.json
```

Run in a terminal at least80columns ×24rows. It is a retained snapshot; source and
current authority are revalidated at validation and save. It starts no API/server,
model, worker or search process. Missing, uncertain, cancelled, wrong-scope or
changed retained bytes refuse. No new history is written merely by opening it.

1. Read the question, omitted/shortened passage warnings, source URLs, exact quote
   offsets, model claims and limitations with PgUp/PgDn or j/k.
2. Tab selects the next claim. Choose your verdict: s SUPPORTED, p PARTIALLY_SUPPORTED,
   c CONTRADICTED, i INSUFFICIENT or n NOT_FACTUAL. These are your judgments, not
   model validation. No default verdict is assumed.
3. Toggle the source IDs you used with1–4. Supported, partially supported and
   contradicted judgments require citations. Only retained controller IDs can be
   selected; the model's original citations stay unchanged.
4. Press e, type your own rationale, then Enter to apply it locally. Escape discards
   that edit. Every claim needs a nonempty rationale. Notes are bounded to1024
   characters/2048UTF-8 bytes. This is a private plaintext terminal view; keep it
   away from shared terminal/session recordings.
5. Read the complete draft and all owner judgments to END after editing. Press v.
   Incomplete judgments refuse; otherwise inspect the exact SHA256 and separate
   confirmation. Press y only to record that exact review. Escape returns without
   consent. q exits; pending confirmation is cancelled before quitting.

Expect `OWNER REVIEW RECORDED` after a confirmed canonical response. Notes are
stored in the existing private CAS as RESTRICTED artifacts; event metadata omits
notes. The task stays VERIFYING and model/task/training authority is unchanged.
Existing reviews remain immutable; a new run begins unreviewed local judgments
and can record an explicit correction through the existing service.

If you see `REVIEW UNCONFIRMED`, do not keep pressing y or assume the write failed.
This view never retries. Inspect the latest retained review in a fresh command:

```bash
uv run --frozen panestria research inspect-draft-review REQUEST_UUID \
  --config /absolute/private/synthesis.json \
  --output /absolute/private/new-owner-review.json
```

Compare its exported SHA256 with the digest you confirmed; retain uncertain
history and investigate canonical state if they differ. Existing source/policy/
task checks also apply to inspection. Do not remove evidence or reset the database.

The component checks use actual disposable PostgreSQL, retained CAS/reader and
PTY keyboard interactions, with explicitly synthetic fetch/model setup. They
prove the interaction and canonical fences, not factual accuracy or a G2/G3 pass.
Qualified Delegate support, actual runtime/search and owner trial remain open.
