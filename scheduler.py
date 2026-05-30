"""Reminder scheduling.

Keeps all scheduling out of bot.py (same split as notion_api.py). Backed by
APScheduler with a persistent SQLite jobstore, so reminders survive bot restarts
(deploys, crashes, reboots) — an in-memory scheduler would silently drop every
pending reminder on restart.

Two important constraints this design satisfies:
- Persistent jobs are stored by a *reference* to the function that runs them, so
  that function (`_send_message`) must be a module-level function here, not a
  closure inside a command handler.
- The jobstore file `jobs.sqlite` is live server state. Do NOT let a deploy rsync
  overwrite it, or you wipe every scheduled reminder.
"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

# All reminder times are interpreted in California wall-clock time; zoneinfo
# handles PST/PDT (daylight saving) automatically.
CALIFORNIA = ZoneInfo("America/Los_Angeles")

# Map the /remind_weekly dropdown labels to APScheduler's day-of-week tokens.
WEEKDAYS = {
    "Monday": "mon",
    "Tuesday": "tue",
    "Wednesday": "wed",
    "Thursday": "thu",
    "Friday": "fri",
    "Saturday": "sat",
    "Sunday": "sun",
}

# If the bot was down when a reminder was due, fire it if we're back within this
# many seconds of the scheduled time; otherwise skip that occurrence.
_MISFIRE_GRACE = 3600

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs.sqlite")

_bot = None
_scheduler = None


def setup(bot):
    """Wire up the bot reference and start the scheduler. Call once, after the
    bot is ready (from on_ready) so APScheduler binds to the running event loop.
    Reloads any reminders saved from a previous run."""
    global _bot, _scheduler
    _bot = bot
    if _scheduler is None:
        jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{_DB_PATH}")}
        _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=CALIFORNIA)
        _scheduler.start()


async def _send_message(channel_id, content):
    """The actual action a reminder performs. Referenced by every stored job."""
    channel = _bot.get_channel(channel_id)
    if channel is None:
        # Not in cache (e.g. just after a restart) — fetch it from the API.
        channel = await _bot.fetch_channel(channel_id)
    await channel.send(content)


def schedule_once(channel_id, content, hours):
    """Fire once, `hours` from now. Returns (job_id, run_datetime)."""
    run_date = datetime.now(CALIFORNIA) + timedelta(hours=hours)
    name = f"once @ {run_date:%Y-%m-%d %H:%M %Z} -> #{channel_id}: {content[:40]}"
    job = _scheduler.add_job(
        _send_message,
        trigger=DateTrigger(run_date=run_date),
        args=[channel_id, content],
        name=name,
        misfire_grace_time=_MISFIRE_GRACE,
    )
    return job.id, run_date


def schedule_weekly(channel_id, content, day_token, hour, minute):
    """Fire every week on `day_token` (mon..sun) at hour:minute California time.
    Returns job_id."""
    name = f"weekly {day_token} {hour:02d}:{minute:02d} PT -> #{channel_id}: {content[:40]}"
    job = _scheduler.add_job(
        _send_message,
        trigger=CronTrigger(
            day_of_week=day_token, hour=hour, minute=minute, timezone=CALIFORNIA
        ),
        args=[channel_id, content],
        name=name,
        misfire_grace_time=_MISFIRE_GRACE,
    )
    return job.id


def list_jobs():
    """Active reminders, each with .id, .name, .next_run_time."""
    return _scheduler.get_jobs()


def cancel(job_id):
    """Remove a reminder. Raises apscheduler.jobstores.base.JobLookupError if the
    id doesn't exist."""
    _scheduler.remove_job(job_id)
