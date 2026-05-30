# Post-mortem: `databases.query` removed (Notion data-source migration)

**Date:** 2026-05-30
**Feature:** `/tasks` (Notion task status filtering)
**Severity:** Low — caught immediately during first test, no data affected.

## What happened

The first `/tasks` run returned, in Discord:

```
Notion error: 'DatabasesEndpoint' object has no attribute 'query'
```

The command had been written against `client.databases.query(database_id=..., ...)`,
the long-standing way to query a Notion database.

## Root cause

The installed `notion-client` follows Notion's **2025 data-source API**. In that
model a database is a container of one or more **data sources**, and querying moved
off the database onto the data source. The library reflects this: `databases` no
longer has a `query` method (it keeps `retrieve`, `create`, `update`), and a new
`data_sources` endpoint owns `query`.

So the call referenced a method that no longer exists on that endpoint — hence the
`AttributeError`, surfaced to the user as a `Notion error:` string by the handler's
catch-all.

This had been flagged as a risk before the first run (the `/notion_check` output
listed the task DB as a `data_source` object), so the failure was expected-ish and
quick to place.

## The fix

In `notion_api.py`:

1. Added `_get_tasks_data_source_id()` — calls `databases.retrieve(NOTION_TASKS_DB_ID)`
   once, reads `data_sources[0]["id"]`, caches it.
2. Changed `query_tasks_by_status` to call
   `client.data_sources.query(data_source_id, filter=...)` instead of
   `databases.query`.

No change to `bot.py`, `.env`, or the configured database id — `NOTION_TASKS_DB_ID`
stays the database id and the code resolves the data source from it. The status
filter syntax (`{"property": "Status", "status": {"equals": ...}}`) is identical
across both API versions.

## How to detect a recurrence

- Symptom: `'DatabasesEndpoint' object has no attribute 'query'`, or an
  `object_not_found` / version error mentioning data sources.
- Quick check: in the venv,
  `python -c "from notion_client import Client; print([m for m in dir(Client(auth='x').data_sources)])"`
  should list `query`. If `data_sources` is absent, the installed library predates
  the data-source API and the old `databases.query` path applies instead.
- Anything that pins or downgrades `notion-client` could flip which API is in play —
  check release notes before bumping the version (the query surface changes across it).

## Lesson (generalized)

Notion's API has more than one era live in the wild. Any new database operation in
this bot should target the **data source**, resolved from a stored **database id**,
not assume the pre-2025 `databases.query` shape.
