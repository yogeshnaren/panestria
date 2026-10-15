# Test execution and evidence design

The catalog mixes source-bound historical observations and future PLANNED/NOT_RUN groups; inspect each case rather than treating all as complete or all as unrun. Cursor creates their real assertions with each slice. test-catalog.json supplies IDs/node paths/lanes/expected behavior; requirement-traceability.json retains exact source clauses; implementation-slices.json supplies selected work. Documentation validation is not application test success.

## Lanes and fixtures

Unit/contract use pure logic/fake transports. Migration/integration use real disposable PostgreSQL. Security/chaos exercise actual OS/process/DB boundaries with synthetic fixtures; E2E covers CLI/browser paths. Live requires actual supported hardware/vendor/provider/account conformance under scoped consent. Mocked JSONL or fake transport cannot satisfy a live case. CI lacking an OS capability records SKIP; promotion still needs evidence from a certified runner/host.

Fixture families: tiny Python candidate repo and protected acceptance bundle; two owners/projects/contracts; stable-key fake effect service with lost responses; signal barriers around DB commit/process start/blob finalize/approval/Git CAS; synthetic credential sentinels and hostile configs; hermetic resolver/connector/redirect/compression/MIME/Unicode sources; ten Ask questions/five adverse briefs/10–20 reviewed MVP tasks; sanitized vendor streams; browser session/SSE/digest/unsafe-markdown fixtures.

No internet in deterministic CI; no actual host credentials or metadata endpoints in attack fixtures. Fake resolver/transport is unit evidence, not OS network evidence. Protected required tests are immutable to the worker. Candidate code still executes only in no-secret/no-network verifier sandbox.

## Planned commands after implementation

~~~text
uv lock --check
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen mypy src/panestria
uv run --frozen lint-imports --config .importlinter
uv run --frozen pytest -m 'not live' --junitxml=evidence/ci.xml
uv run --frozen pytest -m 'security or chaos' --junitxml=evidence/boundaries.xml
uv run --frozen pytest -m live --junitxml=evidence/live.xml
~~~

The live command is a future separately scoped action. Register markers and gate_case_id/candidate_commit/fixture_digest through pytest user_properties. Test collection must include each required ID, with every required parameter assertion passing. Empty suite, duplicate IDs, skipped/xfail or missing cases cannot turn green because a command exited 0. Place lane-specific files as needed and update node paths in the implementation manifest.

## Gate evaluator contract

Input: required manifest, actual JUnit/structured report receipts, candidate/environment/corpus hashes, compatibility manifests and known blockers. Validate against schemas/case-result.schema.json; check every required case exists, exact candidate/version/hash, correct lane and LIVE vs HERMETIC/OS_BOUNDARY mode, command exit and immutable report/artifact proof. FAIL for failed case/blocker; INCOMPLETE for missing/SKIP/NOT_RUN/UNKNOWN/wrong candidate/mock-for-live. PASS only for complete actual evidence. Case-result text supplied by an LLM is not a trusted test runner receipt.

Version each scenario's parameters and assertion→requirement IDs; splitting a group preserves release requirements. Run changed/dependency checks per slice, cumulative G0/G1/G2/G3 at promotion, all MVP tests/six faults before trial. After changed candidate revalidate affected/cross-cutting gates and document/extend or restart observation. Report sample size/abstention/confusion honestly.

## Gates and owner review

G0: synthetic workflow/contract/state/events/approval/DB recovery. G1: A-1 offline Ask, B-single and actual sandbox/adapter/resource/auth proof. G2: D-1 with deterministic evidence plus separate support/uncertainty and live public brief. G3: B-1 two actual workers/final-tree checks, Mission Control, redacted traces/usage/exposure, cumulative security/recovery and trial.

Six faults: ambiguous external effect, prompt injection, exhausted entitlement, GPU/resource pressure, false done and approval changed after crash. R3 requires 14-day consented daily use with incident regressions resolved and exact candidate tracked. Owner acceptance and SOTA authorization remain separate. Latency targets are set from hardware evidence before acceptance; no retroactive hiding of failed targets.

## Revision 3 gate additions

G0/G1/G2 original manifests remain 20/72/96 cases. G3 now requires **157 cases**, comprising the 124 original cases plus 33 R3 extension cases under existing AOS case prefixes. The case-result schema and seven verifier discriminators are unchanged. Match the complete active manifest, not a hard-coded four-cases-per-AOS count. An evaluator that ignores new cases is incompatible and cannot PASS revision-3 G3.

`test-catalog.json` marks new nodes NOT_RUN, including real-phone and target-host LIVE requirements. Implement/register real node/assertion mappings and exact runtime/source evidence while coding. Planning validation and default CI are not that evidence. The machine-readable pretrial subset has 156 cases and excludes AOS-030-TC04, which records the 14-day trial/owner decision. Pretrial readiness does not PASS final G3; all 157 are required afterward.
