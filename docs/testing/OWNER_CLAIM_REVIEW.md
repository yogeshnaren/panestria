# Review a retained research draft

This adds an owner judgment to each exact draft claim and its retained passages.
Judgments are explicitly OWNER_REPORTED. They do not qualify the automatic
verifier, complete the research task or grant training rights.

Start with a collected PUBLIC research request and a retained draft, following
[local synthesis](LOCAL_RESEARCH_SYNTHESIS.md). Reuse its private synthesis config
and database environment. Review needs no model cache, inference, search service
or provider credential. Current local-read policy, VERIFYING task/ACTIVE goal,
exact sources, task version and epoch are rechecked.

Inspect the answer and exact retained excerpts, then create a template:

```bash
uv run --frozen panestria research inspect-draft <request-UUID> \
  --config /absolute/private/synthesis.json --output /absolute/private/draft.html
uv run --frozen panestria research prepare-draft-review <request-UUID> \
  --config /absolute/private/synthesis.json --output /absolute/private/review.json
```

Use new output paths in an owner-only directory. Open the draft locally. Edit
each entry's verdict, citations and rationale. Keep its ordinal, claim hash,
request and draft hash unchanged. Every entry needs a nonempty rationale and
SUPPORTED, PARTIALLY_SUPPORTED, CONTRADICTED, INSUFFICIENT or NOT_FACTUAL.
The first three require passage IDs such as `p1` from the retained packet.
You may cite a retained contradiction omitted by the generated claim. An ID
proves passage membership, not judgment correctness. Repeated sources are not
independent votes.

Validate the edited file and inspect the returned confirmation SHA256:

```bash
uv run --frozen panestria research check-draft-review <request-UUID> \
  --config /absolute/private/synthesis.json --review /absolute/private/review.json
```

This writes no event and calls no model. To retain those exact judgments, use
the returned digest in a separate command:

```bash
uv run --frozen panestria research record-draft-review <request-UUID> \
  --config /absolute/private/synthesis.json --review /absolute/private/review.json \
  --sha256 <confirmation-digest> --accept-owner-review
uv run --frozen panestria research inspect-draft-review <request-UUID> \
  --config /absolute/private/synthesis.json --output /absolute/private/reviewed.json
```

Expect OWNER_REVIEW_RECORDED, assessment_source OWNER_REPORTED and no task or
training authority. Notes are RESTRICTED private artifacts; stdout and canonical
events contain metadata, never rationale text. Inspection revalidates the draft
and source bytes. Changed/stale/cancelled drafts, missing evidence, bad citations,
unfinished entries, absent explicit intent and wrong digests refuse. An export
failure does not erase a committed review; inspect with a new path.

Corrections append immutable reviews, up to64 per request. Identical judgments
replay the original receipt without another event; replaying an old review does
not replace a newer correction. Original drafts and earlier judgments remain.
Qualified semantic verification, broader planning and actual search/cumulative
G2 validation remain required.

The [component evidence](../../evidence/owner-claim-review-2026-10-21/report.json)
uses real disposable PostgreSQL/CAS/reader/CLI, an explicit model-output fixture
and no live inference. It checks exact confirmation, private notes, corrections,
replay, original task state and cancellation/claim-binding guards.


For keyboard review without editing a JSON template, use the
[exact claim-review terminal](RESEARCH_CLAIM_REVIEW_TUI.md). It uses this same
canonical review service, current-source checks and OWNER_REPORTED limitations;
full scroll review and separate digest confirmation are required.
