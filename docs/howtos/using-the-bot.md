# Using the bot — a guide for the team

This is for anyone on the QLP Discord server who wants to *use* the bot. No coding
needed. (If you're working on the bot's code instead, start with
`../summary/overview.md`.)

The bot appears in the server as **Aboyeur**. You talk to it with **slash commands**
— messages that start with `/`.

## How slash commands work

1. Click in the message box of any channel and type `/`.
2. A menu pops up. Start typing the command name (e.g. `tasks`) to filter it.
3. Pick the command. If it needs a choice (like which task status), Discord shows a
   little dropdown or field — fill it in.
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
the bot yet. *(Reply: private — only you see it.)*

### `/tasks`
Shows tasks from the team's Notion task tracker, filtered by status. After you pick
`/tasks`, choose a **status** from the dropdown:

| Choice | Shows |
| --- | --- |
| **Done** | Finished tasks |
| **In progress** | Tasks being worked on right now |
| **Not started** | Tasks not begun yet |
| **Pivoted** | Tasks that were dropped or changed direction |
| **Active** | Everything still on the table — *In progress* **and** *Not started* together (i.e. not Done, not Pivoted) |

The reply lists each matching task with its assignee and due date, e.g.:

```
Tasks — Active (2):
- Update help center & FAQ · 👤 imglebasi · 📅 2025-02-20
- Publish release notes · 👤 George Zou · 📅 2025-02-28
```

*(Reply: public — the whole channel sees it, handy for standups.)*

> **Tip:** "What's left to do?" → `/tasks` → **Active**. "What did we finish?" →
> **Done**.

## Add a new Notion page for the bot to read

The bot can only read Notion pages and databases that have been **shared with it**.
A brand-new page is invisible to the bot until you do this. You need edit access to
the page in Notion.

1. Open the page (or database) in Notion.
2. Click the **`•••`** menu in the top-right corner.
3. Choose **Connections** (you may need to scroll down the menu).
4. Find and add the bot's connection — it's named **Aboyeur** *(confirm the exact
   name with George if you don't see it)*.
5. Done. Sharing a page also shares everything nested **inside** it, so sharing a
   top-level page covers its sub-pages.

To confirm it worked, run **`/notion_check`** — the new page should appear in the
list.

> **Note:** the task tracker shown by `/tasks` is a specific, pre-configured
> database. Sharing a *different* task list with the bot doesn't automatically make
> `/tasks` read it — that needs a setup change. Ask George if you want the bot
> pointed at a different tracker.

## Getting help

- Bot not responding at all? Run `/ping`. No reply usually means the bot is offline
  — ping George.
- A command missing from the `/` menu? It may be newly added and not synced to your
  client yet — fully reload Discord (Ctrl/Cmd+R) and try again.
- Anything else, ask in the team channel or message George.

---

*This guide grows as the bot gains features. Recording, transcription, and
scheduled reminders are planned — they'll be documented here when they land.*
