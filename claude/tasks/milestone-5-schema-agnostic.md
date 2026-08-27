# Milestone 5 — Schema-agnostic Notion layer (new "Master Task List" workspace)

**Approved by George 2026-08-26.** Triggered by the second Notion workspace move:
the new DB "Master Task List" renamed `Sprint` -> `Sprints` AND changed its type
from select to **relation**, with values `Sprint 1` (space) instead of `Sprint1`.
Three breakages from one column. Fix the class of problem, not the instance.

## Goal
The bot works against ANY task database that carries a few crucial properties,
resolving columns by ROLE (alias + type) against the live schema instead of
hardcoded names, and building each filter from the type Notion reports.

## New DB columns (read off George's screenshots)
Task name (title) · Assignee (people) · Department (select) · **Sprints (relation)**
· Status (status) · Epic (relation) · Description (text) · Priority (select) ·
Due date (date) · Attach file (files) · Updated at (last_edited_time) · File Name ·
Submission Link (url) · Tag(s) (multi_select) · Approval By (people) · Place ·
Projects (relation)

## Design (approved)
- **A. Role resolution.** `PROP_*` constants -> role table (aliases + acceptable
  types), resolved once against the cached schema, cached in `_roles`.
  Two passes: alias match first for every role, then type fallback over columns
  not already claimed. `name` = whichever property has `type == "title"`.
- **B. Crucial roles = `name` + `assignee`.** Missing -> `MissingPropertyError`
  naming the role and the aliases tried (George: hard error naming it). Every
  other role optional: filter skipped, display line dropped.
- **C. Relation support.** `_eq_filter` gains a relation branch: read
  `relation.data_source_id` from the schema, query that data source ONCE, cache
  `{normalized title -> page id}` + `{page id -> title}`. Filter by id, display by
  reverse lookup. No N+1.
- **D. Loose sprint matching.** Normalize to lowercase-alphanumeric so
  `Sprint 1` / `Sprint1` / `sprint-1` collapse to `sprint1`. Bare numbers also try
  `sprintN`, so an old int in botstate.db still resolves.
- **E. Department order from the schema's select-option order.** Hardcoded
  `DEPARTMENT_ORDER` deleted.
- **F. Generic extraction.** `_prop_value` dispatches on type (title, rich_text,
  select, multi_select, status, people, date, checkbox, number, url, email,
  phone, files, relation, formula, rollup, created/last_edited time+by, unique_id).

## Behavior decisions (George, 2026-08-26)
1. `/taskdetail` shows **ALL** properties present in the DB (roles first in a fixed
   order, then the rest in schema order). Empty ones print `—`.
2. `/setsprint` takes a **text label** (`label:`), not an int. Validated against the
   real sprint options; unknown -> error listing them.
3. Missing crucial property -> **hard error naming the column**.
4. `/notion_check` **extended** with the resolved role->column map, the missing
   roles, and every column with its type.

## Files
- `notion_api.py` — bulk of the change (roles, relation index, generic extractors,
  sprint helpers, `describe_schema`).
- `bot.py` — `/setsprint` (label), `/sprint`, `/tasks` scope text, `/taskdetail`
  (all props), `/sprinttasks` (schema dept order), `_load_personal_tasks`
  (MissingPropertyError), `/notion_check` (extended).
- `store.py` — current sprint stored as TEXT, not int.

## Out of scope / untouched
scheduler.py, the gateway wiring, `_load_personal_tasks`'s single-loader +
`_personal_sorted` invariant (task numbers must stay consistent across /tasks,
/taskdetail, /remind).

## Notion-side prereq for George
The **Sprints database must also be shared with the connection**, not just Master
Task List — relation resolution reads it. If unshared, sprint filtering degrades to
all-sprints with a clear message.

## Status
- [x] Plan approved
- [x] notion_api.py rewritten
- [x] bot.py updated
- [x] store.py sprint as text
- [x] py_compile clean
- [ ] Live test on the new workspace (George)
- [x] Docs updated (George approved 2026-08-26): README (command table + a "what the
      task database must contain" role table + relation-sharing note), deep-dive
      (sprint-as-label, relations, roles-not-names, schema-driven filters, generic
      extraction), notion-integration-model (relation sharing doesn't cascade,
      relations filter by page id, schema as the load-bearing call), using-the-bot
      (/setsprint label, /taskdetail all columns, "if you change the task board"),
      overview, docs index, and the 2026-07-10 post-mortem's obsolete advice.
- [x] NEW docs/explainers/schema-driven-notion-columns.md — the teaching artifact
      (three-way breakage table, roles, claimed-column rule, required-vs-optional
      rationale, relation indexing, restart rule, how to extend).
