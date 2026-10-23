# Let offline Ask recall a confirmed Build

This adds one explicit step between [a retained confirmed PUBLIC Build](OFFLINE_BUILD_REFERENCES.md)
and ordinary local memory. It lets Ask find a short note about a past change.
It does not run Claude, grant tools, approve another change or train a model.

Use your existing installed CLI, private Build config and scoped
`PANESTRIA_DATABASE_URL`. Keep credentials in the existing private environment;
do not paste them into the commands or commit them. The database must be up.
No Build runtime/certificates/native login are needed for these three commands.
The private config still needs its complete normal schema and an existing private
root containing the complete `offline-results/` archive.

1. Obtain the `reference_sha256` from the original successful capture. Inspect its
   full diff with `build reference --diff` if needed. Preview a30-day memory note:

   ```bash
   panestria build prepare-recall --config /absolute/private/build.json REFERENCE_SHA256
   ```

   Expect `REVIEW_ONLY`, `preview` and `review_sha256`. Read the exact body, project,
   source and duration. It contains at most160 bytes of original intent and256
   bytes of diff; shortened fields are labeled. Retaining the archive does not
   approve this note automatically.

2. If the preview is correct, use its exact hash and the separate consent flag:

   ```bash
   panestria build remember-reference --config /absolute/private/build.json \
     REFERENCE_SHA256 REVIEW_SHA256 --accept-local-recall
   ```

   Expect `REMEMBERED`, `item_id`, `source_id`, `row_version`, `retain_until` and
   `training_export: DENIED`. Save the identifiers for later suppression. An exact
   replay returns the same memory/expiry with `replayed: true`. It creates no
   duplicate and extends no expiry. To choose1–365 days instead of30, use the
   same `--retain-days DAYS` on both commands. A stale policy/review, changed note,
   suppressed/corrected/expired item or missing archive refuses import.

3. Use your existing [offline Ask terminal](LOCAL_ASK_TUI.md) or
   [Ask command](LOCAL_ASK_SERVER.md) with the **same owner/project database**.
   Ask a relevant question about that Build. Its normal retrieval/privacy/budget
   rules decide inclusion; this is not a pinned instruction or guaranteed answer.
   The canonical receipt records sources and the memory system records retrieved/
   included stages. A different project cannot retrieve this item. Ask still
   needs its own admitted local runtime; importing the note does not start one.

4. To stop future recall, use the saved memory item and its current row version:

   ```bash
   panestria build suppress-recall --config /absolute/private/build.json \
     REFERENCE_SHA256 ITEM_UUID ROW_VERSION --confirm-local-suppression
   ```

   Expect `SUPPRESSED`, a new `row_version` and `history_deleted: false`. A prepared
   Ask whose source was suppressed before claim refuses stale memory; a new Ask
   omits it. Reimport cannot resurrect or overwrite a suppressed/corrected item.
   Withdrawal requires no model or current read/edit permission. It deletes no
   archive, historical database row or storage. Changing/removing an archive alone
   does not withdraw the separately copied memory.

The note is ordinary untrusted memory about a historical verified change. It
establishes neither fresh task acceptance nor rights to train/export.30-day
retention limits retrieval; it is not automatic deletion or a backup policy.

[Original observations](../../evidence/offline-build-recall-2026-10-23/report.json)
retain actual disposable PG/Git/Docker and scripted owner merge, explicit fixture
native generation, concurrent deduplication, stale policy, suppression/correction
and ordinary Ask source revalidation. The default local-model transport is a
fixture. A separate actual cached CPU journey used799 input/13 output tokens and
19.55s generation (18.99s first token). It answered “The calculator Build changed
to `value = 43`.” despite a number-only request. This is a **failed formatting
case**, not a passing quality score or latency qualification; the strict optional
test is preserved. No cloud inference, model download or owner service change.

For developers, run the two default cases in
`tests/integration/test_offline_build_recall.py` with `-m 'not live'` using the
ordinary disposable database fixture. The separate `live` case requires an
explicit `PANESTRIA_RECALL_TEST_MODEL_CACHE` pointing to an existing cache, refuses
an existing model service and creates only its own network-disabled CPU runtime.
Its native Build setup is explicitly synthetic. Do not treat its result as live
Claude qualification or rerun merely to obtain a favorable answer.

AOS-012-S6 remains IN_PROGRESS: broader Ask/Delegate capture, separately eligible
training-purpose examples, full rights/lifecycle integration and original
TC08/TC09/G1/G2/G3 and owner trial remain unfinished.
