# Discord bot basics

A standalone tutorial on the Discord-platform concepts this bot relies on. None of
this is about Python or general programming — it's the Discord-specific layer that
trips up newcomers. If a command "isn't working," the cause is almost always one of
the things below.

## A bot is a long-lived process, not a script

When you run `python bot.py`, `bot.run()` opens a persistent **WebSocket** to
Discord (the *gateway*) and blocks forever. The bot is "online" only while that
process is alive. Close the terminal or the laptop and the bot goes offline. To be
always-on, it has to live somewhere persistent (a small VPS or a Raspberry Pi) —
that's a later decision; a laptop is fine for development.

## Two halves of the Discord API

- **Gateway (events in).** Discord *pushes* events to the bot over the WebSocket:
  a message was sent, someone joined a voice channel, a slash command was invoked.
- **REST API (actions out).** The bot *calls* Discord to do things: send a message,
  DM a member, join voice. The library (Pycord) wraps both; you rarely call REST
  directly.

## Intents — the #1 "why isn't it working" trap

Discord makes a bot declare which **categories of events** it wants to receive.
That declaration is called *intents*. Some intents are **privileged** (Message
Content, Server Members) and must be toggled **on in two places**:

1. In code: `intents.message_content = True`, `intents.members = True`.
2. In the Developer Portal: Bot page → Privileged Gateway Intents.

If the code asks for an intent that's **off in the portal**, the handler runs but
**receives nothing** — no error, just silence. When an event-driven feature
mysteriously does nothing, check the portal toggles first.

This bot enables Message Content and Server Members now (even though `/ping` and
`/tasks` don't strictly need them) so the later DM and message-reading features
don't fail silently.

## Slash commands

Modern bots take input through **slash commands** — the `/something` you type in
Discord. In Pycord you declare one with a decorator:

```python
@bot.slash_command(name="ping", description="Check the bot is alive.", guild_ids=GUILD_IDS)
async def ping(ctx):
    await ctx.respond("pong! 🏓")
```

Two things to know:

### Registration happens at startup, and is guild- or global-scoped
The library tells Discord about its commands once, on connect. Consequences:
- **Edit a command → restart the process**, or Discord won't know about the change.
- `guild_ids=[...]` registers the command to **one server**, where it appears
  **instantly** — ideal for development. Registering **globally** (no `guild_ids`)
  can take up to ~1 hour to propagate. This bot uses the guild scope via the
  `DISCORD_GUILD_ID` env var.

### The 3-second interaction rule
When a slash command fires, Discord expects acknowledgement within **~3 seconds**
or it marks the interaction as failed. A trivial reply (`/ping`) is fine. Anything
slow — a Notion round-trip, transcription, joining voice — must **defer first**:

```python
await ctx.defer()          # acknowledges immediately; "Bot is thinking…"
result = await do_slow_work()
await ctx.respond(result)  # the real answer, sent as a follow-up
```

`defer()` buys you time (up to ~15 minutes) to send the real follow-up. Every slow
command in this bot uses this pattern. Add `ephemeral=True` to `defer`/`respond` to
make the reply visible only to the person who ran the command.

## Dropdown choices

A slash command parameter can present a fixed dropdown:

```python
status: discord.Option(str, choices=["Done", "In progress", "Active"])
```

Discord renders the choices as a menu, so users pick rather than type. `/tasks`
uses this for its status filter.

## Other terms you'll meet

| Term | Meaning |
| --- | --- |
| **Guild** | Discord's internal word for a **server**. Same thing. |
| **Scopes vs permissions** | Scopes (`bot`, `applications.commands`) decide what the bot can be *granted* at invite time; the bot's role in the server decides what it's *allowed to do* (e.g. Connect/Speak for voice). |
| **Token** | The bot's secret password and identity. Lives in `.env`, never in code or git. Leaked → regenerate in the portal. |
| **Snowflake / ID** | The long number identifying any user, channel, or guild. |
| **Ephemeral** | A reply only the invoking user can see. |
