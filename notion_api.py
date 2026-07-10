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


# --- Workspace users (for /associate) ----------------------------------------
def list_workspace_users():
    """Return [{"id", "name", "email"}, ...] for every PERSON in the workspace.

    Bots and any user without an email come back with email=None. Used by
    /associate to confirm an email belongs to a real Notion member before binding.
    Needs the integration's "read user information" capability.
    """
    client = _get_client()
    users = []
    cursor = None
    while True:
        kwargs = {"start_cursor": cursor} if cursor else {}
        resp = client.users.list(**kwargs)
        for u in resp["results"]:
            if u.get("type") != "person":
                continue  # skip bot users
            email = (u.get("person") or {}).get("email")
            users.append({"id": u["id"], "name": u.get("name", ""), "email": email})
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return users


def list_task_assignees():
    """Distinct people who appear as an Assignee on any task, as
    [{"id","name","email"}, ...].

    Crucial for a team on guest accounts: Notion's `users.list` returns workspace
    MEMBERS only — guests never show up there, even though they're assigned tasks.
    Guests DO appear in the Assignee (people) property, so we harvest identities
    straight from the task rows. `email` may be "" if Notion doesn't expose it for
    that user (common for guests); match by name in that case.
    """
    client = _get_client()
    ds_id = _get_tasks_data_source_id()
    seen = {}
    cursor = None
    while True:
        kwargs = {"start_cursor": cursor} if cursor else {}
        resp = client.data_sources.query(ds_id, **kwargs)
        for page in resp["results"]:
            prop = page.get("properties", {}).get(PROP_ASSIGNEE)
            if not prop:
                continue
            for person in prop.get("people", []):
                uid = person.get("id")
                if not uid or uid in seen:
                    continue
                email = (person.get("person") or {}).get("email") or ""
                seen[uid] = {"id": uid, "name": person.get("name", ""), "email": email}
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return list(seen.values())


def find_notion_person(identifier):
    """Resolve a person by email OR display name (case-insensitive), searching both
    workspace members AND task assignees (so guests are found). Returns
    {"id","name","email"} or None.

    `identifier` is whatever the user typed in /associate — an email or a name.
    """
    target = identifier.strip().lower()
    # Members first (authoritative names/emails), then guests via task assignees.
    candidates = list_workspace_users() + list_task_assignees()
    for c in candidates:
        if c.get("email") and c["email"].lower() == target:
            return c
    for c in candidates:
        if c.get("name") and c["name"].lower() == target:
            return c
    return None


# --- Task database queries ---------------------------------------------------
# Property names in the Task Tracker DB. If a Notion column is renamed, change it
# HERE — every filter and extractor reads from these constants.
PROP_NAME = "Task name"
PROP_STATUS = "Status"
PROP_ASSIGNEE = "Assignee"
PROP_DUE = "Due date"
PROP_PRIORITY = "Priority"
PROP_DEPARTMENT = "Department"
PROP_DESCRIPTION = "Description"
PROP_SPRINT = "Sprint"
PROP_UPDATED = "Updated at"

# Fixed display order for /sprinttasks. A task whose department isn't listed here
# sorts to the end.
DEPARTMENT_ORDER = [
    "Production", "Narrative", "Design", "Art", "Engineering", "QA", "Audio",
]

# Notion's 2025 API splits a database into one or more "data sources"; the rows
# live in a data source and the query endpoint targets it, not the database. We
# resolve the database id (NOTION_TASKS_DB_ID) to its data source id once and cache.
_data_source_id = None
_schema = None  # cached {prop_name: {"type": ..., ...}} for the task data source


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


def _get_schema():
    """Retrieve + cache the task data source's property schema (name -> definition).

    Lets us build the correct filter shape for each property from its TYPE (a
    select, status, and rich_text each take a different filter), instead of
    hardcoding — and exposes the Department select options for validation.
    """
    global _schema
    if _schema is None:
        client = _get_client()
        ds = client.data_sources.retrieve(_get_tasks_data_source_id())
        _schema = ds.get("properties", {})
    return _schema


def get_department_options():
    """Valid Department names = the (multi_)select options defined in Notion."""
    prop = _get_schema().get(PROP_DEPARTMENT, {})
    ptype = prop.get("type")
    if ptype in ("select", "multi_select"):
        return [o["name"] for o in prop.get(ptype, {}).get("options", [])]
    return []


def _eq_filter(prop_name, value):
    """An equals/contains filter for `prop_name`, shaped by the property's type."""
    ptype = _get_schema().get(prop_name, {}).get("type")
    if ptype == "select":
        return {"property": prop_name, "select": {"equals": value}}
    if ptype == "multi_select":
        return {"property": prop_name, "multi_select": {"contains": value}}
    if ptype == "status":
        return {"property": prop_name, "status": {"equals": value}}
    if ptype in ("rich_text", "title"):
        return {"property": prop_name, ptype: {"equals": value}}
    # Unknown/number/etc. — fall back to rich_text equals so the call still runs.
    return {"property": prop_name, "rich_text": {"equals": value}}


def query_tasks(assignee_id=None, sprint=None, department=None):
    """Query the Task Tracker with optional AND filters; return full task dicts.

      assignee_id: Notion user id -> tasks whose Assignee contains them.
      sprint:      int            -> tasks whose Sprint == "Sprint{n}".
      department:  str            -> tasks whose Department == that name.

    Filtering is SERVER-SIDE — Notion returns only matching rows; we never fetch
    the whole table and filter in Python. Paginates.
    """
    client = _get_client()
    ds_id = _get_tasks_data_source_id()

    clauses = []
    if assignee_id:
        clauses.append({"property": PROP_ASSIGNEE, "people": {"contains": assignee_id}})
    # Sprint filter is OPTIONAL: applied only when a sprint is set AND the DB
    # actually has a Sprint column. On a DB without sprints we silently return all
    # sprints rather than erroring, so the task commands still work.
    if sprint is not None and PROP_SPRINT in _get_schema():
        clauses.append(_eq_filter(PROP_SPRINT, f"Sprint{sprint}"))
    if department:
        clauses.append(_eq_filter(PROP_DEPARTMENT, department))

    if len(clauses) == 1:
        notion_filter = clauses[0]
    elif len(clauses) > 1:
        notion_filter = {"and": clauses}
    else:
        notion_filter = None

    tasks = []
    cursor = None
    while True:
        kwargs = {}
        if notion_filter:
            kwargs["filter"] = notion_filter
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.data_sources.query(ds_id, **kwargs)
        for page in resp["results"]:
            tasks.append(_task_full(page))
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return tasks


def _task_full(page):
    """Flatten every displayed property of a task page into a plain dict. Each
    extractor reads the property by its own type, so this is robust to whether
    e.g. Sprint/Priority are select or text columns."""
    props = page.get("properties", {})
    return {
        "id": page["id"],
        "name": _prop_title(props.get(PROP_NAME)),
        "status": _prop_status(props.get(PROP_STATUS)),
        "assignee": _prop_people(props.get(PROP_ASSIGNEE)),
        "due": _prop_date(props.get(PROP_DUE)),
        "priority": _prop_select(props.get(PROP_PRIORITY)),
        "department": _prop_select(props.get(PROP_DEPARTMENT)),
        "description": _prop_rich_text(props.get(PROP_DESCRIPTION)),
        "sprint": _prop_select(props.get(PROP_SPRINT)),
        "updated": _prop_timeish(props.get(PROP_UPDATED)),
    }


# --- Per-type property extractors --------------------------------------------
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


def _prop_status(prop):
    if not prop:
        return ""
    st = prop.get("status")
    return st.get("name", "") if st else ""


def _prop_select(prop):
    """select / multi_select / rich_text / title -> a single display string."""
    if not prop:
        return ""
    ptype = prop.get("type")
    if ptype == "select":
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""
    if ptype == "multi_select":
        return ", ".join(o.get("name", "") for o in prop.get("multi_select", []))
    if ptype in ("rich_text", "title"):
        return _rich_text_to_plain(prop.get(ptype, []))
    return ""


def _prop_rich_text(prop):
    if not prop:
        return ""
    ptype = prop.get("type", "rich_text")
    return _rich_text_to_plain(prop.get(ptype, []))


def _prop_timeish(prop):
    """last_edited_time / created_time / date -> ISO string."""
    if not prop:
        return ""
    ptype = prop.get("type")
    if ptype in ("last_edited_time", "created_time"):
        return prop.get(ptype, "")
    if ptype == "date":
        d = prop.get("date")
        return d.get("start", "") if d else ""
    return ""
