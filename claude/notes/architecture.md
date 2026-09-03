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
store.py          # Local bot state: Discord<->Notion associations, current sprint,
                  #   time-off parse cache. stdlib sqlite3 (botstate.db).
timeoff.py        # #time-off channel -> dated entries. OpenAI (sync SDK, to_thread).
                  #   Knows nothing about Discord; bot.py hands it plain dicts.
joke.py           # /joke + /joke-reply. Jokes come from jokes.json (NO API call);
                  #   only the guess-reaction hits OpenAI. Pending jokes in a
                  #   MODULE-LEVEL DICT on purpose -> a restart forgets them.
jokes.json        # 200 curated jokes (100 food / 100 general). Edit freely.
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
- **Schema-driven, not name-driven (2026-08-26).** The bot declares ROLES it needs
  (name, assignee, status, due, sprint, department, priority, description, updated)
  and resolves each to a real column in two passes: name alias, then property TYPE
  over unclaimed columns. `name` = whichever property has type "title".
  Required = name + assignee; the rest degrade. Every filter body is built from the
  type the schema reports, so select/status/relation/multi_select/number all work
  through one call site.
- Relations are indexed once per column (page id <-> title, both directions) so
  filtering by label and displaying a label are each O(1) after a single query.
- Per-process caches: `_data_source_id`, `_schema`, `_roles`, `_relation_cache`.
  RESTART after any Notion schema change.

## Current commands
- `/ping` — liveness.
- `/notion_check` — list everything the connection can see (ephemeral).
- `/intro` (public), `/help` (ephemeral, auto-generated).
- Channel reminders: `/remind_in`, `/remind_weekly`, `/reminders`, `/reminder_cancel`.
- `/associate` (link a Notion person <-> Discord member), `/tasks` +
  `/taskdetail #` (personal, ephemeral), `/setsprint label` + `/sprint`,
  `/sprinttasks [dept]` (public), `/remind x` (per-task DMs before due), `/dm`.
- `/notion_check` also prints the resolved role->column map + every column's type.

## Milestone 4 shape
- Personal-task commands share ONE loader (`_load_personal_tasks`) + ONE sort
  (`_personal_sorted`: due asc, no-due last, name) so task numbers line up across
  /tasks, /taskdetail, /remind.
- query_tasks(assignee_id, sprint, department) builds a type-aware AND filter using
  the cached data-source schema (data_sources.retrieve). Server-side filtering.
  `sprint` is a LABEL string, normalised through match_sprint() before filtering.
- /taskdetail renders task["all"] — every column in the DB, roles first — so new
  Notion columns appear without a code change.
- Bindings + sprint in store.py SQLite; Notion untouched (read-only).

## Time-off layer (Milestone 6)
- bot.py reads channel history (TIMEOFF_CHANNEL_ID) -> plain dicts -> timeoff.py.
  Same split as Notion: the external service lives in its own module.
- Every message parsed ONCE. store.timeoff_cache keyed by message id, guarded by a
  sha256 of the text so an EDITED message re-parses and nothing else does.
- Model gets the message + author + POSTING TIMESTAMP IN LA — without the timestamp
  "tmr"/"next thurs" can't resolve. Strict JSON schema, temperature=0.
- Entries are resolved (real dates) or unresolved (named event only). Unresolved
  show for UNRESOLVED_VALID_DAYS=14 from posting.
- All windowing in America/Los_Angeles dates. Dated entries match by RANGE OVERLAP.

## Joke layer (Milestone 7)
- Setup + punchline come from jokes.json; only the setup is shown, punchline held
  in _pending[discord_id]. Telling a joke costs no tokens and needs no API key.
- _draw() deals from a shuffled deck per pack, not random.choice — independent picks
  repeat far sooner than people expect (birthday problem). FOOD_WEIGHT=0.75.
- Second (small) call reacts to the guess. Wrapped in try/except: if it fails the
  punchline still lands. The garnish must never cost the meal.
- In-memory by design (George): restart forgets, /joke-reply says so plainly.
- Public, unlike most commands — the guessing needs an audience.

## Known duplication (flagged, NOT refactored)
timeoff.py and joke.py each have their own _get_client()/_model() for OpenAI. Two
copies is tolerable; a THIRD OpenAI feature should trigger extracting a shared
openai_client.py. Deliberately left alone to keep the joke change scoped.

## Not built yet
Meeting recording · transcription · Notion page reading.
