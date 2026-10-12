# Operational implementation and release runbook

Implement diagnostics/recovery with their owning slices. Commands are planned contracts, not currently available application operations.

| Situation | Observe | Safe action | Prohibited shortcut |
|---|---|---|---|
| Restart | workflow/task/attempt/boot receipts | Create datasource before launch, recover, inspect unfinished effects | Phantom completion or duplicate paid spawn |
| DB unavailable | bounded readiness and correlation | Refuse new writes/admission; reconnect without losing truth | Memory-only authoritative status |
| Stale worker | epoch/heartbeat/process identity | Fence publishes and observe/reconcile old effect | Old callback overwriting new attempt |
| Approval waiting | exact digest/continuation/expiry/policy | Re-preview and resume dispatch vs finalize correctly | Reuse for changed action/base/candidate |
| CAS response lost | effect/base/candidate/destination receipt | Stable protected-ref query or RECONCILING | Blind repeated/forced merge |
| Corrupt/orphan artifact | SHA and live DB refs | Refuse bad evidence, cleanup proven orphan after TTL | Path existence as success or arbitrary root traversal |
| Model OOM/pressure | actual model/resource snapshot | Stop admissions, unload/degrade, preserve state | Restricted cloud fallback |
| Auth/quota/version | safe mode/manifest/error | Disable affected capability/cooldown; owner official repair | Credential extraction/account pooling/hot-loop |
| Search/reader failure | query/redirect/source status | Incomplete/setup-required; retained denial | Guess missing evidence/silent provider switch |
| Phoenix down | bounded export status | Turn off export, keep DB truth intact | Trace system deciding task state |
| Cancel | task/attempt/in-flight effect | Stop new actions now, terminate boundedly, reconcile | CANCELLED from signal request alone |
| Upgrade/restore | consistent app+DBOS backup/manifests | Isolated restore; effects reviewed before launch | Blind remote replay or destructive downgrade |

Record commands/exit/reports/hashes/candidate/environment and mock-vs-live modes. Known non-blockers have owner/priority/follow-up; required safety/integrity/functionality failures cannot be waived into PASS.

Fourteen-day trial records date/candidate/task kind/verified result/human acceptance/corrections/approval burden/resources/egress/refusals/incidents. Scope is explicit; no unapproved employer/private data. Candidate-changing fixes revalidate tests and extend/restart relevant observation. Owner accepts/rejects exact candidate/evidence; separate record authorizes SOTA implementation. Maintain accepted MVP and rollback while deciding advanced work.
