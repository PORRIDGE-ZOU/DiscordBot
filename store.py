"""Local bot-state store (SQLite).

Holds state the bot OWNS and that does NOT live in Notion:
  - associations:  Discord user <-> Notion person (drives /tasks, /taskdetail, /remind)
  - config:        misc key/value — currently the active sprint label
  - timeoff_cache: the parsed form of each #time-off message, so we never pay to
                   parse the same message twice (drives /time-off-recently)

Why local, not Notion: the Notion integration is read-only by design (it only ever
READS the team's workspace). Bot state is small, bot-owned, and changes through
Discord commands, so it lives in a SQLite file next to jobs.sqlite. Like
jobs.sqlite, botstate.db is live server state — gitignored, never deployed over.

Plain stdlib sqlite3 (no new dependency). sqlite3 is blocking, so async callers
run these via asyncio.to_thread, matching the notion_api pattern.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "botstate.db")


@contextmanager
def _conn():
    """Short-lived connection: commit on clean exit, always close."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    """Create tables if missing. Call once at startup (from on_ready)."""
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS associations (
                discord_id     INTEGER PRIMARY KEY,
                notion_user_id TEXT NOT NULL,
                notion_name    TEXT,
                email          TEXT NOT NULL,
                bound_at       TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)"
        )
        # One row per #time-off message we've already sent to the language model.
        # content_hash lets us notice an EDITED message and re-parse just that one.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timeoff_cache (
                message_id   TEXT PRIMARY KEY,
                author_id    INTEGER,
                author_name  TEXT,
                posted_at    TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                parsed_json  TEXT NOT NULL,
                parsed_at    TEXT NOT NULL
            )
            """
        )


# --- Associations -----------------------------------------------------------

def get_association(discord_id):
    """Row for a Discord user as a dict, or None if unbound."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM associations WHERE discord_id = ?", (discord_id,)
        ).fetchone()
    return dict(row) if row else None


def get_association_by_email(email):
    """Row whose email matches (case-insensitive), or None."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM associations WHERE email = ? COLLATE NOCASE", (email,)
        ).fetchone()
    return dict(row) if row else None


def set_association(discord_id, notion_user_id, notion_name, email):
    """Upsert a 1:1 binding (one Discord user <-> one Notion email).

    Enforces uniqueness on BOTH sides: any existing row holding this email under a
    different Discord user is removed first, so an email never maps to two people.
    Returns what was displaced so the command can report the rebind:
        {"prev_by_discord": <old row or None>, "prev_by_email": <old row or None>}
    """
    prev_by_discord = get_association(discord_id)
    prev_by_email = get_association_by_email(email)
    with _conn() as conn:
        # Free this email from any other Discord user (keeps email 1:1).
        conn.execute(
            "DELETE FROM associations WHERE email = ? COLLATE NOCASE", (email,)
        )
        # Upsert the Discord user's row.
        conn.execute(
            """
            INSERT INTO associations
                (discord_id, notion_user_id, notion_name, email, bound_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                notion_user_id = excluded.notion_user_id,
                notion_name    = excluded.notion_name,
                email          = excluded.email,
                bound_at       = excluded.bound_at
            """,
            (
                discord_id,
                notion_user_id,
                notion_name,
                email,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return {"prev_by_discord": prev_by_discord, "prev_by_email": prev_by_email}


# --- Config -----------------------------------------------------------------

def get_config(key):
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else None


def set_config(key, value):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def get_current_sprint():
    """Current sprint LABEL as a string, or None if unset.

    Stored as free text (not a number) because sprint names differ per workspace —
    "Sprint 1", "Summer", "S3". notion_api matches it loosely against the real
    options, so an older numeric value ("2") still resolves.
    """
    val = get_config("current_sprint")
    return val or None


def set_current_sprint(label):
    set_config("current_sprint", str(label))


# --- Time-off parse cache ----------------------------------------------------
# Parsing a message costs an API call, so we do it exactly once. The cache is
# keyed by Discord message id and guarded by a hash of the message text: an edited
# message changes its hash and gets re-parsed; everything else is a free lookup.

def get_timeoff_cached(message_id, content_hash):
    """Parsed JSON for this message IF we've parsed this exact text before."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT parsed_json FROM timeoff_cache WHERE message_id = ? AND content_hash = ?",
            (str(message_id), content_hash),
        ).fetchone()
    return row["parsed_json"] if row else None


def set_timeoff_cached(message_id, author_id, author_name, posted_at, content_hash, parsed_json):
    """Store (or replace) the parse for one message."""
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO timeoff_cache
                (message_id, author_id, author_name, posted_at, content_hash,
                 parsed_json, parsed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                author_name  = excluded.author_name,
                posted_at    = excluded.posted_at,
                content_hash = excluded.content_hash,
                parsed_json  = excluded.parsed_json,
                parsed_at    = excluded.parsed_at
            """,
            (
                str(message_id),
                author_id,
                author_name,
                posted_at,
                content_hash,
                parsed_json,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
