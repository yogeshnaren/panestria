# Explicit public-web policy destination

Start from freshly fetched main41458fe, independent of pending native probe86.
Public search/fetch transmits a question, URL and metadata to external hosts; it
must not be described as local/offline or inherit a permitted model provider.

Add the closed `public-web` destination to PrivacyAxis's existing transport field
`cloud_destinations`. Retain the historical field name and serialized defaults:
adding a default field or renaming would invalidate protected stored policy and
approval fingerprints. Verify a golden policy hash recorded before this change.
The default remains no external destinations. Provider destinations and public
web are separate, explicit grants; no existing policy acquires web access.

All existing scope/trust/certificate/privacy/autonomy denials dominate. Only
PUBLIC data can use public-web, including when the legacy allow_private_cloud
flag is true. Require action external-send rather than letting a read action
bypass send approval. Observe/suggest deny; approve-first requires review; a
policy permission still carries public-fetch-broker/outbound-disclosure
enforcement requirements. A SYNTHETIC_DEV policy cannot send even if its privacy
list contains public-web. A policy revision still uses authenticated owner review,
exact digest/version and revokes existing approvals; no runtime policy is edited
by this implementation task.

This is deterministic policy preparation, not an outbound capability, connection
grant, disclosure receipt, lease/budget reservation or network certificate. The
broker controller must still check current policy, source lineage, approved
query/URL disclosure, grants, budgets/lease and actual SSRF/TLS/redirect/OS
confinement before any future send. No actual network or provider inference is
needed to qualify this task; no G1/G2/G3 promotion follows from policy tests.
