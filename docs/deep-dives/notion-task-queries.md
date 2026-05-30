# Deep dive: `/tasks` — status-filtered task queries

How the `/tasks` command works end to end, from the dropdown a user picks to the
message the team sees. This is feature 5 (Notion task queries) in its first form:
filtering by status. Later additions ("my tasks", date filters) will extend the
same machinery.

## What the user sees

```
/tasks status:Active
→ Tasks — Active (2):
  - Update help center & FAQ · 👤 imglebasi · 📅 2025-02-20
  - Publish release notes · 👤 George Zou · 📅 2025-02-28
```

The dropdown offers **Done**, **In progress**, **Not started**, **Pivoted**, and
**Active**. "Active" is the team's shorthand for *not Done and not Pivoted* — i.e.
In progress + Not started. The reply is public so the whole team sees it.

## The path through the code

### 1. The choice → status values (`bot.py`)

```python
TASK_STATUS_CHOICES = {
    "Done": ["Done"],
    "In progress": ["In progress"],
    "Not started": ["Not started"],
    "Pivoted": ["Pivoted"],
    "Active": notion_api.ACTIVE_STATUSES,   # ["In progress", "Not started"]
}
```

The dropdown choices are just the keys of this dict. Each maps to a **list** of
Notion Status values — length 1 for a single status, length 2 for "Active". The
list-of-values shape is what lets one code path handle both the simple and the
compound case.

### 2. The handler (`bot.py`)

```python
async def tasks(ctx, status: discord.Option(str, choices=list(TASK_STATUS_CHOICES))):
    await ctx.defer()                                   # 3-second rule
    statuses = TASK_STATUS_CHOICES[status]
    rows = await asyncio.to_thread(                     # sync SDK off the event loop
        notion_api.query_tasks_by_status, statuses)
    ...
    await ctx.respond(formatted)                        # follow-up, ≤2000 chars
```

It follows the standard IO pattern: **defer → to_thread → respond**. `defer()`
because a Notion round-trip can exceed Discord's 3-second deadline; `to_thread`
because `notion-client` is synchronous and would otherwise block the gateway.

### 3. The query (`notion_api.py`)

```python
def query_tasks_by_status(statuses):
    data_source_id = _get_tasks_data_source_id()        # resolve + cache (see below)
    if len(statuses) == 1:
        flt = {"property": "Status", "status": {"equals": statuses[0]}}
    else:
        flt = {"or": [{"property": "Status", "status": {"equals": s}} for s in statuses]}
    # paginate through data_sources.query(data_source_id, filter=flt)
    # -> [{"name", "assignee", "due"}, ...]
```

The filter is built **server-side**: Notion does the filtering and only matching
rows come back. One status → an `equals` filter; several → an `or` of `equals`.
Results are paginated (Notion returns up to 100 per page) so nothing is dropped on
a large board.

### 4. Resolving the data source (`notion_api.py`)

Because of Notion's 2025 data-source model, you can't query a database directly —
you query its data source. `_get_tasks_data_source_id()` calls
`databases.retrieve(NOTION_TASKS_DB_ID)` once, reads `data_sources[0]["id"]`, and
caches it for the process lifetime. Full background:
`../explainers/notion-integration-model.md`.

### 5. Extracting fields (`notion_api.py`)

Each returned row is a Notion **page** whose columns live under `properties`.
`_task_summary` pulls three by exact property name:

| Display | Notion property | Type | Helper |
| --- | --- | --- | --- |
| name | `Task name` | title | `_prop_title` |
| assignee | `Assignee` | people | `_prop_people` (joins names) |
| due | `Due date` | date | `_prop_date` (takes `date.start`) |

Rename any of these columns in Notion and the matching string in `_task_summary`
must change too — the names are matched literally.

### 6. Formatting (`bot.py`)

Rows become `- **name** · 👤 assignee · 📅 due` lines under a
`Tasks — <status> (<count>):` header. Empty assignee or due fields are omitted.
The whole message is truncated to 1990 characters to stay under Discord's 2000-char
cap — a real limit to revisit if a status ever returns a very long list (options
then: paginate, or attach a file).

## How to extend it

- **A new status grouping** (e.g. "Stalled") → add one entry to
  `TASK_STATUS_CHOICES`. No other change.
- **"My tasks"** → add an `assignee` filter (people property) `and`-ed with status,
  plus a Discord-user → Notion-assignee mapping (a config dict) to know who "me" is.
- **"Due this week"** → `and` a Notion `date` filter with `this_week` onto the
  existing filter. The server-side approach already supports it.
