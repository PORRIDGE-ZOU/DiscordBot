"""Time-off calendar built from the #time-off channel's natural-language posts.

People write when they're unavailable in plain English ("driving to LA August 9th
to 19th", "can't make the engineering meeting tmr"). This module turns that into
structured entries a command can filter by date.

Two things make it work:

1. **Every date is America/Los_Angeles.** "tomorrow" means tomorrow in LA, not
   wherever the server happens to be. All windowing here is done in LA dates.
2. **The posting timestamp is part of the input.** "next thurs" is meaningless
   without knowing when it was written, so the model is told when each message was
   posted, in LA time.

Some posts can't resolve to a date at all — "I'll miss the next engineering
meeting" names an event, not a day. Those are kept as UNRESOLVED entries and shown
for two weeks from their posting date (see UNRESOLVED_VALID_DAYS).

Like notion_api.py, this module owns all calls to its external service and knows
nothing about Discord — bot.py hands it plain dicts and renders what comes back.
The OpenAI client is synchronous, so async callers use `asyncio.to_thread`.
"""

import hashlib
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from openai import OpenAI

import store

# The team is in Los Angeles; every date in every message is read as an LA date.
LA = ZoneInfo("America/Los_Angeles")

# How far back to read the channel. Wider than any report window on purpose: a
# message posted July 30 can describe August 9-19, so "this month" needs history
# from before this month.
HISTORY_DAYS = 60

# A post that names an event but no date ("the next work session") is treated as
# live for this many days after it was written.
UNRESOLVED_VALID_DAYS = 14

# Messages per API call. Keeps the request small enough to stay reliable while
# still amortising the system prompt across a batch.
BATCH_SIZE = 20

# Anything outside this set is treated as "unspecified" rather than shown verbatim.
PARTS_OF_DAY = ("all day", "morning", "afternoon", "evening")

_client = None


def _get_client():
    """One lazily-built client, so importing this module never needs the key."""
    global _client
    if _client is None:
        # KeyError here = OPENAI_API_KEY missing from .env
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _model():
    """Overridable in .env so the model can change without a code edit."""
    return os.environ.get("OPENAI_MODEL", "gpt-4o")


def channel_id():
    """The #time-off channel's id, or None if it isn't configured."""
    raw = os.environ.get("TIMEOFF_CHANNEL_ID", "").strip()
    return int(raw) if raw else None


# --- The parse contract ------------------------------------------------------
# A strict JSON schema: the model must return exactly these fields, so the parse
# can't drift into a shape the rest of the module doesn't understand.

_ENTRY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "start_date": {
            "type": ["string", "null"],
            "description": "First day unavailable, YYYY-MM-DD, or null if no date can be derived.",
        },
        "end_date": {
            "type": ["string", "null"],
            "description": "Last day unavailable, YYYY-MM-DD (same as start_date for one day), or null.",
        },
        "event": {
            "type": ["string", "null"],
            "description": "The recurring event they'll miss, e.g. 'engineering meeting', or null.",
        },
        "resolved": {
            "type": "boolean",
            "description": "True if start_date and end_date are filled in. False for a bare 'next X'.",
        },
        "part_of_day": {
            "type": ["string", "null"],
            "description": "One of: all day, morning, afternoon, evening. Null if unclear.",
        },
        "summary": {
            "type": "string",
            "description": "Short reason or context, under 60 characters. Empty string if none given.",
        },
    },
    "required": ["start_date", "end_date", "event", "resolved", "part_of_day", "summary"],
}

_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "entries": {"type": "array", "items": _ENTRY_SCHEMA},
                },
                "required": ["index", "entries"],
            },
        }
    },
    "required": ["results"],
}

_SYSTEM_PROMPT = """\
You extract time-off information from messages in a game-dev team's Discord channel,
where people post in casual English when they will be unavailable.

For each numbered message, return its entries. A message may produce zero entries (if
it isn't about being unavailable), one entry, or several (if it describes more than
one absence).

TIMEZONE: every date is America/Los_Angeles. Each message comes with the local LA date
and weekday it was posted. Resolve all relative expressions against THAT timestamp:
- "today" / "tonight" -> the posting date
- "tomorrow" / "tmr" -> posting date + 1 day
- "next thurs" (any weekday) -> the next occurrence of that weekday strictly AFTER the
  posting date
- "next week" -> Monday through Sunday of the week after the posting date's week
- "August 9th to 19th" -> that range in the year the message was posted (roll to next
  year only if the date would otherwise be in the past by more than a month)

RESOLVED vs UNRESOLVED:
- If you can derive actual dates, fill start_date and end_date and set resolved=true.
  A single day means start_date == end_date.
- If the message only names a recurring event with no derivable date ("I'll miss the
  next engineering meeting", "can't make the next work session"), set resolved=false,
  leave start_date and end_date null, and put the event name in "event".
- If a message names an event AND a derivable date ("can't make the engineering
  meeting tmr"), fill BOTH the dates and "event", with resolved=true.

Never invent a date you cannot derive from the message plus its posting timestamp.
An unresolved entry is correct and useful; a guessed date is not.

OTHER FIELDS:
- "event": only when they name a specific recurring team event (engineering meeting,
  work session, playtest, standup, all-hands). Not for personal activities.
- "part_of_day": only when they scope it ("in the evening", "morning only"). Use
  "all day" when they're out for whole days, null when unclear.
- "summary": a short phrase, under 60 characters, giving their reason or context
  ("driving to LA with family", "picking up gf at LAX"). Empty string if none.

Only count messages where the AUTHOR is describing their OWN unavailability. Ignore
questions, replies about someone else, and general chatter.\
"""


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _format_for_model(index, msg):
    """One message as the model sees it. The posted line is load-bearing — without
    it, 'tmr' and 'next thurs' can't be resolved."""
    local = msg["posted_at"].astimezone(LA)
    return (
        f"[{index}]\n"
        f"author: {msg['author_name']}\n"
        f"posted: {local.strftime('%Y-%m-%d %H:%M')} ({local.strftime('%A')}) America/Los_Angeles\n"
        f"message: {msg['text']}\n"
    )


def _parse_batch(batch):
    """Send up to BATCH_SIZE messages in one call. Returns {index: [entry, ...]}."""
    payload = "\n".join(_format_for_model(i, m) for i, m in enumerate(batch))
    response = _get_client().chat.completions.create(
        model=_model(),
        temperature=0,  # deterministic: the same message should parse the same way
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "time_off",
                "strict": True,
                "schema": _RESPONSE_SCHEMA,
            },
        },
    )
    data = json.loads(response.choices[0].message.content)
    return {
        item["index"]: item.get("entries", [])
        for item in data.get("results", [])
        if isinstance(item.get("index"), int)
    }


def _clean_entry(raw):
    """Normalise one model entry, or None if it's unusable.

    Defensive on purpose: a malformed date is dropped rather than allowed to become
    a confidently-wrong calendar row.
    """
    start = _as_date(raw.get("start_date"))
    end = _as_date(raw.get("end_date"))
    event = (raw.get("event") or "").strip() or None

    if start and not end:
        end = start
    if end and not start:
        start = end
    if start and end and start > end:
        start, end = end, start

    resolved = bool(start and end)
    if not resolved and not event:
        return None  # no date and no event = nothing we can ever display

    part = (raw.get("part_of_day") or "").strip().lower()
    return {
        "start": start,
        "end": end,
        "event": event,
        "resolved": resolved,
        "part_of_day": part if part in PARTS_OF_DAY else None,
        "summary": (raw.get("summary") or "").strip(),
    }


def _as_date(value):
    """'2026-08-09' -> date, anything else -> None."""
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def load_entries(messages):
    """Parse every message (cached) and return a flat list of entries.

    `messages` is a list of plain dicts from bot.py:
        {"id", "author_id", "author_name", "posted_at" (aware datetime), "text",
         "jump_url"}

    Each returned entry carries its author and provenance so the display layer can
    attribute it and link back to the original post. Blocking (SQLite + HTTP) —
    call it via asyncio.to_thread.
    """
    entries = []
    pending = []  # messages with no usable cache entry, to be parsed in batches

    for msg in messages:
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        cached = store.get_timeoff_cached(msg["id"], _hash(text))
        if cached is not None:
            entries.extend(_attach(json.loads(cached), msg))
        else:
            pending.append(msg)

    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        parsed = _parse_batch(batch)
        for index, msg in enumerate(batch):
            raw_entries = parsed.get(index, [])
            store.set_timeoff_cached(
                msg["id"],
                msg.get("author_id"),
                msg["author_name"],
                msg["posted_at"].isoformat(),
                _hash(msg["text"].strip()),
                json.dumps(raw_entries),
            )
            entries.extend(_attach(raw_entries, msg))

    return entries


def _attach(raw_entries, msg):
    """Clean the model's entries and stamp them with who said it and when."""
    out = []
    for raw in raw_entries or []:
        entry = _clean_entry(raw)
        if not entry:
            continue
        entry["author"] = msg["author_name"]
        entry["posted_at"] = msg["posted_at"].astimezone(LA)
        entry["message_id"] = msg["id"]
        entry["jump_url"] = msg.get("jump_url")
        out.append(entry)
    return out


# --- Windows -----------------------------------------------------------------

def today_la():
    """Today's date in Los Angeles — the reference point for every window."""
    return datetime.now(LA).date()


def week_window(start=None, days=7):
    """The next `days` days INCLUSIVE of today: (start, end) as LA dates."""
    start = start or today_la()
    return start, start + timedelta(days=days - 1)


def month_window(today=None):
    """First and last day of the current LA calendar month."""
    today = today or today_la()
    first = today.replace(day=1)
    # Jump into the next month, then step back a day — avoids month-length maths.
    next_month = (first + timedelta(days=32)).replace(day=1)
    return first, next_month - timedelta(days=1)


def select(entries, start, end, include_unresolved=True):
    """Split entries into what falls in [start, end]: (dated, unscheduled).

    - **dated**: a resolved entry whose range OVERLAPS the window at all (a
      long absence still counts on every day it covers). Sorted by start date.
    - **unscheduled**: an entry with no derivable date, counted as live from its
      posting day through UNRESOLVED_VALID_DAYS later — shown when that validity
      span overlaps the window. Sorted by when it was posted, newest first.
    """
    dated, unscheduled = [], []
    for entry in entries:
        if entry["resolved"]:
            if entry["start"] <= end and entry["end"] >= start:
                dated.append(entry)
        elif include_unresolved:
            posted = entry["posted_at"].date()
            if posted <= end and posted + timedelta(days=UNRESOLVED_VALID_DAYS) >= start:
                unscheduled.append(entry)

    dated.sort(key=lambda e: (e["start"], e["end"], e["author"].lower()))
    unscheduled.sort(key=lambda e: e["posted_at"], reverse=True)
    return dated, unscheduled


# --- Display helpers ---------------------------------------------------------

def format_day(day, today=None):
    """'Aug 26', or 'Aug 26 (today)' / '(tomorrow)' when it's near."""
    today = today or today_la()
    label = day.strftime("%b %-d")
    if day == today:
        return f"{label} (today)"
    if day == today + timedelta(days=1):
        return f"{label} (tomorrow)"
    return label


def format_range(entry, today=None):
    """The date part of a dated entry: one day, or 'Aug 26 – Sep 1'."""
    today = today or today_la()
    if entry["start"] == entry["end"]:
        return format_day(entry["start"], today)
    return f"{format_day(entry['start'], today)} – {entry['end'].strftime('%b %-d')}"


def describe(entry):
    """The trailing detail of a line: part of day, event, and reason."""
    bits = []
    if entry.get("part_of_day") and entry["part_of_day"] != "all day":
        bits.append(entry["part_of_day"])
    if entry.get("event"):
        bits.append(entry["event"])
    if entry.get("summary"):
        bits.append(f"_{entry['summary']}_")
    return " — ".join(bits)
