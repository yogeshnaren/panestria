# Memory pin limits and literal search

Production-readiness plan item 1.23. Before this change, size was checked only
when an Ask ran. One pinned memory item of about 6 KB made every Ask in its
project fail with `pinned_context_budget_exceeded`. Memory search also passed
user text through `websearch_to_tsquery`, so `-5 degrees` became "not 5 or
degree" and matched unrelated items.

## Pin limits at write time

Every pin reaches every Ask, so the whole set of a project's pins is checked
whenever a write makes an item pinned:

- adding a pinned item (`POST /v1/memory`, `POST /v2/memory`);
- correcting an item with `pinned: true` (`POST /v1|v2/memory/{id}/correct`);
- unsuppressing a pinned item (`POST /v2/memory/{id}/unsuppress`).

The set is the project's ACTIVE pinned items whose validity and retention have
not ended, plus the item being written. Items that become valid later are
counted now. Unpinning, suppressing and unpinned writes are never refused by
these checks.

The budget is the default Ask that the TUI and Mission Control send:
2048 context tokens, minus 128 output tokens, minus the 128-token framing in
`kernel/ask.py`. Ask bounds tokens by UTF-8 bytes, giving 1792 bytes. The pins,
the standing rules and the assistant charter, rendered with an empty question,
must fit in 1792 - 256 = 1536 bytes, leaving 256 bytes for the question. The charter is
always counted, so turning it on later cannot strand an accepted pin.

In practice each pin costs its body plus about 212 bytes of source metadata.
With the charter counted, the pins' bodies and metadata share about 650 bytes:
one pin of up to about 440 bytes, or two short ones. A memory item that does
not fit can stay unpinned; search can still retrieve it when it matches.

A project holds at most 10 pins, the default memory search page, so default
searches and Ask (20 hits) never refuse with `pinned_memory_limit`. With the
current byte budget, that is reached only if the budget is raised.

Pin-set writes take a per-project transaction advisory lock after any item row
lock, so two concurrent pins cannot both pass against a stale set.

Pins written before this change are not rewritten. If they already exceed the
budget, Ask still refuses with `pinned_context_budget_exceeded`. Correcting a
pin to `pinned: false` is never refused by the pin checks.

## Error codes

Write-time refusals return HTTP 422 with `{"code": ...}` and write nothing.

| Code | Raised by | Meaning | Owner action |
|---|---|---|---|
| `memory_pin_budget_exceeded` | add, correct, unsuppress | The project's pins, with this item, would not fit the default Ask. | Shorten the item, keep it unpinned, or unpin or suppress another pin. |
| `memory_pin_limit_exceeded` | add, correct, unsuppress | The project already has 10 pins. | Unpin or suppress one. |
| `pinned_context_budget_exceeded` | Ask (unchanged) | This Ask's budget is smaller than the default and cannot hold the pins. | Raise `context_tokens`, lower `max_output_tokens`, or unpin. |
| `pinned_memory_limit` | search, Ask (unchanged) | The requested search page is smaller than the pin count. | Request a larger `limit`. |

No CLI or TUI command adds or pins memory. `panestria build remember-reference`
writes unpinned recall notes, and the Ask TUI only reads. The HTTP API is
therefore the only surface for these refusals. The TUI still shows the Ask-time
codes after `; question was not sent`.

## Literal search

PostgreSQL first turns the query into lexemes with
`to_tsvector('english', query)`. Python then quotes each lexeme as a tsquery
literal and joins them with `|`. The result is bound as one constant
`%s::tsquery`. User text never reaches a tsquery or websearch parser, so `-`,
`OR`, quotes, `!`, `&`, `<->` and `:*` are plain text. Multi-word searches keep
their OR behaviour across lexemes. The old path also stemmed already stemmed
lexemes again (`degre` became `degr`), which could miss exact matches; that no
longer happens. A query with no lexemes (only stop words or punctuation) returns
pins only.

## Query plan

Pins and FTS matches are now separate `UNION ALL` branches. The FTS predicate
filters `memory_revision` directly instead of a materialized CTE of the whole
project, so the planner can use `ix_memory_fts`. Because the tsquery is a bound
constant rather than a subquery, the planner can estimate how many rows match.

`tests/integration/test_memory_limits_query.py` checks that the plan reaches
`ix_memory_fts` when sequential scans are disabled. At 20,000 revisions in one
project, the old query took 81 to 85 ms and could not use the index. The new query
took 5 to 9 ms, and the planner switched between the GIN bitmap scan and a
filtered sequential scan at that size. The pinned branch still scans
`memory_item`, because `pinned` has no index. Adding one would need a migration
and was not needed here.
