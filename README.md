# Quarter Life Pounder Discord Bot

A custom Discord bot for the QLP (USC Games AGP) team's game-dev workflow.

**Planned features** (built one at a time):
1. Scheduled messaging — timed/recurring messages to channels and member DMs.
2. Meeting recording — join voice, record each meeting, always produce an audio file.
3. Transcription — bilingual EN/ZH transcripts (faster-whisper, large-v3, local).
4. Notion reading — read any page from the team workspace.
5. Notion task queries — "what are the ongoing tasks?", "what are *my* tasks?"

**Current status:** online 24/7 on EC2. Working: liveness, Notion connectivity,
sprint + personal task queries, and reminders. Recording/transcription are still
planned.

---

## Setup

### 1. Create the Discord application + bot
1. https://discord.com/developers/applications → **New Application**, name it.
2. **Bot** (left sidebar) → **Reset Token** → copy the token. This is the bot's
   password — keep it secret, it goes in `.env`, never in code or git.
3. On the same **Bot** page, enable these **Privileged Gateway Intents**:
   - **Message Content Intent**
   - **Server Members Intent**

### 2. Invite the bot to the server
1. **OAuth2 → URL Generator**.
2. Scopes: `bot`, `applications.commands`.
3. Bot Permissions: `Send Messages`, `Read Message History`
   (voice permissions get added when the recording feature lands).
4. Open the generated URL → pick the QLP server → authorize.

### 3. Configure secrets
```bash
cp .env.example .env
```
Edit `.env` and paste your real `DISCORD_TOKEN`. Optionally set `DISCORD_GUILD_ID`
(your server ID) so slash commands appear instantly during development — see the
comments in `.env.example` for how to get it.

### Notion connection (for the Notion features)
1. https://www.notion.so/my-integrations → **+ New connection** → name it, pick the
   workspace, type **Internal** → create.
2. Copy the **Internal Integration Secret** (`ntn_...`) into `.env` as `NOTION_TOKEN`.
3. **Share pages with it** (required — the connection sees nothing otherwise): open
   the team's top page (and the task database) → `•••` → **Connections** → add the
   connection. Sharing a page cascades to its child pages.
4. **Enable "Read user information"** on the connection (Configuration → Capabilities).
   `/associate` needs it to look up workspace members by email. Without it, that
   command can't validate emails.

### 4. Install dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Running

```bash
source venv/bin/activate   # if not already active
python bot.py
```

You should see `Logged in as ...` and the bot's status go online in the server.
In any channel, type `/ping` → the bot replies `pong 🏓`.

The bot is a **long-lived process**: it stays online only while `python bot.py`
is running. Closing the terminal (or the laptop) takes it offline. Always-on
hosting (a small VPS or Pi) comes later.

---

## Commands

Visibility: **public** = the whole channel sees it; **private** = only the invoker
("Only you can see this").

| Command | What it does | Visibility |
|---------|--------------|------------|
| `/ping` | Replies `pong! 🏓`. Confirms the bot is alive. | public |
| `/notion_check` | Lists the Notion pages/databases the connection can see, **plus how the bot reads the task database** — which column fills each role it needs, anything it couldn't find, and every column with its type. First stop when a task command misbehaves. | private |
| `/intro` | Posts a short blurb of what the bot can do. | public |
| `/help` | Lists every command and its description (auto-generated). | private |
| `/associate person:<email or name> member:<@user>` | Links a Notion person to a Discord member, so that member's `/tasks` shows their tasks. Matches by email **or** display name, across workspace members **and** task assignees — so **guests** work too. 1:1 — re-running re-binds. Anyone can run it. | private |
| `/tasks` | Your own tasks, numbered. Scoped to the current sprint if one is set (otherwise all sprints). Needs you to be `/associate`d. | private |
| `/taskdetail number:<n>` | **Every** property of one of your tasks, by its number from `/tasks` — including columns added to Notion after the bot was written. | private |
| `/setsprint label:<name>` | Sets the team's current sprint by its **name in Notion** (e.g. `Sprint 1`). Matched loosely — `Sprint 1`, `sprint1` and `1` all work — and validated against the sprints that actually exist. Anyone can run it. | private |
| `/sprint` | Reports the current sprint. | public |
| `/sprinttasks [department:<name>]` | All tasks in the current sprint (or all sprints if none set), grouped by department — or just one department if given. | public |
| `/remind x:<days>` | DMs you `x` days before **each** of your tasks is due. Re-running replaces your previous batch. | private |
| `/dm message:<…> [member:<@user>]` | Sends a DM (to yourself if no member given) and confirms privately whether it went through. | private |
| `/remind_in`, `/remind_weekly`, `/reminders`, `/reminder_cancel` | Channel reminders: one-shot, weekly (California time), list, cancel. | private |

The Notion-backed commands need `NOTION_TASKS_DB_ID` set to the **database** id (the
32-hex chunk before `?v=` in the database's URL — not a `/p/` page link). Associations
and the current sprint are stored locally in `botstate.db` (gitignored, like
`jobs.sqlite`).

### What the task database must contain

The bot does **not** require specific column names. It resolves what it needs against
your database's live schema — first by name (a set of accepted aliases per role), then
by property **type**. Rename `Sprint` to `Sprints`, or `Assignee` to `Owner`, and it
keeps working.

| The bot needs | Accepted names (any case/spacing) | Or any column of type |
| --- | --- | --- |
| **task name** *(required)* | — | `title` |
| **assignee** *(required)* | Assignee, Assignees, Owner, Assigned to | `people` |
| status | Status, State, Progress | `status` |
| due date | Due date, Due, Deadline, End date | `date` |
| sprint | Sprints, Sprint, Iteration, Cycle | any |
| department | Department, Dept, Team, Discipline | `select` / `multi_select` |
| priority | Priority, Importance | — |
| description | Description, Notes, Details, Summary | — |
| last updated | Updated at, Last edited | `last_edited_time` |

Only **task name** and **assignee** are required — without them there's nothing to
show and no way to tell whose task it is, and the task commands say so by name. Every
other row is optional: a database with no sprint column simply shows all tasks, and a
missing field is left out of the display rather than erroring.

Run **`/notion_check`** after any Notion schema change to see exactly which column the
bot picked for each role.

> **If your sprint column is a relation** (it links to a separate Sprints database
> rather than being a Select), that Sprints database must be **shared with the
> connection too**. Sharing the task database does *not* cascade to a database it
> merely links to. Same for any other relation column you want shown by name.

> The schema is read **once per process** — restart the bot after adding, renaming or
> retyping a Notion column.
