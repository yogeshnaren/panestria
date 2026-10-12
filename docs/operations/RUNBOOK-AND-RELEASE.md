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

## S3 local PostgreSQL scaffold

This section is the current setup for the empty migration scaffold. It is not the later domain schema, backup drill, or fresh-host proof. AOS-001-TC04 stays `NOT_RUN` until a separate Ubuntu host is available.

Requires Docker and the Compose v2 plugin. This machine used Docker 29.1.3 and Compose v5.6.0. The image digest is pinned in `compose.yaml`. The published port is `127.0.0.1:55432` only.

```bash
docker compose -f compose.yaml -p panestria-s3 up -d --wait
export PANESTRIA_DATABASE_URL='postgresql://panestria_synthetic:placeholder-not-a-secret@127.0.0.1:55432/panestria_synthetic'
uv run --frozen alembic -c migrations/alembic.ini upgrade head
docker compose -f compose.yaml -p panestria-s3 down -v
```

`upgrade head` now applies `0001_scaffold`, `0002_kernel`, and `0003_approval_preview`. `down -v` removes only the Compose project volume `panestria_s3_pgdata`. The reset helper refuses any other volume name and refuses a symlink data directory.

After `uv sync --frozen --group dev` has populated the cache, `UV_OFFLINE=1 uv sync --frozen --group dev` reinstalls without network. That check is not a fresh-machine bootstrap.

## Trial record

Fourteen-day trial records date/candidate/task kind/verified result/human acceptance/corrections/approval burden/resources/egress/refusals/incidents. Scope is explicit; no unapproved employer/private data. Candidate-changing fixes revalidate tests and extend/restart relevant observation. Owner accepts/rejects exact candidate/evidence; separate record authorizes SOTA implementation. Maintain accepted MVP and rollback while deciding advanced work.
