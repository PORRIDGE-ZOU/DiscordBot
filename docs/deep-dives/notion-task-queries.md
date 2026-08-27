# Deep dive: sprint + personal task commands

How the bot answers "what are *my* tasks?" and "what's in this sprint?" end to end —
from linking a Discord user to a Notion person, through the sprint filter, to the
numbered list and the per-task reminders. This is feature 5 (Notion task queries) in
its real form.

The commands covered: `/associate`, `/tasks`, `/taskdetail`, `/setsprint`, `/sprint`,
`/sprinttasks`, `/remind`.

## The core idea

Notion knows tasks are assigned to **Notion people**. Discord knows **Discord users**.
Nothing connects the two automatically — so the bot keeps an explicit **association**:
one Discord user ↔ one Notion person. Once you're associated, "my tasks" = the tasks
Notion has assigned to *your* Notion person, narrowed to the **current sprint**.

Two pieces of state make this work, and **both live in a local SQLite (`store.py`,
`botstate.db`), not in Notion** — Notion stays read-only:

- **associations** — `discord_id → (notion_user_id, notion_name, email)`.
- **config** — the `current_sprint` **label** (a string like `Sprint 1`, not a number —
  sprint naming differs per workspace).

## `/associate` — linking the two worlds

```
/associate person:george@usc.edu member:@porridge
→ ✅ Linked @porridge ↔ George Zou (george@usc.edu).
```

- `member` is a Discord **user-picker** (`discord.Option(discord.Member, ...)`), so
  Discord guarantees it's a real member of this server and hands us the **stable user
  ID** — never a username, which can change.
- `person` is an **email OR a display name**, resolved by
  `notion_api.find_notion_person` (case-insensitive, email first then name). No match →
  the command does nothing and says so. (Reading assignee names/emails needs the
  integration's **"Read user information"** capability — see
  `../explainers/notion-integration-model.md`.)
- **Guests are the reason `person` accepts a name.** Notion's `users.list` returns
  workspace **members only** — guests never appear there, even though they're assigned
  tasks. A team on guest accounts (to avoid per-seat cost) would be unresolvable by the
  members list alone. So `find_notion_person` searches **members *plus* everyone who
  appears as an assignee** (`list_task_assignees`, which harvests people straight from
  the task rows). Guests frequently have **no email exposed** through the API, so for
  them you pass their **display name exactly as it shows in the Assignee column**.
- The binding is **1:1 in both directions**. `store.set_association` deletes any row
  already holding that key before upserting, so a person can't map to two Discord
  users. It returns what it displaced, and the command reports a re-bind explicitly:
  *"⚠️ This was already bound! … Now re-bound: …"*. The key is the email when Notion
  exposes one, else the display name.

We store the **Notion user id** (a stable uuid), because that's what lets us filter
tasks by assignee **server-side** (the People filter takes a user id, not an email) —
and that id is present on every assignee, member or guest.

## Setting the sprint — `/setsprint` and `/sprint`

`/setsprint label:Sprint 1` writes `current_sprint = "Sprint 1"` into the local config
table (anyone may set it — it's shared team state). `/sprint` reads it back:
*"We're in **Sprint 1**!"*.

It's a **label, not a number**, because sprint naming is a per-workspace choice —
`Sprint 1`, `S3`, `Summer`. The command validates it against the sprint values that
actually exist in Notion (`notion_api.get_sprint_options`) and rejects an unknown one
**with the real list**, rather than accepting it and silently matching zero tasks later.

Matching is deliberately loose. `notion_api._norm()` reduces a string to lowercase
alphanumerics, so `Sprint 1`, `sprint1`, `SPRINT-1` and even a bare `1` all collapse to
the same key and land on the same sprint. `query_tasks` re-normalises the *stored* label
on every query too, so a value saved before a rename still resolves — and a sprint that
has since been deleted produces a named error instead of an empty list.

**Sprint scoping is optional.** The filter applies only when a sprint is set **and** the
database actually has a sprint column. Without either, the task commands still work —
they show all sprints, and the headers read "all sprints" / "All tasks".

### When the sprint column is a relation

In the current workspace, `Sprints` is a **relation** to a separate Sprints database,
not a Select. That changes two things:

- A relation cell holds **page ids**, not text. Filtering by "Sprint 1" means finding
  that sprint page's id first: `{"property": "Sprints", "relation": {"contains": "<page
  id>"}}`.
- Displaying a task's sprint means turning the id back into a title.

Both directions come from **one** query. `_relation_index(column)` reads the related
data source id out of the schema, queries it once, and caches two maps — `page id →
title` and `normalised title → page id`. Every subsequent lookup is a dict hit; there is
no per-task fetch.

> The related database must be **shared with the connection separately**. Sharing the
> task database does *not* cascade across a relation. When it isn't shared, the index
> comes back empty: sprints display as `1 linked` instead of `Sprint 1`, and
> `/setsprint` says the column links to a database the bot can't read.

## The one shared list — why task numbers line up

`/tasks`, `/taskdetail #`, and `/remind` all operate on **the same ordered list** of
your sprint tasks, so "task 3" means the same task in all three. That's enforced by
two shared helpers in `bot.py`:

- **`_load_personal_tasks(ctx)`** — resolves your association, queries your tasks
  (scoped to the current sprint **if one is set**), returns them sorted. If you're not
  linked, or the Notion query itself fails, it sends the right ephemeral error and
  returns `None`; the caller just stops. It wraps the query in try/except so a Notion
  error (e.g. a bad DB id) is **reported**, not left hanging on "thinking…". A missing
  *required column* is caught separately as `MissingPropertyError` and shown with a ⚠️
  and the fix.
- **`_personal_sorted(tasks)`** — the canonical order: **Due date ascending
  (no-due-date last), tiebreak by Task name.** ISO date strings (`2026-06-20`) sort
  correctly as plain strings, so no date parsing is needed for ordering.

If you ever add a command that numbers a user's tasks, route it through these two so
the numbering stays consistent.

> The number is a **snapshot**. If the board changes between `/tasks` and
> `/taskdetail 3`, the list is recomputed and #3 may differ. That's an accepted
> trade-off for v1 — the alternative (caching each user's last list) adds state for
> little gain.

## The query — one function, schema-driven filters

Everything funnels through one generalized function:

```python
notion_api.query_tasks(assignee_id=None, sprint=None, department=None)
```

It builds an **`and`** of whichever filters you pass and runs it **server-side** (Notion
returns only matching rows; we never download the whole board). The three filter
clauses:

| Argument | Notion filter |
| --- | --- |
| `assignee_id` | `{"property": <assignee column>, "people": {"contains": <user id>}}` |
| `sprint` | the sprint column `== <label>`, shaped by that column's type |
| `department` | the department column `== <name>` |

Note what's *not* in that table: column names. Which brings us to the part that matters.

## Roles, not column names

The bot has now survived two workspace moves. The second one renamed `Sprint` to
`Sprints`, changed its type from Select to **relation**, and changed its values from
`Sprint1` to `Sprint 1` — three independent breakages from one column, and only one of
them was loud. (Post-mortem:
`../bugs/2026-07-10-notion-workspace-migration.md`.) So the bot stopped hardcoding
column names entirely.

Instead it declares the **roles** it needs — `name`, `assignee`, `status`, `due`,
`sprint`, `department`, `priority`, `description`, `updated` — and resolves each one
against the live schema in `resolve_roles()`, in two passes:

1. **By name.** Each role has a list of accepted aliases (`ROLE_ALIASES`), compared
   through `_norm()`, so `Due date`, `due_date` and `DueDate` all match.
2. **By type.** Any role still unfilled takes the first *unclaimed* column of an
   acceptable type (`ROLE_FALLBACK_TYPES`) — a `people` column becomes the assignee, a
   `date` column becomes the due date. `name` is always simply the property of type
   `title`, of which Notion guarantees exactly one.

A column can only be claimed by one role, which is what stops the new `Approval By`
(also a `people` column) from being mistaken for the assignee once `Assignee` has
matched by name. The result is cached in `_roles`.

The full design — including why the required/optional line falls where it does, and how
relations are indexed — is in
`../explainers/schema-driven-notion-columns.md`.

**Crucial vs optional.** `REQUIRED_ROLES` is just `name` + `assignee` — without them
there is nothing to list and no way to tell whose task it is. Their absence raises
`MissingPropertyError`, which the commands print verbatim ("The task database has no
**assignee** column. Name one of your columns …"). Every other role is optional: its
filter is skipped and its display line is dropped. This distinction is deliberate — a
silently-skipped filter looks exactly like "you have no tasks", which is the worst
failure mode this feature has.

### Filters are built from the type, not assumed

`_eq_filter(column, value)` reads the column's **type** from the cached schema and emits
the matching filter body:

| Type | Filter |
| --- | --- |
| `select` | `{"select": {"equals": v}}` |
| `multi_select` | `{"multi_select": {"contains": v}}` |
| `status` | `{"status": {"equals": v}}` |
| `relation` | `{"relation": {"contains": <resolved page id>}}` |
| `people` | `{"people": {"contains": v}}` |
| `number` | `{"number": {"equals": float(v)}}` |
| `rich_text` / `title` | `{"<type>": {"equals": v}}` |

So the same call site filters a Select, a Status or a relation without knowing which it
is — the schema decides. `get_options(role)` reads that same schema for the **valid
values** of a role (a select's options, or the titles behind a relation), which
`/setsprint` and `/sprinttasks` use to reject typos with a real list.

## Reading every property — `_task_full`

`_task_full` flattens a task page into plain strings. The **role keys** feed the compact
views:

| Key | Filled by the role | Used by |
| --- | --- | --- |
| name | `title` property | every view |
| status, assignee, due | resolved columns | `/tasks`, `/sprinttasks` |
| priority, department, sprint, description, updated | resolved columns | sorting, headers |

…and `task["all"]` carries **every column the database has** — recognised roles first,
then the rest in Notion's own order — which is what `/taskdetail` prints. Add a column
in Notion, restart the bot, and it shows up. No code change.

Every value goes through one dispatcher, `_prop_value(prop, column)`, which handles
title, rich_text, select, multi_select, status, people, date, checkbox, number, url,
email, phone, files, relation, formula, rollup, created/last-edited time and by, and
unique_id. **An unrecognised type returns `""` rather than raising** — so an exotic new
Notion column can never break a command that wasn't asking about it.

`due` stays the raw ISO date string, because `_personal_sorted` sorts on it and
`/remind` parses it.

## The commands at a glance

- **`/tasks`** — your sprint tasks, numbered: `N. **Name** — Status — 📅 Due — Desc`
  (description truncated). Ephemeral.
- **`/taskdetail n`** — **every** property of task *n* from that same list, under its
  own Notion name. Ephemeral.
- **`/sprinttasks`** — the whole sprint, public. With no argument it groups by the
  department order **defined in Notion** (the select's own option order, which is the
  order Notion shows them in); unknown departments last. With a `department` argument it
  validates the name against the Notion options, then lists just that department.

## `/remind x` — a DM before each task is due

```
/remind 3
→ Scheduled 4 reminder(s), 3 day(s) before each due date. Skipped 1 (no due date / already past).
```

For each of your current-sprint tasks **that has a due date**, the bot schedules **one**
DM, fired `x` days before that task's due date (at 09:00 California). So three tasks with
three due dates → three separate DMs.

- **No due date, or the reminder moment is already past** → skipped (and counted).
- **Re-running `/remind`** first clears your previous batch
  (`scheduler.clear_task_reminders`), then schedules fresh — so it never stacks
  duplicates.
- The task text is **snapshotted at schedule time** and passed as the job's argument, so
  the reminder survives a bot restart (the jobs live in the persistent `jobs.sqlite`
  store). The trade-off: if the task changes after you set the reminder, the DM shows the
  old text.

These per-task jobs are namespaced `taskremind:<discord_id>:<i>` so they can be cleared
per user and kept **out of `/reminders`**, which lists only channel reminders. Full
scheduler background lives alongside the channel-reminder code in `scheduler.py`.

## How to extend it

- **"Due this week" / date filters** → add a `date` clause to `query_tasks` (Notion
  supports a `this_week` filter) and `and` it in like the others.
- **Filter `/tasks` by status too** → add a `status` argument to `query_tasks` and an
  `_eq_filter(_role_prop("status"), …)` clause, guarded by `if status and status_col`
  like the others.
- **Teach the bot a new role** (say, "epic") → add it to `ROLE_ALIASES` (and
  `ROLE_FALLBACK_TYPES` if a type can identify it). Nothing else needs to know.
- **A "who's overloaded?" view** → `query_tasks(sprint=…)` returns every task with its
  assignee; group in Python.
- **Let people self-associate only** → gate `/associate` so `member` must equal
  `ctx.author` unless the caller is a lead. (Today anyone can bind anyone — a deliberate
  v1 choice.)
