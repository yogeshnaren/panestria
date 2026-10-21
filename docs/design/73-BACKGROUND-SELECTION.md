# One finite automatic queue selection

MVP-X11 / AOS-012-S5/S7 partial integration. `background next` reads the bounded
canonical event queue (up to256 historical items, including items outside the
32-row terminal listing). It considers only separately owner-reviewed, linked,
currently eligible, never-started items. It writes no fact, probes no account,
reserves no resource and grants no execution permission.

Ordering is declared value priority descending (3highest), then known fresh
owner/provider reset before unknown, then earliest reported reset, then immutable
queue sequence. Estimates/unknowns do not acquire precise reset times. An unknown
balance remains subject to explicit best-effort policy, all reserves, observed
exhaustion and the same billing/privacy constraints. Ranking is not a quality or
savings score. Bad immutable queue bindings stop inspection rather than being
silently ignored; per-item denied eligibility is summarized by bounded reason.

`background run-next --allow-background-subscription-run` picks one candidate
and calls the existing finite runner. The view is not a reservation: that runner
obtains the existing PostgreSQL session lock and revalidates current immutable
binding/policy, actual linked principal, billing/quota/foreground/storage and
runtime qualification before claims. A selection race can yield WAIT. A denial,
unknown result or failure returns immediately; another job is never substituted.
The command neither resumes a previously started job nor approves its merge.
Existing explicit run/runs/reconcile-run remain the inspection/recovery controls.

There is no installed timer, scheduler daemon, new service, model/provider choice,
automatic policy renewal or quota/billing refresh. Opt-in deployment of a periodic
finite service and full foreground/resource/limit qualification remain separate.
Original historical/live component evidence is not promoted to the new source.
