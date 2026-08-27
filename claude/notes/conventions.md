# Conventions (this codebase)

Established as the bot is built. Follow these; don't introduce a second way.

- **Library**: Pycord (`import discord`, `discord.Bot`). Not discord.py. Never
  install both.
- **Secrets**: all via `.env` + python-dotenv, read with `os.environ`. Names go in
  `.env.example` (never real values). Never hardcode tokens/keys.
- **Slash commands**: `@bot.slash_command(...)`, registered with `guild_ids=GUILD_IDS`
  so they appear instantly in dev (DISCORD_GUILD_ID). Global = slow propagation.
- **Comments**: explain the Discord-specific *why* (intents/portal sync, 3s rule,
  gateway) for the human reader. Skip explaining general Python.
- **Structure**: single `bot.py` for now. Split into modules/cogs only when George
  approves it as its own task.

- **Notion**: all calls in `notion_api.py`. Database id in `.env`
  (`NOTION_TASKS_DB_ID`), resolved to a data source id (cached) before querying.
  Filtering is server-side via Notion `filter`, never over all rows in Python.
- **NEVER hardcode a Notion column name or a filter shape.** Declare what the bot
  needs as a ROLE in `ROLE_ALIASES` / `ROLE_FALLBACK_TYPES`, resolve it against the
  live schema (`resolve_roles()`), and build the filter from the type the schema
  reports (`_eq_filter`). A new column/rename/type change must not need a code edit.
- **Crucial vs optional roles**: only `name` + `assignee` are required
  (`REQUIRED_ROLES`). Everything else absent = that filter is skipped and that
  display line is dropped. Missing a required role raises `MissingPropertyError`,
  which commands surface verbatim — never a silent empty result.
- **Slash choices**: dropdowns use `discord.Option(str, choices=[...])`; map each
  choice to its underlying value(s) in a dict (e.g. `TASK_STATUS_CHOICES`).
- **Visibility**: team-internal connectivity output -> ephemeral; shared team info
  (task lists) -> public. George decides per command.

## The IO command pattern (follow for every slow command)
defer() -> asyncio.to_thread(sync SDK) -> respond(), truncated to 2000 chars.
Applies to sqlite (store.py) too — it's blocking; wrap in to_thread.

## Bot state (Milestone 4)
- Bot-owned state (associations, current sprint) lives in store.py SQLite
  (botstate.db), NOT in Notion. Notion stays READ-ONLY. botstate.db is gitignored
  live state, same handling as jobs.sqlite.
- Notion property names are constants (PROP_* in notion_api.py) — rename in one
  place. Filters are built type-aware from the cached data-source schema
  (_eq_filter), never hardcoded per type.
- Personal-task commands (/tasks, /taskdetail, /remind) MUST share the one loader
  (_load_personal_tasks) + sort (_personal_sorted) so task numbers stay consistent.
- Per-task DM reminder jobs are namespaced "taskremind:<discord_id>:<i>"; keep them
  out of /reminders (channel-only).

- Loose value matching uses `_norm()` (lowercase, alphanumerics only) so
  "Sprint 1" == "sprint1" == "1". Use it for every user-typed-vs-Notion compare.
- Relations hold PAGE IDS. Index the related data source ONCE in both directions
  (`_relation_index`) — never one lookup per row.

## Discord landmines baked into the code
- Intents in code MUST match the portal toggles or events arrive empty.
- ctx.respond() within ~3s of invocation, else interaction fails. Slow work ->
  ctx.defer() first, followup later.
- Commands register at startup -> restart after any command change.
