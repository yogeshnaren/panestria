# Bounded diagnostic storage history across process restarts

Selected original R3 outcome: AOS-018-S4/MVP-X13 explicitly requires retained,
bounded source-bound growth observations across restarts. Existing opt-in storage
watch/terminal/Mission Control compares only an in-memory previous sample. A
restarted process therefore loses the baseline for disk-growth and changed
Timeshift-policy warnings. This change retains diagnostic samples behind an
additional explicit private `history_directory` setting. Default behavior and
legacy settings serialization remain unchanged when that field is absent.

The existing observer and foreground `storage watch` use one nonblocking history
lock while collecting. A compatible retained sample can supply only the previous
diagnostic baseline. Current capacity/admission still requires a new OS observation;
past data grants no execution, cleanup, canonical event or release authority.
`storage inspect` stays an explicitly invoked fresh read and creates no history.

New records bind original observation and capture timestamps, exact collector
source-byte identity, current typed settings hash and a filesystem identity derived
from observed device/fsid/geometry. No same-device-number assumption alone is used
across a restart. Baseline age is at most24hours, with future, incompatible and
unconfirmed samples excluded. No timestamp, source certificate or old report is
refreshed. Existing exact filesystem/device comparison remains in the probe.

Storage is an explicitly selected dedicated mode0700 directory, mode0600 regular
lock/samples and held no-follow directory descriptor. Content-hash-named immutable
records have a16KiB bound. Existing record hashes/strict schema/privacy are checked
before reuse. The directory admits at most512 entries including its lock and4MiB
logical data; filesystem overhead is extra. It never prunes, overwrites a sample,
starts an automatic replacement history, queues a competing writer or deletes a
partial/invalid record. Lock, budget, corruption, unavailable fsid and I/O failures
remain visible warnings alongside current capacity; no stale sample becomes zero.

Opt-out, configuration changes, elapsed probe deadline and shutdown retain the
original publication fences. Configuration is rechecked before retention. The
watch stops on a changed configuration rather than saving a result under another
selection. Existing source reports remain intact after opt-out. There is no added
schedule or background job: the chosen foreground watch/observer must be running.

The private history contains selected filesystem path, component labels/numeric
estimates, schedule/retention observations and recommendations, not file contents,
credentials, actual snapshot allocation or project ownership claims. Browser/TUI
metadata keeps its existing no-path/device contract; notices disclose the history
budget/status and previous compatible observation time. This is descriptive
storage history, not a unified general resource inbox, full host/foreground
qualification, metric distribution, Timeshift author attribution or G3 completion.
