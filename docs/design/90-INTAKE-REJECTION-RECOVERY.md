# Correctable rejection versus uncertain commit

Arbitrary imported Build documents can fail canonical validation. The initial
client treated every non-success reply as unknown, locking even a definitively
rejected bundle until reload. Distinguish this request's confirmed pre-commit
rejection from lost COMMIT acknowledgment or post-commit inspection failure.

On malformed envelope rejection or an acknowledged rollback of KernelDenied,
ValueError/Pydantic or ContractRejected inside the caller-owned write transaction,
add `X-Panestria-Mutation: NOT_COMMITTED`. Mark only after rollback returns. The
header means this request did not commit; it does not prove the plan UUID has no
prior record. Never mark COMMIT/rollback-ack loss, database failures or later reads
as uncommitted. Invalid canonical goal documents return a bounded422 rather than
escaping the handler. Existing privacy/policy/session/atomicity guards remain.

The shared browser client recognizes the header only on Build mutation409/422
responses for the fixed plan/accept paths. It never renders error bodies. A known
staging denial clears the PUBLIC checkbox and unlocks correction with the same
plan ID, requiring another manual review/submission. A known acceptance denial
permits fresh inspection and a separately confirmed decision. Missing marker,
network loss, malformed response, unavailable service and COMMIT uncertainty keep
the original ID/redispatch block. Never infer no-commit from an HTTP status.

Connected checks exercise a real invalid inventory hash and malformed contract,
then actual canonical commit followed by explicit commit-ack loss. The browser
corrects the same plan ID with one manual POST per decision. Existing lost-reply
and acceptance browser cases must continue preserving uncertainty. No worker,
provider, runtime qualification, new migration or release acceptance is involved.
