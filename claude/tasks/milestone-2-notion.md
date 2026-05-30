# Milestone 2: Notion (features 4 + 5)

## 2a — connection check (DONE, pending George's run)
- notion_api.py: list_shared_content() via `search`, paginated, title extraction
  for pages + databases. notion-client is SYNC -> callers use asyncio.to_thread.
- bot.py: /notion_check — defer(ephemeral) + to_thread + 2000-char truncate.
- requirements.txt: +notion-client. .env.example: +NOTION_TOKEN. README: Notion setup.
- George: NOTION_TOKEN in .env, shared a page with connection. Needs to run + test.

## 2b — read a page (NEXT)
- notion_api: read_page(page_id_or_url) -> blocks.children.list, paginated, blocks
  -> plain text. Handle Discord 2000-char limit (truncate / file / paginate — ask George).
- bot.py: /notion_read <url-or-id>.
- Teaching: page content = blocks; pagination; block types.

## 2b — read a page (LATER, deferred)
- Skipped for now; George prioritized status filtering. Still TODO.

## 2c — task queries: STATUS filter (DONE + WORKING in server)
- DB: "Test Tasks Tracker". Props: Task name (title), Status (status), Assignee
  (people), Due date (date), Priority (select), Task type (select).
- Status options: Done, In progress, Not started, Pivoted.
- notion_api.query_tasks_by_status(statuses): server-side status filter, equals
  for one / or-compound for many. ACTIVE_STATUSES = [In progress, Not started].
  Paginated. _task_summary returns name/assignee/due.
- bot.py /tasks: discord.Option dropdown choices Done/In progress/Not started/
  Pivoted/Active. Public reply. defer + to_thread. 2000-char truncate.
- .env: NOTION_TASKS_DB_ID (George must fill from DB URL).
- George's behavior choices: single /tasks dropdown; "Active" label; public; show
  name+assignee+due.
- RESOLVED: data-source model. `databases.query` removed in installed
  notion-client; hit `'DatabasesEndpoint' object has no attribute 'query'`.
  Fixed -> resolve DB id to data_sources[0].id (cached), use data_sources.query.
  See gotchas.md + docs/bugs/2026-05-30-databases-query-removed.md.

## 2d — task queries: "my tasks" (LATER)
- Needs Discord-user -> Notion-assignee mapping (config dict). this_week date filter.

## Conventions established
- Notion logic in notion_api.py, not bot.py.
- Slow/IO commands: defer first, asyncio.to_thread for sync SDK, ephemeral for
  team-internal content.
