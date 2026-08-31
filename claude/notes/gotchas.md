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

## A channel is a CONVERSATION — parsing messages in isolation loses the meaning
First live run of /time-off-recently (2026-08-31) reported three people as
unavailable "this week" who were actually talking about **October 11**.

Cause: each message was sent to the model ALONE.
- "I won't be able to attend sunday lab the weekend of fall recess" is undatable by
  itself. The date lived in a DIFFERENT message 40 min earlier ("fall recess/oct 11").
- "I **also** won't be able to attend sunday lab!" is a reply. With nothing to refer
  to, "also" is meaningless.
Both fell into the undated bucket, and the 14-day-validity rule then surfaced them
in the next-7-days view — a confidently wrong answer, the exact failure mode the
design was supposed to avoid.

Fix: CONTEXT_MESSAGES=8 preceding posts travel with every message as read-only
context; the prompt has an explicit CONVERSATION CONTEXT section for "also"/"same
here"/"that weekend" and for dates pinned upthread. The cache key is now
hash(text + context), so changing context correctly invalidates a stale parse.

Generalised lesson: **when an LLM parses user-generated text, the unit of meaning is
rarely the unit of storage.** Ask what a human would need to read to understand this
one message, and send that.

## An undated entry ages out on a timer, not on its event
An entry with no derivable date is shown for UNRESOLVED_VALID_DAYS (14) after
posting. If the session it refers to already happened — or is two months out — the
window is simply wrong. Undated entries should be read as "someone flagged
something", not as "this person is out this week".
