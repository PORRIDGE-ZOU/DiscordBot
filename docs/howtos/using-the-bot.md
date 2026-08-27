# Using the bot — a guide for the team

This is for anyone on the QLP Discord server who wants to *use* the bot. No coding
needed. (If you're working on the bot's code instead, start with
`../summary/overview.md`.)

The bot appears in the server as **Sous Chef**. You talk to it with **slash commands**
— messages that start with `/`.

## How slash commands work

1. Click in the message box of any channel and type `/`.
2. A menu pops up. Start typing the command name (e.g. `tasks`) to filter it.
3. Pick the command. If it needs input (a member to pick, a sprint name, a task
   number), Discord shows a little field or picker — fill it in.
4. Press Enter.

Some replies everyone in the channel can see; some are **private** (only you see
them — Discord labels these "Only you can see this"). Each command below says which.

## The commands

### `/ping`
Checks the bot is awake. It replies `pong! 🏓`. If you ever wonder "is the bot even
online?", run this. *(Reply: public.)*

### `/notion_check`
Lists every Notion page and database the bot is currently able to read. Use it to
confirm the bot can see a page you just shared with it (see "Add a new Notion page"
below). If a page you expected is missing from the list, it hasn't been shared with
the bot yet.

It also reports **how it reads the task tracker** — which column it's using for the
assignee, the due date, the sprint and so on, plus anything it couldn't find. If
`/tasks` is showing the wrong thing after someone edited the Notion board, this is the
first command to run. *(Reply: private — only you see it.)*

### Link yourself first: `/associate`
Before the bot can show you *your* tasks, it needs to know which Notion person you
are. Run this **once**:

```
/associate person:<your Notion email or display name> member:@you
```

Pick yourself from the member list, and for `person` give either your Notion **email**
or your **display name exactly as it appears in the Assignee column** of the task
tracker. Name works even for **guest** accounts (which don't have a full workspace
membership) — so everyone on the team can be linked. The bot confirms privately. Change
Notion accounts later? Just run it again — it re-links. Anyone can run this for anyone,
so a lead can link the whole team.

### Set the sprint: `/setsprint` and `/sprint`
Set the **current sprint** by its **name in Notion** — `/setsprint label:Sprint 1`
(anyone can) — and check it with `/sprint` → *"We're in Sprint 1!"* (public).

You don't have to type it exactly: `Sprint 1`, `sprint1` and plain `1` all work. If you
type a sprint that doesn't exist, the bot refuses and lists the ones that do, so you
never end up silently filtering for nothing. If no sprint is set, the task commands
still work — they just show tasks across **all** sprints.

### `/tasks` — your tasks this sprint
Shows the tasks assigned to **you** in the current sprint, as a numbered list:

```
Your tasks — Sprint 1 (3):
1. Block out kitchen level — In progress — 📅 2026-06-18 — greybox the back-of-house
2. Fix dialogue camera — Not started — 📅 2026-06-20
3. Audio pass on plating SFX — Not started — 📅 2026-06-24
```

You must be `/associate`d first. *(Reply: private — only you see it.)*

### `/taskdetail` — one task in full
`/taskdetail 2` shows **every** column of task #2 from your `/tasks` list — status,
assignee, due date, priority, department, sprint, description, and whatever else the
board has (tags, submission link, approver, epic…). Add a column in Notion and it
appears here too. The number matches what `/tasks` showed. *(Reply: private.)*

### `/sprinttasks` — the whole sprint
Shows **everyone's** tasks in the current sprint, numbered and grouped by department —
in the same order the departments are listed in Notion:

```
Sprint 1 (12):
1. Block out kitchen level — In progress — 👤 George Zou — 🏷️ Design
...
```

Add a department to narrow it: `/sprinttasks department:Engineering`. An unknown
department name is rejected with the list of valid ones. *(Reply: public — handy for
standups.)*

### `/remind` — get a DM before your tasks are due
`/remind 3` sends you a **direct message 3 days before each of your current-sprint
tasks is due** — one DM per task. Tasks with no due date (or already within 3 days) are
skipped, and the bot tells you how many. Running it again **replaces** your previous
reminders. *(Reply: private.)*

> Two kinds of reminders: `/remind` is about **your tasks' due dates**. The
> `/remind_in` and `/remind_weekly` commands post to a **channel** on a clock you set —
> different tool, see `/help`.

### `/dm` — send a direct message
`/dm message:<text>` DMs the message to **you** and privately confirms it was sent —
handy for testing that the bot can reach you. Add `member:@someone` to DM them instead.
If their DMs are closed, the bot tells you it couldn't deliver. *(Reply: private.)*

## Add a new Notion page for the bot to read

The bot can only read Notion pages and databases that have been **shared with it**.
A brand-new page is invisible to the bot until you do this. You need edit access to
the page in Notion.

1. Open the page (or database) in Notion.
2. Click the **`•••`** menu in the top-right corner.
3. Choose **Connections** (you may need to scroll down the menu).
4. Find and add the bot's connection — it's named **Sous Chef** *(confirm the exact
   name with George if you don't see it)*.
5. Done. Sharing a page also shares everything nested **inside** it, so sharing a
   top-level page covers its sub-pages.

To confirm it worked, run **`/notion_check`** — the new page should appear in the
list.

> **Note:** the task tracker shown by `/tasks` is a specific, pre-configured
> database. Sharing a *different* task list with the bot doesn't automatically make
> `/tasks` read it — that needs a setup change. Ask George if you want the bot
> pointed at a different tracker.

## If you change the task board in Notion

Renaming a column is fine — the bot recognises the common names for each thing it
needs (`Assignee`/`Owner`, `Due date`/`Deadline`, `Sprints`/`Sprint`…) and otherwise
falls back to matching by column *type*. Adding a column is fine too; it just shows up
in `/taskdetail`.

Two things to know:

1. **Tell George to restart the bot** after any column change. It reads the board's
   structure once when it starts, so until it restarts it's still working from the old
   one.
2. **A column that links to another database** (like `Sprints`) only works if that
   other database is *also* shared with the bot — sharing the task tracker doesn't
   cover it. Sprints showing as "1 linked" instead of "Sprint 1" is the tell.

Run `/notion_check` afterwards to see exactly what the bot picked up.

## Getting help

- Bot not responding at all? Run `/ping`. No reply usually means the bot is offline
  — ping George.
- A command missing from the `/` menu? It may be newly added and not synced to your
  client yet — fully reload Discord (Ctrl/Cmd+R) and try again.
- Anything else, ask in the team channel or message George.

---

*This guide grows as the bot gains features. Meeting recording and transcription are
planned — they'll be documented here when they land.*
