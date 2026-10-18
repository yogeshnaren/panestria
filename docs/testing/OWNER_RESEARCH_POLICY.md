# Prepare and confirm a dedicated research project

This is the local owner's policy review step before new PUBLIC research question
staging. It makes no search, fetch, model or paid call. It does not install search
or issue a live runtime certificate. Actual live search setup remains deferred
by the owner. See [the design](../design/56-OWNER-RESEARCH-POLICY.md).

Use current main containing this task, frozen dependencies and a dedicated
current-schema database via the existing `PANESTRIA_DATABASE_URL`. Tests use a
separate disposable database; do not point tests at your review database.

Prepare private [ResearchSettings](OWNER_RESEARCH_COLLECTION.md) with a **new
dedicated research project UUID**, your owner UUID, existing canonical private
CAS/certificate directories and an actual qualified joint certificate matching
the exact search/runtime configuration. Do not reuse an offline Ask project.
No configuration file or flag is a substitute for real qualification.

```bash
uv run --frozen panestria research prepare-policy \
  --config /absolute/private/research.json --public-web-policy
```

Expect PENDING, a review ID/effect digest and the full proposed policy. Read it:
only read and PUBLIC web export may act; private cloud, model destinations,
edits, installation, spending, merge and delete are not enabled. The current
policy still denies egress. No question or query has been sent.

After reviewing, use that exact ID and digest:

```bash
uv run --frozen panestria research confirm-policy REVIEW_UUID EFFECT_SHA \
  --config /absolute/private/research.json --public-web-policy
```

Expect APPLIED and `policy_ref`. Use that reference and returned trust profile
when authoring a **new** PUBLIC research contract, then follow
[question staging](OWNER_RESEARCH_SUBMISSION.md) and
[bounded collection](OWNER_RESEARCH_COLLECTION.md). Existing pinned contracts
do not change when policy changes. An applied policy is permission, not evidence
that a worker or search service is running or a research answer is correct.

Repeating prepare with identical configuration/current grant returns CURRENT
without creating another revision. For certificate renewal, select the new
actually qualified certificate and perform a new prepare/review/confirm; privacy
and autonomy versions stay unchanged if their data did not change. Old review
IDs cannot confirm a different selected certificate. An existing Ask project,
wrong digest/scope, stale version, absent/expired certificate or broader substituted
grant is refused. A failed confirmation may have recorded APPROVED without a
grant; retry uses the same exact review and revalidates before application.

No TUI or GUI is added by these commands. The owner has requested a guided
terminal interface; the present interface remains individual CLI operations.

Focused component check (actual disposable Postgres and owner CLI; synthetic
certificates/HTTPS, no provider keys or live search configuration required):

```bash
umask 077
uv run --frozen pytest tests/integration/test_owner_research_policy.py -q
```

The connected collection case also needs the existing pinned reader image. This
does not pass D-1/G2, semantic support or the full R3 owner trial.
