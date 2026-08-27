# Gotchas (Discord / Notion / Whisper landmines hit)

## Notion 2025 data-source API — `databases.query` is GONE
- Error seen: `'DatabasesEndpoint' object has no attribute 'query'`.
- Cause: installed notion-client follows Notion's 2025 API. A database is now a
  container of one or more **data sources**; rows live in a data source and the
  query endpoint moved to `client.data_sources.query(data_source_id, ...)`.
  `databases.query` was removed.
- Tell: `search` returns objects with `object == "data_source"` (we saw a
  `datasource` item in /notion_check output).
- Fix pattern: `databases.retrieve(db_id)` returns a `data_sources` list; take
  `data_sources[0]["id"]`, cache it, query that. NOTION_TASKS_DB_ID stays the
  DATABASE id; code resolves the data source from it. (notion_api.py)
- Property filters (status equals, etc.) are unchanged between the two APIs.

## Slash commands register at bot STARTUP
- Edit code -> must restart `python bot.py` for Discord to learn new/changed
  commands. Guild-scoped (DISCORD_GUILD_ID) appear instantly after restart;
  global commands can take ~1 hour. Old process still running = new command absent.

## Intents must match portal
- Intent enabled in code but OFF in Developer Portal = handler silently receives
  nothing. The #1 "why isn't it working" trap.

## A workspace move can break ONE column three different ways (2026-08-26)
Moving to the "Master Task List" DB, `Sprint` became `Sprints` (name), changed from
select to **relation** (type), and its values became `Sprint 1` with a space (format).
Each alone breaks the filter, and the failure modes differ:
- wrong NAME -> the schema check misses, filter silently dropped -> "all sprints"
  quietly, which reads as working.
- wrong TYPE -> `_eq_filter` builds a `rich_text` body for a relation -> Notion 400.
- wrong VALUE -> filter is valid, matches nothing -> "you have no tasks".
Only the middle one is loud. Fix was to resolve columns by ROLE from the live schema
and build filters from the reported type (see conventions.md).

## Notion sharing does NOT cascade across a relation
Sharing the task DB with the connection does not share a database it merely LINKS to.
A relation column then returns page ids the bot can't resolve to titles — the Sprints
DB must be shared separately (••• -> Connections). Tell: sprints display as
"N linked" instead of "Sprint 1", and /setsprint reports the column links to a
database the bot can't read.

## Relation filters take a PAGE ID, not the label
`{"relation": {"contains": "<page-id>"}}`. Resolving "Sprint 1" -> id needs a query
against the related data source; index it once in both directions and cache, or you
get an N+1 per task.
