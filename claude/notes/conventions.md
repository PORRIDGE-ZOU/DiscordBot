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

## Discord landmines baked into the code
- Intents in code MUST match the portal toggles or events arrive empty.
- ctx.respond() within ~3s of invocation, else interaction fails. Slow work ->
  ctx.defer() first, followup later.
