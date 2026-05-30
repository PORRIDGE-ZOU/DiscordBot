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
