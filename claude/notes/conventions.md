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
- **Slash choices**: dropdowns use `discord.Option(str, choices=[...])`; map each
  choice to its underlying value(s) in a dict (e.g. `TASK_STATUS_CHOICES`).
- **Visibility**: team-internal connectivity output -> ephemeral; shared team info
  (task lists) -> public. George decides per command.

## The IO command pattern (follow for every slow command)
defer() -> asyncio.to_thread(sync SDK) -> respond(), truncated to 2000 chars.

## Discord landmines baked into the code
- Intents in code MUST match the portal toggles or events arrive empty.
- ctx.respond() within ~3s of invocation, else interaction fails. Slow work ->
  ctx.defer() first, followup later.
- Commands register at startup -> restart after any command change.
