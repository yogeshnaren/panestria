# Optional protected Build observation

The observer can explicitly open an existing private Build report store in a
new read-only mode. Default construction remains compatible with trusted writers;
read-only construction creates no directory and `_put` refuses every publication.
Workers and browser requests cannot choose or replace the store. No new migration,
proof, key, model, ledger or dispatcher is introduced.

Reuse BuildProgressService under repeatable read, current actor/policy/contract
and existing protected byte/DB/report checks. The PUBLIC-only call option is
checked immediately after the existing goal/policy read, before plan/evidence
inspection. Existing terminal/export callers keep their behavior. The HTTP
transaction is rolled back on success and exception; project share guards are
short-lived and no connection survives response streaming. Reauthorize before
JSON delivery, including after CAS I/O.

Return a closed projection: exact decimal event cursor, final required check
counts/verdict/report references, current plan milestone state/source references,
held/unknown capacity, canonical goal and owner merge, separate NOT_ASSESSED
release acceptance and dispatch NONE. Omit all user-authored descriptions and
raw report/diff/path/prompt/private profile contents. This view is not an artifact
content authority and cannot authorize a merge.

The React panel reads only when opened, aborts on selection/end-session, validates
scope and authority and periodically rechecks protected bytes. A response failure
clears its prior score; local freshness expires at fifteen seconds. No optimistic
results or persisted browser state is introduced. A full check bar deliberately
coexists with ACTIVE/PENDING owner approval; actual release acceptance is separate.

Evidence is an actual browser/PG/Git/Docker-verifier connected journey using the
existing explicit native/auth/capacity fixtures. Initial refusal of a 0664 trusted
runtime script proves the existing script guard remained active. Fix the task's
trusted checkout precondition, retain failures, and remove temporary diagnostic
tracing; never weaken script ownership/hash/mode validation to obtain a pass.
Original live qualification and full AOS-028/G3 cases remain pending.
