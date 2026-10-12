# Panestria MVP acceptance — R3 completion and review

**Owner-confirmed boundary:** R0–R3, all 31 MVP AOS specs, including 027a and 027b. **Current state:** NOT_STARTED; every checkbox is pending. Documentation/package checks from the previous task do not satisfy runtime tests here.

## Candidate identity and evidence

- [ ] Record repository URL/default branch, immutable candidate commit, build/dependency hashes and reproducible setup.
- [ ] Record exact model/runtime/driver/CLI versions, hardware profile, sandbox profile, owner/project scope and test corpus version.
- [ ] Each of the 31 MVP items has its required positive/negative/security/failure evidence, not just a merged issue.
- [ ] MVP-X01–X06 baseline obligations in the roadmap are covered and tested; missing parent-spec detail receives an acceptance addendum.
- [ ] Attach fixture reports, actual CI run references, safe logs, provenance/artifact manifests, backup/rollback steps and known issues.

## A-1 — offline Ask

- [ ] Network-disabled local Ask runs the fixed ten-prompt set, including three source-linked recall questions and a hostile request for prohibited cloud fallback.
- [ ] Owner/project scope, source attribution, superseded/suppressed facts and policy limits are correct.
- [ ] Warm/cold latency and memory are measured on actual supported hardware. Confirm a hardware-specific target before acceptance; a missed target is not PASS merely because the reply exists.
- [ ] Model absence/resource pressure returns explicit safe degradation; canonical status/approvals do not need an available LLM.

## D-1 — verified Delegate

- [ ] All cited sources were actually fetched and retained with hashes, passage positions and extraction metadata.
- [ ] Fabricated citation/wrong quote/truncated source cases fail or show incomplete evidence. Supported/contradicted/insufficient/unknown judgments are visible and calibrated with reviewed examples.
- [ ] Private-IP, redirect and DNS-rebinding fixtures are denied. Viewed instructions cannot enable privileged actions or access credentials/private mounts.
- [ ] Search/query disclosures and configured provider scope are visible; one explicitly authorized live public brief includes evidence and uncertainty.
- [ ] Disabling research preserves Ask and Build.

## B-1 — concurrent Build

- [ ] Both pinned vendor adapters pass actual scoped compatibility/security checks; missing account/feature evidence is not green.
- [ ] Two permitted independent tasks run in separate worktrees with bounds and fenced attempts; overlapping changes trigger explicit conflict handling.
- [ ] Required checks run on the final integrated candidate tree, not only on isolated patches.
- [ ] Failing test/bad path/stale epoch/tampered artifact/false-done cannot produce completion or merge.
- [ ] Exact effect_digest-bound owner/project/action/base/candidate/check-set/policy/expiry approval controls merge; changing any bound field invalidates authorization.
- [ ] Lost effect response enters reconciliation without blind duplicate action; cancellation stops new admissions and reports in-flight effects honestly.

## Cross-cutting release blockers

- [ ] Task state/event/tracked transaction result commit atomically in one PostgreSQL datasource session; pre/post-commit crash fixtures demonstrate replay behavior.
- [ ] Global cursor concurrent-writer/commit-order/reconnect/duplicate/gap tests show no missed late event; UI reads canonical state.
- [ ] Trust/privacy/autonomy each varied alone; no accidental widening. Wrong owner/project/actor and stale policy decisions are denied.
- [ ] OS filesystem/network/process restrictions deny host-secret, symlink and forbidden destination attempts; malicious hooks/settings/MCP configuration cannot run.
- [ ] Hard cash/process/resource limits and unknown-usage treatment block overspend/retry storms/unauthorized provider switching.
- [ ] Local API Host/Origin/CSRF/auth fixtures pass; secrets, restricted artifacts and sensitive capture do not leak in telemetry.
- [ ] Mission Control shows accurate status, approvals, evidence, traces, cost confidence and authorized/accessible/observed cloud exposure separately.
- [ ] Fresh install, daemon/server restart/reboot, DB unavailable, artifact retention, backup/restore and rollback are reproducible.

## Six required fault drills

| Drill | Passing behavior | Evidence ref / verdict |
|---|---|---|
| Ambiguous external effect | Reconcile before repeat; no blind duplicated merge/send | pending / NOT_RUN |
| Prompt injection | Reader/repo/skill text cannot enlarge actor permissions or egress | pending / NOT_RUN |
| Exhausted entitlement | Pause/refuse safely; no retry storm or unauthorized fallback | pending / NOT_RUN |
| GPU/resource pressure | Foreground remains usable; task state/evidence preserved | pending / NOT_RUN |
| False done | Worker narrative cannot override failed/missing/UNKNOWN checks | pending / NOT_RUN |
| Approval change after crash | Changed payload/policy/candidate invalidates old approval | pending / NOT_RUN |

## Fourteen-day owner trial

- [ ] The owner approves trial scope/data/tasks; start/end dates and candidate versions recorded.
- [ ] Daily representative Ask/Delegate/Build use logs verified completion, human acceptance/corrections, approval burden, refusal reasons, latency/resources and egress decisions.
- [ ] No confirmed unresolved policy/task-state integrity breach. Each incident is triaged, root-caused, fixed and protected by a regression check before acceptance.
- [ ] Candidate-changing fixes re-run relevant gates and extend/restart affected observation; reports clearly identify which version produced each result.
- [ ] Usefulness and usability assessed explicitly, including whether approvals/evidence make decisions understandable. Report real sample size and uncertainty; no statistical efficacy claim from a small trial.
- [ ] Known non-blockers have owner/priority/reason/follow-up. No required safety/durability/functionality failure is waived into PASS.

## Owner decision — two independent records

| Field | Initial value |
|---|---|
| Candidate commit / evidence manifest | unset |
| Gate state | NOT_RUN |
| Trial state | NOT_STARTED |
| Owner acceptance | PENDING |
| MVP state | NOT_STARTED |
| Authorize SOTA implementation | false |
| Next phase authorized | none |

After all required gates/trial pass, the owner records accept/reject with date, commit, evidence and known non-blockers. Only that decision establishes MVP_ACCEPTED. A separate decision names R4 or a deliberately revised SOTA entry scope. Accepting MVP does not automatically authorize SOTA.

If acceptance fails, return to the affected MVP slices and retain the candidate evidence. If MVP is accepted but expansion is deferred, keep a maintenance-only branch/release usable. Do not relabel missing SOTA experiments as MVP defects or claim the full target is complete because its roadmap exists.
