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
    assignee_col = require_role("assignee")  # resolved from the live schema
    seen = {}
    cursor = None
    while True:
        kwargs = {"start_cursor": cursor} if cursor else {}
        resp = client.data_sources.query(ds_id, **kwargs)
        for page in resp["results"]:
            prop = page.get("properties", {}).get(assignee_col)
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



# --- Task database: schema-driven column resolution --------------------------
# The bot must survive a workspace/DB swap where columns get renamed or change
# TYPE (our "Sprint" select became a "Sprints" RELATION). So nothing here is
# hardcoded to a column name: we describe what the bot NEEDS as a set of ROLES,
# then resolve each role against the live schema — by name alias first, by
# property TYPE second — and build every filter from the type Notion reports.


class MissingPropertyError(Exception):
    """The task database lacks a property the bot can't work without.

    Raised (and surfaced to the user verbatim) instead of failing silently — a
    silently-skipped filter looks like "you have no tasks", which is the worst
    possible failure mode.
    """


# role -> column names we accept for it, most specific first. Compared loosely
# (case/space/punctuation-insensitive), so "Due date", "due_date" and "DueDate"
# all match the same alias.
ROLE_ALIASES = {
    "name": (),  # always the title property — no alias needed
    "assignee": ("assignee", "assignees", "owner", "owners", "assigned to", "assigned"),
    "status": ("status", "state", "progress"),
    "due": ("due date", "due", "deadline", "due on", "end date"),
    "sprint": ("sprints", "sprint", "iteration", "cycle"),
    "department": ("department", "departments", "dept", "team", "discipline"),
    "priority": ("priority", "importance"),
    "description": ("description", "notes", "details", "summary"),
    "updated": ("updated at", "updated", "last edited", "last edited time"),
}

# Second-chance resolution: if no column matched a role's aliases, take the first
# unclaimed column of one of these types. This is what makes a never-seen-before
# database work — a title is a title and a people column is a people column no
# matter what it's called.
ROLE_FALLBACK_TYPES = {
    "name": ("title",),
    "assignee": ("people",),
    "status": ("status",),
    "due": ("date",),
    "updated": ("last_edited_time",),
    "department": ("select", "multi_select"),
}

# Without these two the personal-task feature has no meaning: nothing to show,
# and no way to tell whose task it is.
REQUIRED_ROLES = ("name", "assignee")

# Display order for the known roles in /taskdetail; every other column follows in
# the schema's own order.
ROLE_DISPLAY_ORDER = (
    "status", "assignee", "due", "priority", "department", "sprint",
    "updated", "description",
)

# Notion's 2025 API splits a database into one or more "data sources"; the rows
# live in a data source and the query endpoint targets it, not the database. We
# resolve the database id (NOTION_TASKS_DB_ID) to its data source id once and cache.
# Everything below is cached PER PROCESS — restart the bot after any Notion
# schema change so it re-reads.
_data_source_id = None
_schema = None       # {prop_name: {"type": ..., ...}} for the task data source
_roles = None        # {role: column name or None}
_relation_cache = {}  # prop_name -> {"by_id": {...}, "by_norm": {...}}


def _norm(text):
    """Lowercase, alphanumerics only — the loose key used for every name/value
    comparison. 'Sprint 1', 'Sprint1' and 'sprint-1' all collapse to 'sprint1'."""
    return "".join(ch for ch in str(text).lower() if ch.isalnum())


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

    This is the single source of truth for the whole module: role resolution,
    filter shapes, select options and relation targets all read from it.
    """
    global _schema
    if _schema is None:
        client = _get_client()
        ds = client.data_sources.retrieve(_get_tasks_data_source_id())
        _schema = ds.get("properties", {})
    return _schema


def resolve_roles():
    """Map every role to a real column in this database (or None). Cached.

    Two passes so an explicitly-named column always beats a type guess:
      1. alias match  — "Sprints" fills the `sprint` role.
      2. type fallback — an unclaimed `people` column fills `assignee`.
    A column is claimed by at most one role, so e.g. "Approval By" can't be
    mistaken for the assignee once "Assignee" has been matched.
    """
    global _roles
    if _roles is None:
        schema = _get_schema()
        by_norm = {}
        for col in schema:
            by_norm.setdefault(_norm(col), col)

        found = {}
        claimed = set()
        for role, aliases in ROLE_ALIASES.items():
            for alias in aliases:
                col = by_norm.get(_norm(alias))
                if col and col not in claimed:
                    found[role] = col
                    claimed.add(col)
                    break
        for role, types in ROLE_FALLBACK_TYPES.items():
            if found.get(role):
                continue
            for col, defn in schema.items():
                if col not in claimed and defn.get("type") in types:
                    found[role] = col
                    claimed.add(col)
                    break
        _roles = {role: found.get(role) for role in ROLE_ALIASES}
    return _roles


def _role_prop(role):
    """The column filling `role`, or None if this database hasn't got one."""
    return resolve_roles().get(role)


def require_role(role):
    """Like _role_prop, but raise a MissingPropertyError naming exactly what to
    add/rename in Notion. Used for the roles a command genuinely can't work without."""
    col = _role_prop(role)
    if col is None:
        aliases = ROLE_ALIASES.get(role, ())
        types = ROLE_FALLBACK_TYPES.get(role, ())
        want = ", ".join(f"`{a}`" for a in aliases) or "a title property"
        hint = f" (or any column of type {', '.join(types)})" if types else ""
        raise MissingPropertyError(
            f"The task database has no **{role}** column. Name one of your columns "
            f"{want}{hint}, then restart the bot so it re-reads the schema."
        )
    return col


def check_required():
    """Raise if the database is missing a role the task commands depend on."""
    for role in REQUIRED_ROLES:
        require_role(role)


def describe_schema():
    """Diagnostic used by /notion_check: which column fills each role, which roles
    are unfilled, and every column with its Notion type."""
    schema = _get_schema()
    roles = resolve_roles()
    return {
        "roles": dict(roles),
        "missing_required": [r for r in REQUIRED_ROLES if not roles.get(r)],
        "missing_optional": [
            r for r in ROLE_ALIASES if r not in REQUIRED_ROLES and not roles.get(r)
        ],
        "columns": [(name, defn.get("type", "?")) for name, defn in schema.items()],
    }


# --- Relations ---------------------------------------------------------------
# A relation cell holds PAGE IDS, not text. To filter by "Sprint 1" we need that
# sprint page's id, and to display a task's sprint we need the id back as a title.
# So we index the related data source ONCE (one query, cached) in both directions
# — never one lookup per task.

def _relation_data_source(prop_name):
    """The data source id a relation column points at, or None."""
    defn = _get_schema().get(prop_name, {})
    if defn.get("type") != "relation":
        return None
    rel = defn.get("relation") or {}
    ds_id = rel.get("data_source_id")
    if ds_id:
        return ds_id
    # Older payloads only name the database; resolve it the same way we do ours.
    db_id = rel.get("database_id")
    if not db_id:
        return None
    try:
        db = _get_client().databases.retrieve(database_id=db_id)
        sources = db.get("data_sources", [])
        return sources[0]["id"] if sources else None
    except Exception:
        return None


def _relation_index(prop_name):
    """{"by_id": {page id: title}, "by_norm": {loose title: page id}} for a
    relation column, cached.

    Both maps come back EMPTY if the related database isn't shared with the
    connection — sharing the task DB does NOT cascade to a database it merely
    links to. Callers degrade instead of crashing.
    """
    if prop_name not in _relation_cache:
        by_id, by_norm = {}, {}
        ds_id = _relation_data_source(prop_name)
        if ds_id:
            try:
                client = _get_client()
                cursor = None
                while True:
                    kwargs = {"start_cursor": cursor} if cursor else {}
                    resp = client.data_sources.query(ds_id, **kwargs)
                    for page in resp["results"]:
                        title = _title_of(page)
                        by_id[page["id"]] = title
                        by_norm.setdefault(_norm(title), page["id"])
                    if not resp.get("has_more"):
                        break
                    cursor = resp.get("next_cursor")
            except Exception:
                by_id, by_norm = {}, {}
        _relation_cache[prop_name] = {"by_id": by_id, "by_norm": by_norm}
    return _relation_cache[prop_name]


# --- Options + filters -------------------------------------------------------

def get_options(role):
    """Every valid value for a role's column: the select/status options defined in
    Notion, or the titles of the related pages for a relation. [] when the column
    is free-form (text/number) or absent — the caller then skips validation."""
    col = _role_prop(role)
    if not col:
        return []
    defn = _get_schema().get(col, {})
    ptype = defn.get("type")
    if ptype in ("select", "multi_select", "status"):
        return [o.get("name", "") for o in (defn.get(ptype) or {}).get("options", [])]
    if ptype == "relation":
        return sorted(_relation_index(col)["by_id"].values())
    return []


def get_department_options():
    """Valid Department names, whatever the department column is called."""
    return get_options("department")


def get_sprint_options():
    """Valid sprint labels, whatever the sprint column is called or typed."""
    return get_options("sprint")


def match_sprint(label):
    """Canonical sprint label for whatever the user typed, or None if no match.

    Matching is loose: 'Sprint 1' == 'sprint1' == 'SPRINT-1', and a bare '1' also
    tries 'sprint1' (so an old numeric setting still resolves). When the column
    exists but its values aren't enumerable (free text), the label is accepted
    as-is — there's nothing to validate against.
    """
    col = _role_prop("sprint")
    if not col:
        return None
    if _get_schema().get(col, {}).get("type") == "relation" and not _relation_index(col)["by_id"]:
        raise MissingPropertyError(
            f"The `{col}` column links to another database the bot can't read. Open "
            "that database → ••• → Connections → add the bot's connection, then "
            "restart the bot."
        )
    options = get_sprint_options()
    if not options:
        return label
    target = _norm(label)
    candidates = {target, f"sprint{target}"}
    if target.startswith("sprint"):
        candidates.add(target[len("sprint"):])
    for option in options:
        if _norm(option) in candidates:
            return option
    return None


def _eq_filter(prop_name, value):
    """An equals/contains filter for `prop_name`, shaped by the property's TYPE.

    Each Notion property type takes a different filter body; reading the type from
    the cached schema is what lets the same call site filter a select, a status or
    a relation without knowing which it is.
    """
    ptype = _get_schema().get(prop_name, {}).get("type")
    if ptype == "select":
        return {"property": prop_name, "select": {"equals": value}}
    if ptype == "multi_select":
        return {"property": prop_name, "multi_select": {"contains": value}}
    if ptype == "status":
        return {"property": prop_name, "status": {"equals": value}}
    if ptype == "relation":
        # Relations filter on the related PAGE ID, so resolve the label first.
        page_id = _relation_index(prop_name)["by_norm"].get(_norm(value))
        if not page_id:
            raise MissingPropertyError(
                f"Couldn't resolve **{value}** in the `{prop_name}` relation. Share "
                "the database it links to with the bot's connection too "
                "(open it → ••• → Connections), then restart the bot."
            )
        return {"property": prop_name, "relation": {"contains": page_id}}
    if ptype == "people":
        return {"property": prop_name, "people": {"contains": value}}
    if ptype == "checkbox":
        return {"property": prop_name, "checkbox": {"equals": bool(value)}}
    if ptype == "number":
        try:
            return {"property": prop_name, "number": {"equals": float(value)}}
        except (TypeError, ValueError):
            pass
    if ptype in ("rich_text", "title"):
        return {"property": prop_name, ptype: {"equals": value}}
    # Unknown type — fall back to rich_text equals so the call still runs.
    return {"property": prop_name, "rich_text": {"equals": value}}


def query_tasks(assignee_id=None, sprint=None, department=None):
    """Query the task database with optional AND filters; return full task dicts.

      assignee_id: Notion user id -> tasks whose assignee column contains them.
      sprint:      str            -> tasks in that sprint (label, matched by type).
      department:  str            -> tasks in that department.

    Every filter is skipped when this database has no column for that role, so a
    sprint-less or department-less DB still answers. Filtering is SERVER-SIDE —
    Notion returns only matching rows; we never fetch the whole table and filter
    in Python. Paginates.
    """
    check_required()
    client = _get_client()
    ds_id = _get_tasks_data_source_id()

    clauses = []
    if assignee_id:
        clauses.append(
            {"property": require_role("assignee"), "people": {"contains": assignee_id}}
        )
    sprint_col = _role_prop("sprint")
    if sprint is not None and sprint_col:
        # Normalise the stored label against what Notion actually has, so a value
        # saved before a rename (or an old bare "2") still resolves — and a sprint
        # that no longer exists says so instead of returning zero tasks.
        canonical = match_sprint(sprint)
        if canonical is None:
            raise MissingPropertyError(
                f"The current sprint **{sprint}** doesn't exist in the `{sprint_col}` "
                f"column any more. Valid: {', '.join(get_sprint_options()) or '(none)'}"
                " — run `/setsprint` to pick one."
            )
        clauses.append(_eq_filter(sprint_col, canonical))
    dept_col = _role_prop("department")
    if department and dept_col:
        clauses.append(_eq_filter(dept_col, department))

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
    """Flatten a task page into plain strings.

    The role keys (name/status/due/...) feed the compact views; "all" carries
    EVERY column this database has, in schema order, for /taskdetail — so a new
    Notion column shows up with no code change.
    """
    props = page.get("properties", {})
    roles = resolve_roles()

    def role_value(role):
        col = roles.get(role)
        return _prop_value(props.get(col), col) if col else ""

    task = {
        "id": page["id"],
        "name": role_value("name") or "(untitled)",
        "status": role_value("status"),
        "assignee": role_value("assignee"),
        "due": role_value("due"),
        "priority": role_value("priority"),
        "department": role_value("department"),
        "description": role_value("description"),
        "sprint": role_value("sprint"),
        "updated": role_value("updated"),
    }
    # Every other column, known roles first then the rest in Notion's own order —
    # /taskdetail renders these verbatim, so a new column appears with no code change.
    ordered = [roles[r] for r in ROLE_DISPLAY_ORDER if roles.get(r)]
    ordered += [
        col for col in _get_schema()
        if col not in ordered and col != roles.get("name")
    ]
    task["all"] = [(col, _prop_value(props.get(col), col)) for col in ordered]
    return task


# --- Generic property extraction ---------------------------------------------
# One dispatcher over every Notion property type. An unrecognised type returns ""
# rather than raising, so adding an exotic column in Notion can never break a
# command.

def _scalar(value):
    """Whatever a formula/rollup hands back -> a display string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "✅" if value else "☐"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):  # a date {"start": ...} or an option {"name": ...}
        return value.get("start") or value.get("name") or ""
    if isinstance(value, list):
        return _rich_text_to_plain(value)
    return str(value)


def _prop_value(prop, prop_name=""):
    """Plain-string value of ANY Notion property, dispatched on its own type.

    `prop_name` is only needed for relations, which look up their titles in the
    cached index for that column.
    """
    if not prop:
        return ""
    ptype = prop.get("type")

    if ptype in ("title", "rich_text"):
        return _rich_text_to_plain(prop.get(ptype, []))
    if ptype == "select":
        return (prop.get("select") or {}).get("name", "")
    if ptype == "status":
        return (prop.get("status") or {}).get("name", "")
    if ptype == "multi_select":
        return ", ".join(o.get("name", "") for o in prop.get("multi_select", []))
    if ptype == "people":
        names = [p.get("name") or "" for p in prop.get("people", [])]
        return ", ".join(n for n in names if n)
    if ptype == "date":
        # Kept as the raw ISO start: /tasks sorts on it and /remind parses it.
        d = prop.get("date") or {}
        start, end = d.get("start", ""), d.get("end")
        return f"{start} → {end}" if end else start
    if ptype == "checkbox":
        return "✅" if prop.get("checkbox") else "☐"
    if ptype == "number":
        n = prop.get("number")
        return "" if n is None else str(n)
    if ptype in ("url", "email", "phone_number"):
        return prop.get(ptype) or ""
    if ptype == "files":
        names = []
        for f in prop.get("files", []):
            names.append(
                f.get("name")
                or (f.get("external") or {}).get("url")
                or (f.get("file") or {}).get("url")
                or ""
            )
        return ", ".join(n for n in names if n)
    if ptype == "relation":
        links = prop.get("relation", [])
        titles = []
        if prop_name:
            by_id = _relation_index(prop_name)["by_id"]
            titles = [by_id.get(item.get("id"), "") for item in links]
            titles = [t for t in titles if t]
        if titles:
            return ", ".join(titles)
        # Related DB not shared -> we know how many links there are, not their names.
        return f"{len(links)} linked" if links else ""
    if ptype in ("created_time", "last_edited_time"):
        return prop.get(ptype) or ""
    if ptype in ("created_by", "last_edited_by"):
        return (prop.get(ptype) or {}).get("name") or ""
    if ptype == "unique_id":
        uid = prop.get("unique_id") or {}
        number, prefix = uid.get("number"), uid.get("prefix")
        if number is None:
            return ""
        return f"{prefix}-{number}" if prefix else str(number)
    if ptype == "formula":
        formula = prop.get("formula") or {}
        return _scalar(formula.get(formula.get("type")))
    if ptype == "rollup":
        rollup = prop.get("rollup") or {}
        rtype = rollup.get("type")
        if rtype == "array":
            values = (_prop_value(item) for item in rollup.get("array", []))
            return ", ".join(v for v in values if v)
        return _scalar(rollup.get(rtype))
    return ""
