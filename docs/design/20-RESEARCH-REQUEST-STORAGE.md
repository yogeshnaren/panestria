# Immutable scoped research request storage

Prerequisites: merged #66 contracts and explicit #69 text branch. Continue
AOS-013-S1 with durable request metadata only; source snapshots, claims and
retained fetch authority remain separate pending tasks.

Add migration 0023 after 0022. Research requests bind owner/project/goal/task by
composite foreign keys, pin the question artifact identity/hash/size/classification
by a composite artifact foreign key, and enforce declared count/byte/redirect/time
caps in PostgreSQL. An additive artifact unique constraint enables the pin; it
must preserve all existing artifact rows. A referenced question cannot silently
change its pinned metadata. No question plaintext or credentials enter this table.

The trusted kernel service revalidates closed contracts, checks actor/task scope,
stores the immutable request and emits its task event in the same caller-owned
transaction. Identical scoped retries reuse one row/event; changed payloads deny.
The global audit sequence also orders the receipt. No tool/provider/reader/fetch
effect is authorized by preparing a request. SQL integrity is not proof that the
underlying protected artifact blob exists; SourceStore must establish that later.

Downgrade locks and refuses populated research-request history. Test actual
PostgreSQL scope/artifact mismatches, pinned mutations, idempotence, transaction
rollback, concurrent retry and real dump/restore. Use a uniquely created test
database inside the disposable R1 fixture; leave shared fixture audit history and
owner databases intact. Advance supported local server's exact schema head without
enabling research routes. Full AOS-013 cases/G2 remain pending.
