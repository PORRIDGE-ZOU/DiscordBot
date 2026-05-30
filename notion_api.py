"""Notion API helpers.

All Notion calls live here so bot.py stays focused on Discord wiring. The bot
talks to Notion through a single internal-integration ("connection") token. The
connection only sees pages/databases that have been explicitly shared with it in
Notion (page -> ••• -> Connections) — a valid token with nothing shared returns
an empty result, which is the #1 Notion gotcha.

notion-client is a SYNCHRONOUS library (blocking HTTP). Callers in async code
should run these functions off the event loop, e.g. `await asyncio.to_thread(...)`,
so the Discord gateway keeps beating while we wait on Notion.
"""

import os

from notion_client import Client

# One shared client, built lazily from the token so importing this module never
# fails just because NOTION_TOKEN isn't set until a Notion command actually runs.
_client = None


def _get_client():
    global _client
    if _client is None:
        token = os.environ["NOTION_TOKEN"]  # KeyError = NOTION_TOKEN missing from .env
        _client = Client(auth=token)
    return _client


def list_shared_content():
    """Return [(title, object_type, id), ...] for everything the connection sees.

    Uses Notion's `search` with no query, which lists every page and database
    shared with the integration. Paginates so nothing is silently cut off.
    """
    client = _get_client()
    results = []
    cursor = None
    while True:
        kwargs = {"start_cursor": cursor} if cursor else {}
        resp = client.search(**kwargs)
        for obj in resp["results"]:
            results.append((_title_of(obj), obj["object"], obj["id"]))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return results


def _title_of(obj):
    """Pull a human-readable title out of a page or database object.

    Notion stores titles differently for databases vs pages, so we handle each.
    """
    if obj["object"] == "database":
        return _rich_text_to_plain(obj.get("title", [])) or "(untitled database)"
    # A page's title lives inside whichever property has type "title".
    for prop in obj.get("properties", {}).values():
        if prop.get("type") == "title":
            return _rich_text_to_plain(prop.get("title", [])) or "(untitled page)"
    return "(untitled)"


def _rich_text_to_plain(rich):
    """Notion text is a list of 'rich text' pieces; join their plain_text."""
    return "".join(piece.get("plain_text", "") for piece in rich)


# --- Task database queries ---------------------------------------------------
# Status values that count as "Active": everything not Done and not Pivoted.
ACTIVE_STATUSES = ["In progress", "Not started"]

# Notion's 2025 API splits a database into one or more "data sources"; the rows
# live in a data source and the query endpoint targets it, not the database. We
# resolve the database id (NOTION_TASKS_DB_ID) to its data source id once and cache.
_data_source_id = None


def _get_tasks_data_source_id():
    """Resolve + cache the task database's data source id from NOTION_TASKS_DB_ID."""
    global _data_source_id
    if _data_source_id is None:
        client = _get_client()
        db_id = os.environ["NOTION_TASKS_DB_ID"]  # KeyError = id missing from .env
        db = client.databases.retrieve(database_id=db_id)
        sources = db.get("data_sources", [])
        if not sources:
            raise RuntimeError(
                "Task database reports no data sources — check NOTION_TASKS_DB_ID "
                "and that the database is shared with the connection."
            )
        _data_source_id = sources[0]["id"]
    return _data_source_id


def query_tasks_by_status(statuses):
    """Return tasks whose Status is one of `statuses`.

    `statuses` is a list of Status names. One value -> an `equals` filter; several
    -> an OR. The filter runs SERVER-SIDE — Notion does the filtering and only
    matching rows come back; we never fetch the whole table and filter in Python.
    Returns [{"name": ..., "assignee": ..., "due": ...}, ...].
    """
    client = _get_client()
    data_source_id = _get_tasks_data_source_id()

    if len(statuses) == 1:
        notion_filter = {"property": "Status", "status": {"equals": statuses[0]}}
    else:
        notion_filter = {
            "or": [{"property": "Status", "status": {"equals": s}} for s in statuses]
        }

    tasks = []
    cursor = None
    while True:
        kwargs = {"filter": notion_filter}
        if cursor:
            kwargs["start_cursor"] = cursor
        # 2025 API: query the data source, not the database.
        resp = client.data_sources.query(data_source_id, **kwargs)
        for page in resp["results"]:
            tasks.append(_task_summary(page))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return tasks


def _task_summary(page):
    """Extract the fields we display from a task page. Property names match the
    'Test Tasks Tracker' DB: 'Task name' (title), 'Assignee' (people), 'Due date'."""
    props = page.get("properties", {})
    return {
        "name": _prop_title(props.get("Task name")),
        "assignee": _prop_people(props.get("Assignee")),
        "due": _prop_date(props.get("Due date")),
    }


def _prop_title(prop):
    if not prop:
        return "(untitled)"
    return _rich_text_to_plain(prop.get("title", [])) or "(untitled)"


def _prop_people(prop):
    if not prop:
        return ""
    names = [person.get("name", "") for person in prop.get("people", [])]
    return ", ".join(n for n in names if n)


def _prop_date(prop):
    if not prop:
        return ""
    date = prop.get("date")
    return date.get("start", "") if date else ""
