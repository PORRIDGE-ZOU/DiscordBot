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
- **config** — the `current_sprint` number.

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

`/setsprint 2` writes `current_sprint = 2` into the local config table (anyone may set
it — it's shared team state). `/sprint` reads it back: *"We're in **Sprint 2**!"*.

The sprint number `2` becomes the Notion filter value **`"Sprint2"`** — the task DB's
`Sprint` column (a Select) stores values named exactly `Sprint1`, `Sprint2`, …. The
conversion is a single `f"Sprint{n}"` inside `query_tasks`, so the command layer only
ever deals in integers. (If your Select options are named differently, the filter
won't match — the names must be `Sprint{n}`.)

**Sprint scoping is optional.** `query_tasks` applies the Sprint filter only when a
sprint is set **and** the DB actually has a `Sprint` column. With no sprint set (or a
DB that has no such column), the task commands still work — they just show all sprints,
and the headers read "all sprints" / "All tasks" instead of "Sprint N". This keeps the
bot usable before sprints are configured.

## The one shared list — why task numbers line up

`/tasks`, `/taskdetail #`, and `/remind` all operate on **the same ordered list** of
your sprint tasks, so "task 3" means the same task in all three. That's enforced by
two shared helpers in `bot.py`:

- **`_load_personal_tasks(ctx)`** — resolves your association, queries your tasks
  (scoped to the current sprint **if one is set**), returns them sorted. If you're not
  linked, or the Notion query itself fails, it sends the right ephemeral error and
  returns `None`; the caller just stops. It wraps the query in try/except so a Notion
  error (e.g. a missing column, a bad DB id) is **reported**, not left hanging on
  "thinking…".
- **`_personal_sorted(tasks)`** — the canonical order: **Due date ascending
  (no-due-date last), tiebreak by Task name.** ISO date strings (`2026-06-20`) sort
  correctly as plain strings, so no date parsing is needed for ordering.

If you ever add a command that numbers a user's tasks, route it through these two so
the numbering stays consistent.

> The number is a **snapshot**. If the board changes between `/tasks` and
> `/taskdetail 3`, the list is recomputed and #3 may differ. That's an accepted
> trade-off for v1 — the alternative (caching each user's last list) adds state for
> little gain.

## The query — one function, type-aware filters

Everything funnels through one generalized function:

```python
notion_api.query_tasks(assignee_id=None, sprint=None, department=None)
```

It builds an **`and`** of whichever filters you pass and runs it **server-side** (Notion
returns only matching rows; we never download the whole board). The three filter
clauses:

| Argument | Notion filter |
| --- | --- |
| `assignee_id` | `{"property": "Assignee", "people": {"contains": <user id>}}` |
| `sprint` | `Sprint == "Sprint{n}"` |
| `department` | `Department == <name>` |

The Sprint and Department clauses are built by **`_eq_filter`**, which picks the right
filter shape from the property's **type** — a `select`, a `status`, and a `rich_text`
each filter differently. Rather than hardcode "Sprint is a select", the code reads the
data source's schema once (`data_sources.retrieve`, cached in `_schema`) and adapts.
That makes the bot robust to whether `Sprint`/`Priority`/`Department` are configured as
select or text columns in Notion.

`_get_department_options()` reads that same schema to list the **valid department
names** (the select options), which `/sprinttasks` uses to reject typos.

## Reading every property — `_task_full`

Where the old code pulled three fields, `_task_full` extracts the whole task into a flat
dict, each value via a type-specific helper:

| Key | Notion property | Type | Helper |
| --- | --- | --- | --- |
| name | `Task name` | title | `_prop_title` |
| status | `Status` | status | `_prop_status` |
| assignee | `Assignee` | people | `_prop_people` |
| due | `Due date` | date | `_prop_date` |
| priority | `Priority` | select | `_prop_select` |
| department | `Department` | select | `_prop_select` |
| description | `Description` | rich text | `_prop_rich_text` |
| sprint | `Sprint` | select/text | `_prop_select` |
| updated | `Updated at` | last-edited-time | `_prop_timeish` |

The property **names** are constants at the top of `notion_api.py` (`PROP_NAME`,
`PROP_STATUS`, …). **Rename a column in Notion → change the matching constant**, in one
place. The names are matched literally; a mismatch yields empty results, not an error.

## The commands at a glance

- **`/tasks`** — your sprint tasks, numbered: `N. **Name** — Status — 📅 Due — Desc`
  (description truncated). Ephemeral.
- **`/taskdetail n`** — all nine properties of task *n* from that same list. Ephemeral.
- **`/sprinttasks`** — the whole sprint, public. With no argument it sorts by the fixed
  department order (`notion_api.DEPARTMENT_ORDER`: Production → Narrative → Design → Art
  → Engineering → QA → Audio; unknown departments last) and shows Name/Status/Assignee/
  Department. With a `department` argument it validates the name against the Notion
  options, then lists just that department.

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
- **Filter `/tasks` by status too** → add a `status` argument to `query_tasks` and a
  `_eq_filter(PROP_STATUS, …)` clause.
- **A "who's overloaded?" view** → `query_tasks(sprint=…)` returns every task with its
  assignee; group in Python.
- **Let people self-associate only** → gate `/associate` so `member` must equal
  `ctx.author` unless the caller is a lead. (Today anyone can bind anyone — a deliberate
  v1 choice.)
