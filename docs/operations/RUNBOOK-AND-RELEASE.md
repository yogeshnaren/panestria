# Operational implementation and release runbook

Implement diagnostics/recovery with their owning slices. The table below states the required behavior; it is not a list of available commands. Recovery today is through the per-feature CLI commands in the [testing runbooks](../testing/) (for example `build`, `plan`, `background reconcile-run`). Operator `backup`, `restore`, `upgrade`, `rollback` and service commands are planned in the [remediation plan](../project/R3-REMEDIATION-PLAN.md) and are not available yet.

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
| Trace export down (local OTel; Phoenix is not used, see ADR 0012 proposal) | bounded export status | Turn off export, keep DB truth intact | Trace system deciding task state |
| Cancel | task/attempt/in-flight effect | Stop new actions now, terminate boundedly, reconcile | CANCELLED from signal request alone |
| Upgrade/restore | consistent app+DBOS backup/manifests | Isolated restore; effects reviewed before launch | Blind remote replay or destructive downgrade |

Record commands/exit/reports/hashes/candidate/environment and mock-vs-live modes. Known non-blockers have owner/priority/follow-up; required safety/integrity/functionality failures cannot be waived into PASS.

## S3 local PostgreSQL scaffold

This section starts the local PostgreSQL service and applies all migrations. It is not a backup drill. AOS-001-TC04 (fresh host) passed in a fresh Ubuntu 22.04 VM; see [R0 technical completion](../reviews/R0-TECHNICAL-COMPLETION.md).

Requires Docker and the Compose v2 plugin. This machine used Docker 29.1.3 and Compose v5.6.0. The image digest is pinned in `compose.yaml`. The published port is `127.0.0.1:55432` only.

```bash
docker compose -f compose.yaml -p panestria-s3 up -d --wait
export PANESTRIA_DATABASE_URL='postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic'
uv run --frozen alembic -c migrations/alembic.ini upgrade head
docker compose -f compose.yaml -p panestria-s3 down -v
```

`upgrade head` applies every migration in `migrations/versions` through the current head, `0041_memory_restricted_fts`; check with `uv run --frozen alembic -c migrations/alembic.ini heads`. Most downgrades refuse to discard data; take a backup before upgrading a database that holds real data. `down -v` removes only the Compose project volume `panestria_s3_pgdata`. The reset helper refuses any other volume name and refuses a symlink data directory.

After `uv sync --frozen --group dev` has populated the cache, `UV_OFFLINE=1 uv sync --frozen --group dev` reinstalls without network. That check is not a fresh-machine bootstrap.

## Trial record

Fourteen-day trial records date/candidate/task kind/verified result/human acceptance/corrections/approval burden/resources/egress/refusals/incidents. Scope is explicit; no unapproved employer/private data. Candidate-changing fixes revalidate tests and extend/restart relevant observation. Owner accepts/rejects exact candidate/evidence; separate record authorizes SOTA implementation. Maintain accepted MVP and rollback while deciding advanced work.
