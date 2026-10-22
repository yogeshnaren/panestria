# Explicit exact plan acceptance

Extend the existing Build input with a separate owner-selected
`mission-control serve --build-plan-review` mode. It includes staging/inspection
and adds one exact plan-acceptance action. A distinct HMAC purpose and cookie
prevent intake-only sessions from gaining acceptance authority. Refuse combined
Ask/research/evidence/final-review modes. `--build-intake` and the default observer
continue to deny the accept endpoint. No existing deployment is silently upgraded.

Display the full retained PUBLIC contract, checks, DAG, literal paths, declared
inventory, validation, budgets, effect digest and expiry before a separate
checkbox/confirmation. POST `/v1/mission/build/plans/{plan_id}/accept` accepts only
`effect_digest` and exact boolean `accept_plan:true`. Under the project lock,
recheck session/CSRF in the committing transaction before and after the existing
PlanStore.accept call. Protected inspection enforces current policy and PUBLIC
classification. PlanStore enforces the bound digest, expiry/current goal, latest
plan and membership. Do not reproduce its acceptance state machine in the UI.

The canonical transaction creates CREATED tasks/dependencies and one immutable
acceptance/event. It starts no attempts, workers, model calls or merge dispatch.
Repeated identical acceptance is canonical replay with no additional tasks or
consent extension. A lost reply is UNCONFIRMED; hide the action and inspect the
same UUID. Never automatically reissue acceptance. GET can confirm ACCEPTED or
PROPOSED after an ambiguous reply; another manual decision needs a new review.
A reloaded cookie permits inspection but CSRF remains memory-only, requiring
pairing before a new mutation. Browser expiry display is advisory; server time
and canonical guards decide. No new migration or runtime qualification.

Connected evidence uses real disposable PG/HTTP/CLI pairing/Chromium, declared
fixture inventory and an explicit committed-reply loss. The expired-consent case
changes only the preparation clock SELECT in the test, then exercises actual
stored consent/digest and the unchanged server-time rejection. It is not elapsed
fifteen-minute operational evidence. Live workers, original release gates and
owner acceptance remain separate.
