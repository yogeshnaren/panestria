# Inspect retained research evidence

The owner command exports an existing retained request and its claims as offline
HTML or JSON, rechecking actual question/source/quote bytes. It does not yet
accept a new question or run the full Delegate workflow. Search setup remains
deferred at the owner's request. Inspection calls no model, search or public URL.

From the selected checkout with frozen dependencies, use the existing local DB
environment, private retained-store root and IDs of an already retained request.
Never put DSNs/passwords in command arguments or Git:

```bash
install -d -m 700 "$HOME/panestria-research-exports"
uv run --frozen panestria research inspect \
  OWNER_UUID PROJECT_UUID REQUEST_UUID TASK_UUID \
  --store /absolute/private/research-store \
  --output "$HOME/panestria-research-exports/brief.html"
```

Open the local file. Add `--format json` and choose a new `.json` path for data.
The parent must already be canonical, owner-owned and mode0700. Existing output
files/symlinks are refused; use a new filename to repeat inspection. Terminal
metadata reports EXPORTED, classification, count and file hash without question
or URL text. Failure returns exit1 with a bounded unavailable message. Actor IDs
do not authenticate a remote client; this CLI uses administrative local DB access.

- EVIDENCE_PRESENT means the retained passage exists and any supplied quote
  matched. It does not establish that the assertion follows from that passage.
- INVALID_EVIDENCE means a source/quote failed; unchecked URLs/quotes are omitted.
- NO_EVIDENCE means no retained passages were supplied.
- UNAVAILABLE means current claim/lineage inspection could not be confirmed.

Support and contradictions always remain **NOT_ASSESSED**. Empty requests stay
empty; export never approves/completes goals. HTML escapes untrusted text, has no
scripts/resources and displays URLs without active links. Source instructions
are data. Private exports have independent owner-managed retention.

Reproduce the connected fixture with Docker and frozen cached dependencies:

```bash
uv run --frozen pytest tests/integration/test_research_brief.py -q \
  --basetemp=/tmp/panestria-brief-review-UNIQUE
```

Choose a fresh basetemp: pytest owns/removes that selected test directory. The CLI
journey writes `test_real_owner_cli_exports_esc0/exports/evidence.html` and
`evidence.json` below it. These are **synthetic fixture reviews**: fetch
observations are synthetic; DB, protected CAS, Docker reader, deterministic checks
and CLI are actual. The isolated DB is removed afterward; the file is a historical
fixture snapshot. It is not proof of live TLS/SSRF or semantic qualification.

Checks include unrelated assertions, fabricated quotes/source IDs, uncited
statements, later corruption, scope denial, missing question bytes, unchanged
canonical state/events, inert HTML, private JSON and overwrite/symlink/public-parent
refusal. See the [design and limits](../design/51-RETAINED-EVIDENCE-BRIEF.md).
New-request execution, admitted fetch, semantic qualification and full G2 remain
pending; no original gate or paid SDK obligation is waived.
