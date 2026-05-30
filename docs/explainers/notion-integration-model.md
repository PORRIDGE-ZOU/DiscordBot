# The Notion integration model (incl. the 2025 data-source change)

How the bot reads Notion, why a valid token can still see nothing, and the API
shift that broke our first attempt at querying tasks.

## Connections (integrations) and the token

The bot talks to Notion through an **internal integration** — Notion now labels
these **Connections** in the developer UI. Creating one
(notion.so/my-integrations → New connection → Internal) yields an **Internal
Integration Secret** (`ntn_...`). That secret is the bot's Notion password; it
lives in `.env` as `NOTION_TOKEN`, never in code.

## The sharing gate — why a valid token sees nothing

This is the Notion equivalent of Discord's intents trap, and the single most
common Notion confusion:

> An integration sees **nothing** by default. The token being valid is not enough.

You must **explicitly share** each page or database with the connection:
open it → `•••` → **Connections** → add your connection. Sharing a page **cascades
to its child pages**, so sharing the team's top page exposes the subtree. A page
or database that was never shared returns empty results or a 404 — not an auth
error, which makes it easy to misdiagnose. If `/notion_check` comes back with
fewer items than expected, something isn't shared.

## Reading what's shared: `search`

`/notion_check` calls Notion's `search` with no query, which returns **everything
shared with the connection** — pages and databases. We paginate through the
results and pull a human title out of each. This is also the entry point for the
planned "read every page" feature.

Titles are stored differently per object type: a **database** has a top-level
`title`; a **page** keeps its title inside whichever property has type `"title"`.
`notion_api._title_of` handles both.

## The 2025 data-source model — what changed and why it bit us

Notion reorganized databases in 2025. The new shape:

- A **database** is now a *container*. It holds one or more **data sources**.
- The actual rows (and the schema, and the query endpoint) live in a **data
  source**, not the database.

The installed `notion-client` follows this new API, and the practical consequence
was abrupt: **`databases.query` no longer exists.** Our first `/tasks`
implementation called it and failed with:

```
'DatabasesEndpoint' object has no attribute 'query'
```

(See the post-mortem in `../bugs/2026-05-30-databases-query-removed.md`.)

### How we query now

1. We store the **database id** in `.env` as `NOTION_TASKS_DB_ID` — that's the
   32-character hex chunk before `?v=` in the database's URL. (The `v=` part is a
   *view* id, irrelevant to the API.)
2. On first use we call `databases.retrieve(database_id)`. The response includes a
   `data_sources` list; we take the first one's id and **cache it**.
3. We query that data source: `data_sources.query(data_source_id, filter=...)`.

`notion_api._get_tasks_data_source_id()` does steps 1–2; `query_tasks_by_status`
does step 3. Storing the database id (stable, copy-pasteable from the URL) and
resolving the data source from it keeps configuration simple — you never have to
hunt for a data source id by hand.

## Server-side filtering

The bot never downloads the whole table and filters in Python. It sends Notion a
**filter** and Notion returns only matching rows. For task status:

```python
# one status
{"property": "Status", "status": {"equals": "Done"}}

# several statuses (e.g. "Active" = In progress OR Not started)
{"or": [
    {"property": "Status", "status": {"equals": "In progress"}},
    {"property": "Status", "status": {"equals": "Not started"}},
]}
```

`"status"` here is the filter type for Notion's **Status** property (distinct from
a Select property — they filter differently). The property name `"Status"` must
match the column name in Notion exactly; rename the column and the code string
must change with it. The same is true for `Task name`, `Assignee`, and `Due date`.

This server-side approach is what makes `/tasks` fast and what will let later
queries (assignee = me, due this week) scale without pulling everything.
