"""Quarter Life Pounder Discord bot.

Milestone 1: come online and answer a /ping slash command. This is the smallest
real bot — it proves the whole chain works (token -> gateway -> intents ->
slash command -> response) before any feature is added.
"""

import asyncio
import os

import discord
from dotenv import load_dotenv

import notion_api

# Load DISCORD_TOKEN (and optional DISCORD_GUILD_ID) from the .env file into the
# process environment. Must run before we read them below.
load_dotenv()

# KeyError here = .env missing or token blank
TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")  # optional; None if unset

# --- Intents -----------------------------------------------------------------
# Intents tell Discord which categories of events to push to us over the gateway.
# They MUST also be toggled ON in the Developer Portal (Bot page) or the gateway
# silently withholds those events — the classic "my handler runs but receives
# nothing" trap. message_content and members are *privileged* intents; we enable
# them now because later features need them (DMing members, reading messages).
# /ping itself doesn't strictly need them, but keeping code and portal in sync
# from the start avoids surprises.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = discord.Bot(intents=intents)

# A slash command registered with guild_ids appears INSTANTLY in that server.
# Registered globally (guild_ids=None) it can take up to ~1 hour to propagate.
# We use the guild scope during development if DISCORD_GUILD_ID is set.
GUILD_IDS = [int(GUILD_ID)] if GUILD_ID else None


@bot.event
async def on_ready():
    """Fires once after login + the gateway connection is established."""
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    print("Bot is online. Press Ctrl+C to stop.")


@bot.slash_command(name="ping", description="Check the bot is alive.", guild_ids=GUILD_IDS)
async def ping(ctx: discord.ApplicationContext):
    """Reply to /ping.

    ctx.respond() must be called within ~3 seconds of the command being invoked,
    or Discord marks the interaction as failed. A trivial reply like this is well
    inside that window; slow work (recording, transcription, Notion calls) will
    need ctx.defer() first — that comes up in later milestones.
    """
    await ctx.respond("pong! 🏓")


@bot.slash_command(
    name="notion_check",
    description="List the Notion pages/databases the bot can see.",
    guild_ids=GUILD_IDS,
)
async def notion_check(ctx: discord.ApplicationContext):
    """Connectivity test for Notion: list everything shared with the connection.

    This is the first command that does real network I/O, so two Discord rules
    kick in:
      1. The 3-second interaction rule — a Notion round-trip can exceed it, so we
         ctx.defer() FIRST to acknowledge, then send the real reply afterward.
      2. notion-client is synchronous and would block the gateway, so we run it
         off the event loop with asyncio.to_thread.
    ephemeral=True keeps the (team-internal) titles visible only to the invoker.
    """
    await ctx.defer(ephemeral=True)
    try:
        items = await asyncio.to_thread(notion_api.list_shared_content)
    except Exception as e:
        await ctx.respond(f"Notion error: `{e}`", ephemeral=True)
        return

    if not items:
        await ctx.respond(
            "Connected, but the integration can see **nothing**. In Notion, open a "
            "page or database → ••• → Connections → add this integration.",
            ephemeral=True,
        )
        return

    lines = [f"- {title}  ·  _{otype}_" for title, otype, _id in items]
    body = "\n".join(lines)
    # Discord hard-limits a message to 2000 characters; truncate defensively.
    if len(body) > 1900:
        body = body[:1900] + "\n… (truncated)"
    await ctx.respond(
        f"Connection can see **{len(items)}** item(s):\n{body}", ephemeral=True
    )


# Maps each dropdown choice to the Notion Status value(s) it filters by.
# "Active" expands to In progress + Not started (everything not Done/Pivoted).
TASK_STATUS_CHOICES = {
    "Done": ["Done"],
    "In progress": ["In progress"],
    "Not started": ["Not started"],
    "Pivoted": ["Pivoted"],
    "Active": notion_api.ACTIVE_STATUSES,
}


@bot.slash_command(
    name="tasks",
    description="List tasks from Notion filtered by status.",
    guild_ids=GUILD_IDS,
)
async def tasks(
    ctx: discord.ApplicationContext,
    status: discord.Option(
        str,
        description="Which tasks to show",
        choices=list(TASK_STATUS_CHOICES.keys()),
    ),
):
    """List tasks whose Status matches the chosen filter.

    Public reply (the whole team sees it). defer() first because the Notion
    round-trip can exceed the 3-second interaction limit; the sync SDK runs off
    the event loop via asyncio.to_thread.
    """
    await ctx.defer()
    statuses = TASK_STATUS_CHOICES[status]
    try:
        rows = await asyncio.to_thread(notion_api.query_tasks_by_status, statuses)
    except Exception as e:
        await ctx.respond(f"Notion error: `{e}`")
        return

    if not rows:
        await ctx.respond(f"No tasks with status **{status}**.")
        return

    lines = []
    for t in rows:
        parts = [f"**{t['name']}**"]
        if t["assignee"]:
            parts.append(f"👤 {t['assignee']}")
        if t["due"]:
            parts.append(f"📅 {t['due']}")
        lines.append("- " + " · ".join(parts))

    msg = f"Tasks — **{status}** ({len(rows)}):\n" + "\n".join(lines)
    if len(msg) > 1990:  # Discord caps a message at 2000 chars
        msg = msg[:1990] + "\n… (truncated)"
    await ctx.respond(msg)


# bot.run() opens the gateway connection and BLOCKS forever — the bot is a
# long-lived process, not a script that finishes. Closing this process (or the
# laptop) takes the bot offline.
bot.run(TOKEN)
