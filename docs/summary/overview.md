# Overview — Quarter Life Pounder Bot

Read this first. It explains what the bot is, how the code is laid out, and how to
run it. For "how do I set up the tokens?" see the root `README.md`; for the deeper
"why does this work the way it does?" follow the links into `deep-dives/` and
`explainers/`.

## What it is

A custom Discord bot for the QLP (USC Games AGP) team — a 3D narrative restaurant
sim — that helps the team run its dev process from inside Discord. It is built up
one feature at a time and is expected to grow.

**Planned feature set (the eventual goal):**
1. Scheduled messaging — timed/recurring posts to channels and member DMs.
2. Meeting recording — join voice, record every meeting, always save an audio file.
3. Transcription — bilingual English/Chinese transcripts (faster-whisper large-v3, local).
4. Notion reading — read any page from the team workspace.
5. Notion task queries — filter the task database by status, assignee, date.

**Built and working today:**
- `/ping` — liveness check.
- `/notion_check` — lists every Notion page/database the bot's connection can see.
- `/tasks status:<choice>` — task list filtered by status (Done / In progress /
  Not started / Pivoted / **Active**, where Active = In progress + Not started).

## How the code is laid out

The bot is a single long-lived Python process. Two source files today:

| File | Responsibility |
| --- | --- |
| `bot.py` | **Discord only.** Intents, slash-command registration, the command handlers, `bot.run()`. It never talks to Notion directly — it calls into `notion_api`. |
| `notion_api.py` | **All Notion calls.** Search, task queries, the data-source resolution, and the helpers that turn Notion's JSON into plain values. |

New integrations (Whisper, the scheduler, voice recording) will be added as their
own modules alongside `notion_api.py`, keeping `bot.py` a thin Discord layer. See
`../deep-dives/` as those land.

## The one pattern that runs through every command

Any command that does real network or compute work follows the same three steps,
because of Discord's rules:

1. **`await ctx.defer(...)`** — Discord fails an interaction that isn't acknowledged
   within ~3 seconds. A Notion round-trip can blow that, so we acknowledge first and
   send the real answer as a follow-up.
2. **`await asyncio.to_thread(...)`** — the Notion SDK is synchronous (blocking).
   Running it directly would freeze the bot's gateway connection, so we push it onto
   a worker thread.
3. **`await ctx.respond(...)`** — the follow-up reply, truncated to Discord's
   2000-character message limit.

This is the template for the slow features still to come (recording handoff,
transcription, larger Notion reads). Details: `../explainers/discord-bot-basics.md`.

## How to run it

Full setup (tokens, intents, invite) is in the root `README.md`. Once `.env` is
filled:

```bash
source venv/bin/activate
python bot.py
```

The bot stays online only while that process runs. Editing the code and wanting the
change live means **restarting the process** — slash commands are registered at
startup, so a new or changed command won't appear until you restart.

## Where things are explained

- **Discord platform mechanics** (gateway, intents, slash commands, the 3-second
  rule): `../explainers/discord-bot-basics.md`
- **Notion integration + data-source model**: `../explainers/notion-integration-model.md`
- **How `/tasks` works end to end**: `../deep-dives/notion-task-queries.md`
- **Things that broke and why**: `../bugs/`
