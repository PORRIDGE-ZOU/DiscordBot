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
import scheduler

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
    # Start the reminder scheduler now that the event loop is running and the bot
    # is ready. This also reloads any reminders saved before the last restart.
    scheduler.setup(bot)
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


# --- Intro + help -----------------------------------------------------------
INTRO_TEXT = (
    "👋 I'm **Aboyeur**, the QLP team's helper bot. I can:\n"
    "• 📋 Pull tasks from Notion — `/tasks` (filter by status)\n"
    "• ⏰ Send reminders, one-time or weekly — `/remind_in`, `/remind_weekly`\n"
    "• 🔎 Show which Notion pages I can read — `/notion_check`\n"
    "• 🏓 Confirm I'm alive — `/ping`\n"
    "Type `/help` for the full list."
)


@bot.slash_command(
    name="intro",
    description="Post a short intro of what the bot can do.",
    guild_ids=GUILD_IDS,
)
async def intro(ctx: discord.ApplicationContext):
    """Public — posts the capability blurb to the current channel."""
    await ctx.respond(INTRO_TEXT)


@bot.slash_command(
    name="help",
    description="List all commands and what they do.",
    guild_ids=GUILD_IDS,
)
async def help_command(ctx: discord.ApplicationContext):
    """Private — auto-generated from the registered slash commands so it never
    drifts out of sync with what the bot actually offers."""
    lines = ["**Commands:**"]
    for cmd in sorted(bot.application_commands, key=lambda c: c.name):
        lines.append(f"- `/{cmd.name}` — {cmd.description}")
    await ctx.respond("\n".join(lines), ephemeral=True)


# --- Reminders --------------------------------------------------------------
def _bot_can_post(channel, guild):
    """Whether the bot has permission to send messages in `channel`."""
    return channel.permissions_for(guild.me).send_messages


def _parse_hhmm(text):
    """Parse 'HH:MM' 24-hour into (hour, minute). Raises ValueError if invalid."""
    hour_str, minute_str = text.strip().split(":")
    hour, minute = int(hour_str), int(minute_str)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("out of range")
    return hour, minute


@bot.slash_command(
    name="remind_in",
    description="Send a message once, a number of hours from now.",
    guild_ids=GUILD_IDS,
)
async def remind_in(
    ctx: discord.ApplicationContext,
    message: discord.Option(str, description="What to send"),
    hours: discord.Option(float, description="Hours from now (e.g. 1.5)"),
    channel: discord.Option(discord.TextChannel, description="Channel to post in"),
):
    if hours <= 0:
        await ctx.respond("Hours must be greater than 0.", ephemeral=True)
        return
    if not _bot_can_post(channel, ctx.guild):
        await ctx.respond(
            f"I don't have permission to post in {channel.mention}.", ephemeral=True
        )
        return
    job_id, run_date = scheduler.schedule_once(channel.id, message, hours)
    await ctx.respond(
        f"⏰ Scheduled. I'll post in {channel.mention} at "
        f"**{run_date:%Y-%m-%d %H:%M %Z}**.\nID: `{job_id}` — cancel with `/reminder_cancel`.",
        ephemeral=True,
    )


@bot.slash_command(
    name="remind_weekly",
    description="Send a message every week on a chosen day + time (California).",
    guild_ids=GUILD_IDS,
)
async def remind_weekly(
    ctx: discord.ApplicationContext,
    message: discord.Option(str, description="What to send"),
    day: discord.Option(
        str, description="Day of week", choices=list(scheduler.WEEKDAYS.keys())
    ),
    time: discord.Option(str, description="Time HH:MM, 24h, California (e.g. 09:30)"),
    channel: discord.Option(discord.TextChannel, description="Channel to post in"),
):
    try:
        hour, minute = _parse_hhmm(time)
    except ValueError:
        await ctx.respond(
            "Time must be HH:MM 24-hour — e.g. `09:30` or `17:00`.", ephemeral=True
        )
        return
    if not _bot_can_post(channel, ctx.guild):
        await ctx.respond(
            f"I don't have permission to post in {channel.mention}.", ephemeral=True
        )
        return
    job_id = scheduler.schedule_weekly(
        channel.id, message, scheduler.WEEKDAYS[day], hour, minute
    )
    await ctx.respond(
        f"📅 Scheduled weekly: every **{day} at {time} PT** in {channel.mention}.\n"
        f"ID: `{job_id}` — cancel with `/reminder_cancel`.",
        ephemeral=True,
    )


@bot.slash_command(
    name="reminders",
    description="List active scheduled reminders.",
    guild_ids=GUILD_IDS,
)
async def reminders(ctx: discord.ApplicationContext):
    jobs = scheduler.list_jobs()
    if not jobs:
        await ctx.respond("No active reminders.", ephemeral=True)
        return
    lines = ["**Active reminders:**"]
    for job in jobs:
        when = (
            job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")
            if job.next_run_time
            else "—"
        )
        lines.append(f"- `{job.id}` — {job.name} (next: {when})")
    body = "\n".join(lines)
    if len(body) > 1990:
        body = body[:1990] + "\n… (truncated)"
    await ctx.respond(body, ephemeral=True)


@bot.slash_command(
    name="reminder_cancel",
    description="Cancel a scheduled reminder by its ID.",
    guild_ids=GUILD_IDS,
)
async def reminder_cancel(
    ctx: discord.ApplicationContext,
    id: discord.Option(str, description="Reminder ID (from /reminders)"),
):
    try:
        scheduler.cancel(id)
    except Exception:
        await ctx.respond(f"No reminder with ID `{id}`.", ephemeral=True)
        return
    await ctx.respond(f"Cancelled reminder `{id}`.", ephemeral=True)


# bot.run() opens the gateway connection and BLOCKS forever — the bot is a
# long-lived process, not a script that finishes. Closing this process (or the
# laptop) takes the bot offline.
bot.run(TOKEN)
