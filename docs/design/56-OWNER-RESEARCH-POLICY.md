# Dedicated PUBLIC research project policy review

Parent: revision-3 AOS-023-S1, with AOS-007/009 canonical policy reviews. This
closes the owner CLI grant gap between qualified runtime configuration and
staging/collection. It does not qualify a runtime or finish Delegate/G2.

## Outcome and boundary

`research prepare-policy --config research.json --public-web-policy` creates
or validates a dedicated administrative research scope and displays a PENDING
review, proposed policy and exact effect digest. The current policy remains
offline read-only. `research confirm-policy REVIEW DIGEST --config research.json
--public-web-policy` separately records an owner decision and applies that exact
grant. These are local administrative operations, not model-callable API routes.

The selected source/configuration-bound joint certificate is validated through
both PublicSearchCertificateStore and PublicFetchCertificateStore, before scope
creation and again during review/application. No live certificate issuer,
SearXNG install, upstream selection, inference, network dispatch or credentials
are introduced. Test certificates remain explicitly TEST_FIXTURE_NOT_LIVE.

The only active grant is read/external-send, PUBLIC public-web, act-and-report.
Private-cloud permission is false and edit/install/spend/merge/delete/policy-change
remain observe. Collection still requires its own exact contract, capabilities,
zero cash budget, current policy, lease, limits and independent admission.

## Scope and transactions

Private ResearchSettings supplies owner/project/CAS/certificate store/selected
certificate/search settings. A new project is claimed with INSERT ON CONFLICT
RETURNING under the transaction: only its creator may bootstrap a new marker.
An existing project MUST already have the exact canonical administrative marker;
an existing offline Ask project is refused without being widened. Concurrent
preparation cannot turn an independently initialized Ask project into research.

Stable administrative goal/task IDs derive from the project namespace with UUIDv4
version bits for the existing contract schema. The marker contract is fixed to
initial offline read-only policy, one attempt, zero API cash, denied egress and
required human review. Goal and task stay CREATED; no attempt or acceptance PASS
is generated. The fixed marker avoids contract hash drift on certificate renewal.

Creation is atomic with the initial policy, marker and pending proposal. The
bootstrap adds only new unpublished marker entities after initial event allocation;
existing scope locks are acquired before proposal event allocation. Project →
administrative goal → task locks match cancellation ordering. Prepare ends with
the canonical proposal event and read-only certificate validation.

Confirmation uses two acknowledged canonical transactions: decision, then apply.
Each ends its writes with its policy event. A failure between them can leave
APPROVED without an active grant. Retry revalidates both stores, scope, selected
certificate, exact policy/body/digest, expiry and current version before applying.
APPLIED replay is accepted only while the exact selected policy remains current
and the review/certificate remain valid. Changed/stale/foreign/broader reviews
cannot be substituted. Concurrent pending reviews become stale after one applies.

Axis versions increment only when their data changes. Repeating prepare for an
identical current grant returns CURRENT without a new policy revision. A selected
certificate renewal changes trust and overall version, retaining privacy/autonomy.
Policies pinned into already-staged goals are not silently upgraded.

## Verification and operations

Focused actual-Postgres/owner-CLI checks cover pending versus active permissions,
exact digest and explicit intent, a reviewed stage→collect→reader→export journey,
existing Ask/other-owner preservation, invalid joint certificates before writes,
certificate renewal, interruption between approved/applied phases, and concurrent,
stale or broader reviews. HTTP/certificate fixtures are synthetic; no live
qualification, factual support or release pass follows from these checks.

CLI errors omit DSNs, query text, configuration paths and raw exception text.
Keep pending/approved decisions and prior policy revisions for inspection. On
failure inspect canonical state; do not delete history or create a permissive
certificate to force completion. Existing owner services/databases are preserved.
