"""Quarter Life Pounder Discord bot.

Milestone 1: come online and answer a /ping slash command. This is the smallest
real bot — it proves the whole chain works (token -> gateway -> intents ->
slash command -> response) before any feature is added.
"""

import asyncio
import os
from datetime import datetime, timedelta

import discord
from dotenv import load_dotenv

import notion_api
import scheduler
import store

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
    # Create the local bot-state tables (associations + sprint config) if missing.
    store.init()
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
    description="List what Notion the bot can see, and how it reads the task database.",
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
    body = f"Connection can see **{len(items)}** item(s):\n" + "\n".join(lines)

    # Second half: how the bot READS the task database. Every task command resolves
    # what it needs (title, assignee, due date, sprint…) against the live schema, so
    # this map is the fastest way to see why a command is filtering wrong — a role
    # showing "—" means the bot found no column for it.
    try:
        info = await asyncio.to_thread(notion_api.describe_schema)
    except Exception as e:
        body += f"\n\n**Task database:** couldn't read the schema — `{e}`"
    else:
        roles = "\n".join(
            f"- `{role}` → {col if col else '— *(none found)*'}"
            for role, col in info["roles"].items()
        )
        cols = ", ".join(f"{name} (`{ptype}`)" for name, ptype in info["columns"])
        body += f"\n\n**Task database — what fills each role:**\n{roles}"
        if info["missing_required"]:
            body += (
                "\n⚠️ **Missing required:** "
                + ", ".join(info["missing_required"])
                + " — the task commands can't run until these exist."
            )
        if info["missing_optional"]:
            body += (
                "\nℹ️ Not found (those filters/fields are skipped): "
                + ", ".join(info["missing_optional"])
            )
        body += f"\n\n**Columns ({len(info['columns'])}):** {cols}"

    await ctx.respond(_truncate(body, 1990), ephemeral=True)


# --- Sprint + personal task commands (Milestone 4) ---------------------------
# These bind a Discord user to a Notion person (/associate), then filter the Task
# Tracker by that person + the active sprint. Bot state (the binding, the sprint)
# lives in the local store.py SQLite, NOT in Notion — Notion stays read-only.


def _truncate(text, limit):
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _personal_sorted(tasks):
    """Deterministic order shared by /tasks, /taskdetail, /remind so a given task
    has the SAME number across all three: by Due date ascending (no-due-date last),
    tiebreak by Task name. ISO date strings sort correctly lexicographically."""
    return sorted(
        tasks,
        key=lambda t: (0 if t.get("due") else 1, t.get("due") or "", t.get("name", "").lower()),
    )


async def _load_personal_tasks(ctx):
    """Shared loader for the personal-task commands. Resolves the caller's Notion
    person, queries their tasks (scoped to the current sprint if one is set), and
    returns them sorted. If the caller isn't linked, or the Notion query fails, it
    sends the right error (ephemeral) and returns None — the caller checks for None
    and stops. The sprint is OPTIONAL: when unset, all sprints are returned.

    Assumes ctx.defer(ephemeral=True) was already called.
    """
    assoc = await asyncio.to_thread(store.get_association, ctx.author.id)
    if not assoc:
        await ctx.respond("You're not linked yet — run `/associate` first.", ephemeral=True)
        return None
    sprint = await asyncio.to_thread(store.get_current_sprint)  # may be None (optional)
    try:
        tasks = await asyncio.to_thread(
            notion_api.query_tasks, assoc["notion_user_id"], sprint, None
        )
    except notion_api.MissingPropertyError as e:
        # The database is missing a column the bot can't work without — say which,
        # rather than returning an empty list that reads as "you have no tasks".
        await ctx.respond(f"⚠️ {e}", ephemeral=True)
        return None
    except Exception as e:
        await ctx.respond(f"Notion error: `{e}`", ephemeral=True)
        return None
    return assoc, sprint, _personal_sorted(tasks)


@bot.slash_command(
    name="associate",
    description="Link a Notion account (by email) to a Discord member for task queries.",
    guild_ids=GUILD_IDS,
)
async def associate(
    ctx: discord.ApplicationContext,
    person: discord.Option(
        str,
        name="person",
        description="Notion email OR display name (as shown in the Assignee column)",
    ),
    member: discord.Option(discord.Member, description="The Discord member to link"),
):
    """Bind a Notion person <-> a Discord member. `member` is a user-PICKER (real
    server member + stable ID). `person` is matched by email or display name against
    workspace members AND task assignees — so GUESTS (who never appear in Notion's
    members list, but are still assigned tasks) can be linked too."""
    await ctx.defer(ephemeral=True)
    try:
        found = await asyncio.to_thread(notion_api.find_notion_person, person)
    except Exception as e:
        await ctx.respond(f"Notion error: `{e}`", ephemeral=True)
        return
    if not found:
        await ctx.respond(
            f"Couldn't find **{person}** in Notion — not a workspace member, and not "
            "assigned to any task. Check the email, or try the display name exactly as "
            "it appears in the Assignee column. Nothing changed.",
            ephemeral=True,
        )
        return

    # Key the 1:1 binding on the email when Notion exposes it, else the display name
    # (guests often have no email available through the API).
    key = found["email"] or found["name"]
    result = await asyncio.to_thread(
        store.set_association, member.id, found["id"], found["name"], key
    )
    prev_d = result["prev_by_discord"]
    prev_e = result["prev_by_email"]
    notes = []
    if prev_d and prev_d["email"].lower() != key.lower():
        notes.append(f"{member.mention} was linked to `{prev_d['email']}`")
    if prev_e and prev_e["discord_id"] != member.id:
        notes.append(f"`{key}` was linked to <@{prev_e['discord_id']}>")

    shown = f"`{found['email']}`" if found["email"] else "no email on file"
    bind = f"{member.mention} ↔ **{found['name']}** ({shown})"
    if notes:
        await ctx.respond(
            "⚠️ This was already bound! " + "; ".join(notes) + f". Now re-bound: {bind}.",
            ephemeral=True,
        )
    else:
        await ctx.respond(f"✅ Linked {bind}.", ephemeral=True)


@bot.slash_command(
    name="tasks",
    description="List your tasks in the current sprint.",
    guild_ids=GUILD_IDS,
)
async def tasks(ctx: discord.ApplicationContext):
    """The caller's own tasks for the active sprint. Ephemeral (personal)."""
    await ctx.defer(ephemeral=True)
    loaded = await _load_personal_tasks(ctx)
    if loaded is None:
        return
    _assoc, sprint, items = loaded
    # `sprint` is the Notion label itself ("Sprint 1", "Summer"), so print it as-is.
    scope = sprint if sprint else "all sprints"
    if not items:
        await ctx.respond(f"No tasks assigned to you ({scope}).", ephemeral=True)
        return
    lines = []
    for i, t in enumerate(items, 1):
        parts = [f"**{t['name']}**", t["status"] or "—"]
        if t["due"]:
            parts.append(f"📅 {t['due']}")
        if t["description"]:
            parts.append(_truncate(t["description"], 80))
        lines.append(f"{i}. " + " — ".join(parts))
    body = f"**Your tasks — {scope}** ({len(items)}):\n" + "\n".join(lines)
    await ctx.respond(_truncate(body, 1990), ephemeral=True)


@bot.slash_command(
    name="taskdetail",
    description="Show full details for one of your tasks, by its number from /tasks.",
    guild_ids=GUILD_IDS,
)
async def taskdetail(
    ctx: discord.ApplicationContext,
    number: discord.Option(int, description="Task number shown in /tasks"),
):
    """All properties of one task. Uses the same ordered list as /tasks, so the
    number lines up with what /tasks showed. Ephemeral."""
    await ctx.defer(ephemeral=True)
    loaded = await _load_personal_tasks(ctx)
    if loaded is None:
        return
    _assoc, _sprint, items = loaded
    if number < 1 or number > len(items):
        await ctx.respond(
            f"No task #{number}. You have {len(items)} task(s) — run `/tasks`.",
            ephemeral=True,
        )
        return
    t = items[number - 1]
    # EVERY column this database has, under its own Notion name — the recognised
    # ones first, then whatever else the team added. Nothing here is hardcoded, so
    # a new Notion column shows up the next time the bot restarts.
    lines = [f"**{t['name']}**"]
    lines += [f"• {column}: {value or '—'}" for column, value in t["all"]]
    await ctx.respond(_truncate("\n".join(lines), 1990), ephemeral=True)


@bot.slash_command(
    name="setsprint",
    description="Set the team's current sprint, by its name in Notion.",
    guild_ids=GUILD_IDS,
)
async def setsprint(
    ctx: discord.ApplicationContext,
    label: discord.Option(
        str, description="Sprint name as it appears in Notion, e.g. Sprint 1"
    ),
):
    """Set the active sprint (shared team state). Anyone can run it.

    A LABEL, not a number, because sprint naming is per-workspace. It's validated
    against the sprint values that actually exist in Notion — whether that column
    is a select or a relation to a Sprints database — and matched loosely, so
    "Sprint 1", "sprint1" and "1" all land on the same sprint. An unknown label is
    rejected with the real list rather than silently matching zero tasks later."""
    await ctx.defer(ephemeral=True)
    try:
        matched = await asyncio.to_thread(notion_api.match_sprint, label)
        options = await asyncio.to_thread(notion_api.get_sprint_options)
    except notion_api.MissingPropertyError as e:
        await ctx.respond(f"⚠️ {e}", ephemeral=True)
        return
    except Exception as e:
        await ctx.respond(f"Notion error: `{e}`", ephemeral=True)
        return

    if matched is None:
        if options:
            await ctx.respond(
                f"Unknown sprint **{label}**. Valid: {', '.join(options)}.",
                ephemeral=True,
            )
        else:
            await ctx.respond(
                "This Notion database has no sprint column, so there's no sprint to "
                "set — task commands already show every task.",
                ephemeral=True,
            )
        return

    await asyncio.to_thread(store.set_current_sprint, matched)
    await ctx.respond(f"✅ Current sprint set to **{matched}**.", ephemeral=True)


@bot.slash_command(
    name="sprint",
    description="Show the current sprint.",
    guild_ids=GUILD_IDS,
)
async def sprint(ctx: discord.ApplicationContext):
    """Public — report the active sprint label."""
    await ctx.defer()
    s = await asyncio.to_thread(store.get_current_sprint)
    if s is None:
        await ctx.respond("No sprint set yet — run `/setsprint`.")
    else:
        await ctx.respond(f"We're in **{s}**!")


@bot.slash_command(
    name="sprinttasks",
    description="List all tasks in the current sprint, optionally filtered by department.",
    guild_ids=GUILD_IDS,
)
async def sprinttasks(
    ctx: discord.ApplicationContext,
    department: discord.Option(
        str, description="Filter by department (optional)", required=False, default=None
    ),
):
    """Public team view of the whole sprint. No department -> grouped by the fixed
    department order; with a department -> just that one (validated against the
    Notion Department options)."""
    await ctx.defer()
    sprint_label = await asyncio.to_thread(store.get_current_sprint)  # may be None
    scope = sprint_label if sprint_label else "All tasks"

    if department:
        try:
            valid = await asyncio.to_thread(notion_api.get_department_options)
        except Exception as e:
            await ctx.respond(f"Notion error: `{e}`")
            return
        match = next((d for d in valid if d.lower() == department.lower()), None)
        if not match:
            await ctx.respond(
                f"Unknown department **{department}**. Valid: "
                f"{', '.join(valid) if valid else '(none defined)'}."
            )
            return
        department = match  # normalize to the canonical Notion name

    try:
        items = await asyncio.to_thread(
            notion_api.query_tasks, None, sprint_label, department
        )
    except notion_api.MissingPropertyError as e:
        await ctx.respond(f"⚠️ {e}")
        return
    except Exception as e:
        await ctx.respond(f"Notion error: `{e}`")
        return
    if not items:
        where = f" in **{department}**" if department else ""
        await ctx.respond(f"No tasks{where} ({scope}).")
        return

    if department:
        items.sort(key=lambda t: t["name"].lower())
        lines = [
            f"{i}. **{t['name']}** — {t['status'] or '—'} — 👤 {t['assignee'] or '—'}"
            for i, t in enumerate(items, 1)
        ]
        header = f"**{scope} — {department}** ({len(items)}):"
    else:
        # Group in the order the departments are defined in Notion (that's the order
        # they're shown in there too); anything unrecognised sorts last.
        try:
            order = await asyncio.to_thread(notion_api.get_department_options)
        except Exception:
            order = []
        rank = {d: i for i, d in enumerate(order)}
        items.sort(key=lambda t: (rank.get(t["department"], len(rank)), t["name"].lower()))
        lines = [
            f"{i}. **{t['name']}** — {t['status'] or '—'} — 👤 {t['assignee'] or '—'} — 🏷️ {t['department'] or '—'}"
            for i, t in enumerate(items, 1)
        ]
        header = f"**{scope}** ({len(items)}):"

    await ctx.respond(_truncate(header + "\n" + "\n".join(lines), 1990))


@bot.slash_command(
    name="remind",
    description="DM yourself a set number of days before each of your tasks is due.",
    guild_ids=GUILD_IDS,
)
async def remind(
    ctx: discord.ApplicationContext,
    x: discord.Option(int, description="Days before each due date to remind you"),
):
    """For each of the caller's current-sprint tasks WITH a due date, schedule one
    DM x days before that task's due date. Re-running replaces the caller's previous
    batch (no duplicate stacking). Task text is snapshotted now."""
    await ctx.defer(ephemeral=True)
    if x < 0:
        await ctx.respond("Days must be 0 or more.", ephemeral=True)
        return
    loaded = await _load_personal_tasks(ctx)
    if loaded is None:
        return
    _assoc, _sprint, items = loaded

    # Clear this user's old task reminders first, then reschedule fresh.
    await asyncio.to_thread(scheduler.clear_task_reminders, ctx.author.id)

    now = datetime.now(scheduler.CALIFORNIA)
    scheduled = 0
    skipped = 0
    for t in items:
        run_date = _reminder_datetime(t["due"], x)
        if run_date is None or run_date <= now:
            skipped += 1  # no due date, or the reminder moment is already past
            continue
        days_phrase = "today" if x == 0 else f"in {x} day{'s' if x != 1 else ''}"
        content = (
            f"⏰ **Reminder:** your task **{t['name']}** is due on **{t['due']}** "
            f"({days_phrase}).\nStatus: {t['status'] or '—'}"
        )
        if t["description"]:
            content += f"\n{_truncate(t['description'], 200)}"
        scheduler.schedule_task_reminder(ctx.author.id, run_date, content, scheduled)
        scheduled += 1

    await ctx.respond(
        f"Scheduled **{scheduled}** reminder(s), {x} day(s) before each due date. "
        f"Skipped **{skipped}** (no due date / already past).",
        ephemeral=True,
    )


def _reminder_datetime(due, x):
    """Notion due value (ISO date or datetime) minus x days -> a tz-aware datetime
    at 09:00 California on the reminder day, or None if `due` is empty/unparseable."""
    if not due:
        return None
    try:
        d = datetime.strptime(due[:10], "%Y-%m-%d").date()  # tolerate date or datetime
    except ValueError:
        return None
    day = d - timedelta(days=x)
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=scheduler.CALIFORNIA)


# --- Intro + help -----------------------------------------------------------
INTRO_TEXT = (
    "👋 I'm **Sous Chef**, the bot for QLP. I can:\n"
    "• 🔗 Link your Notion account — `/associate`\n"
    "• 📋 Show your sprint tasks — `/tasks`, `/taskdetail`\n"
    "• 🗂️ Show the whole sprint — `/sprinttasks` (optionally by department)\n"
    "• 🏃 Track the sprint — `/sprint`, `/setsprint`\n"
    "• ⏰ Remind you before tasks are due — `/remind`\n"
    "• ⏲️ Channel reminders, one-time or weekly — `/remind_in`, `/remind_weekly`\n"
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


@bot.slash_command(
    name="dm",
    description="Send a direct message (to yourself by default), then confirm it was sent.",
    guild_ids=GUILD_IDS,
)
async def dm(
    ctx: discord.ApplicationContext,
    message: discord.Option(str, description="The message to send"),
    member: discord.Option(
        discord.Member,
        description="Who to DM (leave blank to DM yourself)",
        required=False,
        default=None,
    ),
):
    """DM `message` to `member` (or to the invoker if none given), then reply with a
    private confirmation. The confirmation is the point: the sender always learns
    whether the DM went through.

    A bot can only DM a user who shares the server AND allows DMs from server members
    — if they don't, Discord raises discord.Forbidden, which we surface instead of
    failing silently."""
    await ctx.defer(ephemeral=True)
    target = member or ctx.author
    try:
        await target.send(message)
    except discord.Forbidden:
        await ctx.respond(
            f"❌ Couldn't DM {target.mention} — their DMs are closed "
            "(they'd need to allow direct messages from server members).",
            ephemeral=True,
        )
        return
    except discord.HTTPException as e:
        await ctx.respond(f"❌ Failed to send the DM: `{e}`", ephemeral=True)
        return
    await ctx.respond(f"✅ DM sent to {target.mention}.", ephemeral=True)


# bot.run() opens the gateway connection and BLOCKS forever — the bot is a
# long-lived process, not a script that finishes. Closing this process (or the
# laptop) takes the bot offline.
bot.run(TOKEN)
