# Finite same-contract Build plan revisions

AOS-025-S3 adds an explicit owner proposal after stopped physical work is proven.
This is a linear bounded family in the existing canonical plan tables. It is not
an automatic repair agent. Each accepted child uses fresh task IDs, the original
immutable goal contract and identical declared inventory. Historical failed nodes,
handoffs, proposal bytes and consent remain unchanged.

V1 consent serialization stays byte compatible. A typed V2 revision consent binds
parent proposal hash, exact child/version, configured maximum versions, immutable
VERIFIED_RETURN proof, cumulative wall/cash envelopes, policy and fresh review
expiry into the existing effect digest. Existing migration0033 already supplies
version/parent columns; no new schema is needed. Maximum total versions is two or
three, including unaccepted drafts. Fix the maximum on the first child. Charge
all prior full validated envelopes plus the new one against the original goal
budget. There is no reset from fresh task IDs, unused drafts or a new review.

Use fleet then project/goal/task locking, with the existing current authority
checks and full PlanValidator. Require a linear latest parent, active goal,
PUBLIC privacy and zero API cash, exact contract/inventory, an acknowledged return
proof from this plan family, no held claims or CLAIMED/UNKNOWN invocations, and no
possibly dispatched side effect. Unknown work must be qualified independently;
no elapsed lease, owner assertion or local receipt rewrite releases it. Earlier
terminal tasks stay historical. Only old undispatched pending nodes are fenced
CANCELLED. A proposal itself creates no child tasks, grants or native dispatch.

Identical concurrent proposal replay reuses immutable consent and expiry. A child
still needs separate exact owner acceptance. Superseded pending versions cannot
be accepted. Historical accepted versions can be read, but cannot dispatch or
cancel a newly accepted version. Goal completion after an exact confirmed merge
checks the latest accepted plan, all its completed nodes and absence of any old
live task; old failed/cancelled records do not prevent a genuinely repaired goal
from completing. They are not relabeled successful.

Changed scope/privacy/cost/capabilities are refused and require new explicit
authorization, outside this same-contract pilot. No contract migration, automatic
model repair, handoff reuse, second worker adapter or optional LangGraph loop is
introduced. General repair quality, X10 requirement/evidence progress and stall
reporting, cumulative TC02/03/04 and G3 qualification remain separate work.
