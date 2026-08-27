# Reading a Notion database you haven't seen before

Why the bot no longer hardcodes Notion column names, and the pattern that replaced
them: resolve **roles** against the live schema, then build every filter from the
**type** Notion reports.

This is the piece that makes the task commands survive a workspace move. If you're
about to touch `notion_api.py`, read this first.

## The problem, stated precisely

The bot has moved Notion workspaces twice. The second move renamed the sprint column
from `Sprint` to `Sprints`, changed its type from **Select** to **relation**, and
changed its values from `Sprint1` to `Sprint 1`.

That's three independent breakages from one column, and the instructive part is that
they fail *differently*:

| What changed | What the old code did | How it looked |
| --- | --- | --- |
| **Name** (`Sprint` → `Sprints`) | schema check missed, filter silently dropped | "works", but every sprint shown |
| **Type** (select → relation) | built a `rich_text` filter body for a relation | Notion 400, loud |
| **Value** (`Sprint1` → `Sprint 1`) | valid filter matching nothing | "you have no tasks" |

Only the middle one announces itself. The other two are **silent wrong answers**, which
on a task bot is worse than a crash: someone reads "no tasks assigned to you" and
believes it.

So the design goal isn't "handle relations". It's: **make a schema mismatch impossible
to mistake for an empty result.**

## The pattern: roles, not names

Instead of asking *"what is the `Sprint` column?"*, the bot declares what it **needs**
and lets the database answer.

```python
ROLE_ALIASES = {
    "name":     (),                                     # always the title property
    "assignee": ("assignee", "owner", "assigned to", ...),
    "due":      ("due date", "due", "deadline", ...),
    "sprint":   ("sprints", "sprint", "iteration", ...),
    ...
}

ROLE_FALLBACK_TYPES = {
    "name":     ("title",),
    "assignee": ("people",),
    "due":      ("date",),
    ...
}
```

`resolve_roles()` fills each role in two passes:

1. **By name.** Every alias is compared through `_norm()` — lowercase, alphanumerics
   only — so `Due date`, `due_date` and `DueDate` are the same string.
2. **By type.** Any role still empty takes the first **unclaimed** column of an
   acceptable type. A `people` column becomes the assignee even if it's called `Who`.

`name` needs no alias at all: Notion guarantees exactly one property of type `title`
per database, so "the title property" is a complete, unambiguous answer.

### Why "unclaimed" is load-bearing

The current board has *two* `people` columns: `Assignee` and `Approval By`. If the type
pass ran freely, `Approval By` could fill the assignee role and everyone's task list
would quietly be wrong.

Because pass 1 runs first for **every** role and marks its column as claimed, pass 2
can only choose from what's left. Explicit naming always beats a type guess. This is
the single most important rule in the resolver — preserve it if you extend this.

## Crucial vs optional — and why the line is where it is

```python
REQUIRED_ROLES = ("name", "assignee")
```

Only two. Without a title there is nothing to display; without an assignee there is no
way to tell whose task it is, so the entire personal-task feature is meaningless.
Missing either raises `MissingPropertyError`, which the commands print verbatim:

> ⚠️ The task database has no **assignee** column. Name one of your columns `assignee`,
> `assignees`, `owner`… (or any column of type people), then restart the bot so it
> re-reads the schema.

Everything else is optional and **degrades**: its filter is skipped, its display line is
dropped. A database with no sprint column shows all tasks and says "all sprints" in the
header.

The distinction exists entirely to serve the goal above. A missing *optional* column
changes the scope of an answer and says so; a missing *required* column can't produce a
meaningful answer at all, so it must refuse loudly rather than return `[]`.

## Filters come from the type

`_eq_filter(column, value)` looks the column's type up in the cached schema and emits
the matching body. The same call site filters a Select, a Status or a relation without
knowing which it is:

```python
select        → {"select":       {"equals":   value}}
multi_select  → {"multi_select": {"contains": value}}
status        → {"status":       {"equals":   value}}
relation      → {"relation":     {"contains": <resolved page id>}}
people        → {"people":       {"contains": value}}
number        → {"number":       {"equals":   float(value)}}
```

Retyping a Notion column from Select to Status — a two-click change someone can make
without telling you — is now a non-event.

## Relations: the label you see isn't the value that's stored

A relation cell holds **page ids**. `Sprint 1` is the *title of the page* those ids
point at; Notion resolves it for display. Two consequences:

- You cannot filter a relation by its label. `{"relation": {"equals": "Sprint 1"}}` is
  not a filter that exists.
- You cannot read a task's sprint name out of the task row alone.

`_relation_index(column)` solves both with **one** query. It reads the related data
source id from the schema, queries it once, and caches two maps:

```
by_id   : page id          → "Sprint 1"     (display)
by_norm : "sprint1"        → page id        (filtering)
```

Naively resolving each task's relation would be an N+1 — one extra API call per row.
Indexing once turns every later lookup into a dict hit.

> **The related database must be shared with the connection separately.** Notion's
> sharing cascades to *child* pages, not across a relation to another top-level
> database. When it isn't shared the index comes back empty, and the bot degrades
> visibly: sprints render as `1 linked`, and `/setsprint` reports that the column links
> to a database it can't read. Empty, not wrong.

## Loose value matching

`_norm()` is used for values as well as names, which is why `Sprint 1`, `sprint1`,
`SPRINT-1` and a bare `1` all select the same sprint. `query_tasks` re-normalises the
**stored** label on every query, so a sprint saved before a rename still resolves, and
one that has since been deleted raises a named error listing the valid options — rather
than filtering for a value that matches nothing.

## Generic extraction

`_prop_value(prop, column)` renders **any** Notion property as a display string: title,
rich_text, select, multi_select, status, people, date, checkbox, number, url, email,
phone, files, relation, formula, rollup, created/last-edited time and by, unique_id.

An unrecognised type returns `""` rather than raising. That's deliberate: adding an
exotic column in Notion must never be able to break a command that wasn't asking about
it.

This is also what lets `/taskdetail` print the whole row — `_task_full` returns
`task["all"]`, every column in the database with the recognised roles first. A new
Notion column appears there after a restart, with no code change.

## The diagnostic

`/notion_check` prints the resolved map:

```
Task database — what fills each role:
- name       → Task name
- assignee   → Assignee
- sprint     → Sprints
- department → Department
- priority   → — (none found)

Columns (17): Task name (title), Assignee (people), Sprints (relation), …
```

A role showing `—` is the answer to "why is this command filtering wrong". Run it first
after any Notion change; it collapses the three-way sprint breakage above into one
glance.

## Caching and the restart rule

`_data_source_id`, `_schema`, `_roles` and `_relation_cache` are all **per process** and
never invalidated at runtime. The bot reads the board's structure once, at first use.

**Restart the bot after any Notion schema change.** This is the same class of trap as
slash commands registering at startup — see `discord-bot-basics.md`.

## Extending it

- **Teach the bot a new role** — add it to `ROLE_ALIASES`, plus `ROLE_FALLBACK_TYPES` if
  a property type can identify it. Nothing else needs to know.
- **Make a role required** — add it to `REQUIRED_ROLES`, and be sure you mean it: the
  task commands stop working entirely without it.
- **Support a new filter shape** — add a branch to `_eq_filter`. Keep the final
  `rich_text` fallback so an unknown type still produces a runnable call.

See `../deep-dives/notion-task-queries.md` for how these pieces are used by the actual
commands, and `notion-integration-model.md` for the data-source model underneath.
