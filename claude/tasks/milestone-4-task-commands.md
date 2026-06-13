# Milestone 4 — Task Commands Spec

Status: APPROVED design (2026-06-13). Not yet built. Personal task querying,
sprint management, per-task reminders. The bot binds each Discord user to a Notion
person, then filters the Task Tracker by that person and the current sprint.

## Data model

**Notion stays read-only.** The bot never writes to Notion. All bot state lives in
a local SQLite store (`botstate.db`) on the bot host, alongside `jobs.sqlite`. New
module `store.py`.

- `associations` — one row per bound user:
  `discord_id` (PK) · `notion_user_id` · `notion_name` · `email` · `bound_at`.
  Binding is 1:1 both directions (one Discord user <-> one Notion email).
- `config` — key/value: `current_sprint` = `"2"`, etc.

**Notion Task Tracker schema** (confirm exact property names + types before build):
`Task name` (title) · `Status` (status: Done / Not started / In progress) ·
`Assignee` (people) · `Due date` (date) · `Priority` (?select) ·
`Department` (?select) · `Description` (?rich text) ·
`Sprint` (?select or text, value `"Sprint{x}"`) · `Updated at` (?last-edited-time).

**Deterministic numbering.** Personal lists (`/tasks`, `/taskdetail`, `/remind`)
share one query + sort so "task 3" means the same task across all three: sort by
Due date ascending (no-due-date last), tiebreak by Task name. Sprint lists
(`/sprinttasks`) sort by fixed department order, then Task name.

## Commands

### /associate [email] [member]
- Who: anyone.
- `member` is a Discord user-picker (not free text) — guarantees a real server
  member + stable user ID.
- Validate: (a) member in this server (picker guarantees); (b) `email` exists in the
  Notion workspace user list (`users.list`). Email not found -> do nothing, error:
  "`email` isn't a member of the Notion workspace."
- Action: resolve email -> Notion user id + name; upsert into `associations`.
  Enforce 1:1 — if this Discord user OR this email was already bound, overwrite and
  say so explicitly: "This email was already bound to @X! Re-bound it to @Y."
- Output (ephemeral): success / explicit rebind / error.

### /tasks
- Who: anyone bound. Unbound -> ephemeral "You're not linked yet — run /associate
  first." and nothing else.
- Reads: caller's `notion_user_id` + `current_sprint` (local DB). No sprint set ->
  "No sprint set — run /setsprint."
- Query: Assignee contains caller AND Sprint == current. Shared sort.
- Output (ephemeral, personal): numbered list, one task/line:
  `N. Task Name — Status — Due — Description` (description truncated).
  Empty -> "No tasks assigned to you in Sprint X."

### /taskdetail #
- Who: anyone bound (same unbound message).
- Same query + sort as /tasks, pick item #. Out of range -> error.
- Output (ephemeral): all properties — Task Name, Status, Assignee, Due Date,
  Priority, Department, Description, Sprint, Updated At.

### /setsprint x
- Who: anyone.
- Validate `x` positive integer. Write `current_sprint = x` to local DB. No check
  that SprintX tasks exist (sprint can be set before tagging).
- Output: "Current sprint set to Sprint X." (success/failure + number).

### /sprint
- Who: anyone. Reads `current_sprint`.
- Output: "We're in Sprint X!" Unset -> "No sprint set yet."

### /sprinttasks [department?]
- Who: anyone. Reads `current_sprint`, queries all tasks in that sprint.
- No department arg: order by fixed sequence Production > Narrative > Design > Art >
  Engineering > QA > Audio (unknown/empty department appended at end), numbered.
  Show Task Name, Status, Assignee, Department.
- With department arg: validate against the Notion Department select options
  (auto-current). Invalid -> error listing valid departments. Filter, numbered,
  show Task Name, Status, Assignee.
- Output (PUBLIC): header states the explicit sprint number.

### /remind x
- Who: anyone bound (same unbound message).
- Meaning: for EACH of the caller's current-sprint tasks with a due date, schedule
  ONE DM sent x days before that task's due date. 3 tasks, 3 due dates -> 3 DMs.
- Edge cases:
  - Task with no due date -> skipped (counted).
  - `due - x days` already past -> skipped (counted).
  - Re-running /remind clears the caller's existing task-reminders first, then
    reschedules fresh (no duplicate stacking).
  - Task properties snapshotted at schedule time (DM may be stale if task later
    changes).
- Delivery: persistent APScheduler job -> DM via the bot. New module-level
  `_send_dm` in `scheduler.py`.
- DM content: task name + due date + status + "Reminder: '<task>' is due on <date>
  (in x days)." (exact wording = George's.)
- Output (ephemeral): "Scheduled N reminders, x days before each due date. Skipped M
  (no due date / already past)."

## Removed
- Old `/tasks status:<choice>` (status dropdown) is KILLED entirely. Name reused for
  personal tasks. `/sprinttasks` covers team-wide views.

## Build prerequisites
1. Confirm Notion Task Tracker exact property names + types (above). Sprint's type
   drives the filter syntax.
2. Notion integration needs "read user information" capability for `users.list`
   (the /associate email check). Confirm in portal.
3. New code: `store.py` (SQLite via stdlib sqlite3); extend `notion_api.py`
   (workspace users, generalized task query, full property extraction); extend
   `scheduler.py` (DM reminders). No new pip deps.

## Locked decisions
- State storage: local SQLite (`botstate.db`), Notion read-only.
- /associate, /setsprint: anyone can run.
- /associate member arg = user-picker; 1:1 binding, explicit rebind message.
- /remind = single arg x; per-task DMs x days before each due date; skip no-due +
  past; replace-on-rerun; snapshot props.
- Department validity = Notion select options.
- Visibility: /tasks, /taskdetail ephemeral; /sprint, /sprinttasks public.
