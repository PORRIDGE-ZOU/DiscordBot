# Notion workspace migration — the gotchas that broke the task commands

**Date:** 2026-07-10

When the team moved to a **new Notion workspace** (and pointed the bot at a new
"Master Tasks Tracker" database), `/tasks` and `/associate` both broke. Three
distinct causes, all now handled — recorded here so the next migration is quick.

## 1. `/tasks` hung on "thinking…" — missing `Sprint` column
The new DB didn't have a `Sprint` column yet, but `query_tasks` filtered on it, so
Notion rejected the query. The personal-task commands didn't catch the error, so the
interaction never got a reply — Discord spun forever.

**Fix (two parts):**
- `_load_personal_tasks` now wraps the query in try/except and **reports** the Notion
  error instead of hanging.
- The **Sprint filter is optional**: `query_tasks` applies it only when a sprint is set
  *and* the DB has a `Sprint` column (checked against the cached schema). No column →
  show all sprints.

**Detect recurrence:** a task command replies `Notion error: …` (good — it's telling
you what's wrong) instead of silently hanging.

## 2. `/tasks` errored — `NOTION_TASKS_DB_ID` was a page id, not a database id
The id was copied from a **`/p/…` page link**, which is a *page* id. Notion answered
`databases.retrieve → "… is a page, not a database."`

**Fix:** use the id from the database's own link — `…/<DATABASE_ID>?v=<VIEW_ID>` — the
32-hex chunk **before `?v=`**. See `../explainers/notion-integration-model.md`.

## 3. `/associate` said "isn't a member" — the team are guests
Members joined as **guests** (to avoid per-seat cost). Notion's `users.list` returns
**members only**, so guests were unresolvable, even though they're assigned tasks.

**Fix:** `/associate`'s `person` argument accepts an email **or a display name**, and
`find_notion_person` searches workspace members **plus** everyone appearing as a task
assignee (`list_task_assignees`) — guests included. Guests often expose no email, so
match them by the **display name shown in the Assignee column**.

**Detect recurrence:** `/associate person:<email>` fails for someone who clearly has
tasks → they're a guest without an exposed email; use their display name.

## Also remember on any workspace/DB switch
- Notion integrations are **workspace-scoped**: make a new connection in the new
  workspace, enable **Read user information**, share the tracker with it.
- The bot **caches the DB schema per process** — after adding/renaming columns (or
  swapping the DB), **restart** so it re-reads the schema.
- `Sprint` Select options must be named exactly `Sprint1`, `Sprint2`, … to match the
  `f"Sprint{n}"` filter.
- Column names must match the `PROP_*` constants in `notion_api.py`.
