# Link a queued account reference to its private Claude login

The [background queue](BACKGROUND_WORK_QUEUE.md) uses local opaque account UUIDs.
That UUID alone says nothing about which Claude login will be used. This workflow
observes the configured pinned CLI/private profile, retains only scoped identity
hashes, and separately records the owner's exact account-link review. It sends no
prompt and does not launch a worker or change account settings.

Use an existing private Build config and queued item:

```bash
panestria background probe-account --config /absolute/private/build.json ITEM_UUID
```

The collector uses the existing pinned executable and the metadata probe's
bounded `--version`, `--help`, `auth status --json` transport. It preserves held
binary/profile checks, an empty temporary HOME and sanitized environment. It does
not read token files, use private endpoints or return raw CLI output. Only a
first-party subscription with observed personal `pro` or `max` metadata and an
account UUID or valid email can produce an observation. Missing/unknown/Team/API
metadata cannot establish this supported profile. A subscription login is not
proof of inference availability, quota, no extra billing or runtime isolation.

Expect `REVIEW_ONLY`, `observation_sha256`, the exact proposed `link`, and
`link_sha256`. The identity hash is salted with the owner/project/account UUIDs;
the profile hash also binds its canonical directory/device/inode. These are
pseudonyms, not anonymous data. Raw email, account IDs, private paths and token
fields are discarded; observations are INTERNAL local metadata. Original
compatibility-manifest bytes/schema and historical evidence are unchanged.

Review the item/binding/account UUID and observation, then explicitly confirm:

```bash
panestria background link-account --config /absolute/private/build.json \
  ITEM_UUID OBSERVATION_SHA256 LINK_SHA256 --accept-account-link
panestria background account --config /absolute/private/build.json ITEM_UUID
```

An observation must be no more than five minutes old, not future-dated, and match
the owner/project/account. The accepted plan/binding must remain current, policy
unexpired, item unwithdrawn and goal unstarted. The protected observation is
acknowledged before one immutable `background.account_linked` event is appended
under the existing fleet/project locks. Rollback cannot leave a canonical link;
concurrent exact review records one event. Replaying the original review returns
its original sequence and time, even after withdrawal; it never reactivates work.

Re-probe and review to refresh metadata for the same identity/profile/binary.
An account/profile/binary change requires a newly reviewed queued item after
withdrawal, not replacement of the old link. Old evidence remains. `account`
reads the retained observation and DB clock without contacting Claude; it shows
freshness and makes no claim about a login that changed after collection. A
future dispatcher must re-probe the actual profile immediately before launch.

Private mode0400 CAS files live under `BUILD_ROOT/account-observations`, with
at most512 files/1MiB; each item's immutable link history caps at64. A full or
unexpected archive refuses new capture; nothing is pruned/deleted. Do not copy
this metadata into worker prompts or training examples.

Every result retains `execution_authority: NONE`, `billing_verified: false` and
runtime qualification NOT_ASSESSED. Queue eligibility still separately checks
reported quota and billing; a scheduling candidate or linked account grants no
lease or spend authority. The [finite job runner](BACKGROUND_RUN.md) separately combines a fresh same-account
probe, explicit disabled-billing report, quota and foreground checks with the
existing qualified native path. Actual runtime/no-spill validation and complete
S5/S7 evidence remain pending.

[Source-bound checks](../../evidence/background-account-2026-10-21/report.json)
cover real PostgreSQL/CLI/private CAS and metadata fixtures. A separate actual
pinned CLI metadata run observed the dedicated profile's personal Pro login,
with zero inference calls and no billing proof. It is not a G3 or SDK TC04 pass.
