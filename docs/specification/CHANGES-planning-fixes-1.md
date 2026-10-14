# AgentOS v0.6.1 — planning fixes revision 1

**Date:** 2026-10-11. The architecture version remains v0.6.1; this is an implementation-spec revision. No AgentOS implementation code or production test success is claimed.

| Requested change | Applied result | Review entry |
|---|---|---|
| One acceptance vocabulary | Seven canonical discriminators, schema and examples; explicit legacy skill migration and no raw shell auto-registration | architecture/04-ACCEPTANCE-CHECKS-AND-SKILL-MIGRATION.md |
| Split 027 | 027a R1 depends on 004/009/010; 027b R3 depends on 027a/026. Index, dependency DAG and release documents updated; 38 active specs | backlog.json; specs/AOS-027a.md; specs/AOS-027b.md |
| Actual skills source | Original ZIP, ZIP SHA256, supplied per-file checksums, full inventory and observed smoke evidence included in both complete and R0 packs | attachments/SKILLS-INVENTORY.md |
| Consistent database schema | task_event everywhere, effect_digest fingerprint, required project scope + scope FKs, constrained task state and row_version | architecture/01-CANONICAL-DATA-AND-API-CONTRACTS.md |
| Event ordering chosen | One global identity seq, CACHE 1, serialized append until commit; no per-task cursor. Includes missed-event concurrency and rollback-gap tests | canonical contracts event ordering decision |
| Simpler DBOS recovery | Same PostgreSQL database; one datasource session/transaction commits task state/event/tracked result. Separate schemas, no dual task store. External effects still reconciled | specs/AOS-003.md |
| One Python package | src/agentos sub-packages, one distribution/lockfile, Import Linter boundaries | specs/AOS-001.md; releases/R0-KERNEL-PROOF.md |
| Risk-scaled planning | Checklist 001/004; full 002/003/005; approximately one-day slices | templates/; COMMON-REQUIREMENTS.md |
| Later release drafts | Explicit DRAFT per item and release in backlog metadata and documents | backlog.json |
| Shared boilerplate | Eight repeated blocks moved to one normative common file; spec links to it and keeps specific clauses | COMMON-REQUIREMENTS.md |

## Preservation and validation boundary

Pristine original complete/R0 archives remain in the delivery's originals directory. The original consolidated Markdown is extracted there under its originally requested All_37 filename. The original architecture baseline and original skill ZIP bytes are unchanged. The revised consolidated file accurately labels 38 active specs; the All_37 filename refers only to the preserved original, not a silently miscounted revision.

Official DBOS transactions/datasources and step docs were inspected on 2026-10-11. Datasource transactions support the atomic database outcome/write design; completed transaction results are replayed, while non-database effects remain outside that guarantee. The exact installed release/API still must be pinned and proven against disposable PostgreSQL when planning AOS-003.

This revision validates archive CRC/checksums, source preservation, skill inventory, dependency acyclicity/release ordering, internal Markdown links and acceptance schema/examples. It does not implement/run AgentOS SQL migrations, runtime durability, sandbox, live vendor or hardware benchmarks. The prototype smoke checks are individually distinguished from production gates.

Sources: [DBOS transactions](https://docs.dbos.dev/python/tutorials/transaction-tutorial), [DBOS steps](https://docs.dbos.dev/python/tutorials/step-tutorial), [PostgreSQL sequence behavior](https://www.postgresql.org/docs/current/functions-sequence.html).
