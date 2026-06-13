# Architecture (Claude's map)

Small, flat, single-process bot. Two source files today; grow by adding helper
modules alongside `notion_api.py`, not by bloating `bot.py`.

## Files
```
bot.py            # Discord wiring ONLY: intents, command registration, the slash
                  #   command handlers, bot.run(). Talks to Notion via notion_api,
                  #   bot state via store, reminders via scheduler.
notion_api.py     # All Notion calls (READ-ONLY). Sync SDK; callers use to_thread.
scheduler.py      # APScheduler: channel reminders + per-task DM reminders. SQLite
                  #   jobstore (jobs.sqlite) -> survives restart.
store.py          # Local bot state: Discord<->Notion associations + current sprint.
                  #   stdlib sqlite3 (botstate.db). NOT in Notion.
requirements.txt  # py-cord, python-dotenv, notion-client, apscheduler, SQLAlchemy
.env / .env.example  # secrets by name; real values only in .env (gitignored)
README.md         # human setup + run + command reference
docs/             # human-facing explanation (summary / deep-dives / bugs / explainers)
claude/           # Claude's workspace (tasks, notes, decisions, memory)
```

## Runtime shape
- One long-lived process (`bot.run()` blocks). Holds the gateway WebSocket open.
- Slash commands registered to the dev guild (DISCORD_GUILD_ID) at startup ->
  appear instantly. Restart required after any command change.

## The IO command pattern (established, reused for every slow command)
1. `await ctx.defer(...)` first — Notion/voice/transcription can exceed Discord's
   3-second interaction deadline.
2. `await asyncio.to_thread(notion_api.fn, ...)` — the Notion SDK is synchronous;
   run it off the event loop so the gateway keeps beating.
3. `await ctx.respond(...)` — followup, truncated to Discord's 2000-char cap.

## Notion layer
- One internal-integration token (`NOTION_TOKEN`). Sees only what's shared with it.
- 2025 data-source model: a database contains data source(s); rows live + are
  queried in the data source. We store the DATABASE id (`NOTION_TASKS_DB_ID`),
  resolve it to a data source id once (cached), and query that.
- Filtering is SERVER-SIDE (Notion's `filter`), never client-side over all rows.

## Current commands
- `/ping` — liveness.
- `/notion_check` — list everything the connection can see (ephemeral).
- `/intro` (public), `/help` (ephemeral, auto-generated).
- Channel reminders: `/remind_in`, `/remind_weekly`, `/reminders`, `/reminder_cancel`.
- Milestone 4 (built, untested live): `/associate` (link Notion email <-> Discord
  member), `/tasks` + `/taskdetail #` (personal, ephemeral), `/setsprint` + `/sprint`,
  `/sprinttasks [dept]` (public), `/remind x` (per-task DMs before due).

## Milestone 4 shape
- Personal-task commands share ONE loader (`_load_personal_tasks`) + ONE sort
  (`_personal_sorted`: due asc, no-due last, name) so task numbers line up across
  /tasks, /taskdetail, /remind.
- query_tasks(assignee_id, sprint, department) builds a type-aware AND filter using
  the cached data-source schema (data_sources.retrieve). Server-side filtering.
- Bindings + sprint in store.py SQLite; Notion untouched (read-only).

## Not built yet
Meeting recording · transcription · Notion page reading.
