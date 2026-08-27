# Documentation index

Human-facing explanation of the Quarter Life Pounder bot. For setup/run steps see
the root `README.md`; this folder is the "how does it work and why" layer.

Each entry below says *why future-you would open it*.

## Start here
- **[summary/overview.md](summary/overview.md)** — what the bot is, the current vs.
  planned features, how the code is laid out, and how to run it. Read this first.

## How-tos (for people *using* the bot, no coding)
- **[howtos/using-the-bot.md](howtos/using-the-bot.md)** — onboarding for a server
  member: every command and how to use it, and how to share a new Notion page with
  the bot. Share this with the team.
- **[howtos/deploying-on-ec2.md](howtos/deploying-on-ec2.md)** — how the bot is
  hosted on EC2 (systemd, swap, the scraper coexistence) and the day-to-day
  operate/update commands. Open to restart it, push a code change, or read logs.

## Explainers (the tech the bot depends on)
- **[explainers/discord-bot-basics.md](explainers/discord-bot-basics.md)** — gateway,
  intents, slash commands, the 3-second interaction rule, command registration,
  guild vs. global. Open when a command "isn't working" or before adding one.
- **[explainers/notion-integration-model.md](explainers/notion-integration-model.md)** —
  connections + the sharing gate, `search`, the 2025 data-source model, and why a
  relation filters by page id. Open before touching anything that reads Notion.
- **[explainers/schema-driven-notion-columns.md](explainers/schema-driven-notion-columns.md)** —
  how the bot reads a task database it has never seen: roles resolved against the live
  schema instead of hardcoded column names, crucial-vs-optional properties, relation
  indexing, and the restart rule. Open before changing `notion_api.py`, or when a
  Notion column gets renamed or retyped.

## Deep dives (how a feature actually works)
- **[deep-dives/notion-task-queries.md](deep-dives/notion-task-queries.md)** — the
  sprint + personal task commands end to end (`/associate`, `/tasks`, `/taskdetail`,
  `/setsprint`, `/sprint`, `/sprinttasks`, `/remind`): the Discord↔Notion association,
  the sprint filter, the shared numbering, and the per-task reminders. Open before
  changing task querying.

## Bugs (post-mortems)
- **[bugs/2026-05-30-databases-query-removed.md](bugs/2026-05-30-databases-query-removed.md)** —
  the Notion `databases.query` removal and the data-source fix. Open if a Notion
  query suddenly `AttributeError`s.
- **[bugs/2026-07-10-notion-workspace-migration.md](bugs/2026-07-10-notion-workspace-migration.md)** —
  what broke moving to a new workspace: page-vs-database id, guests not in
  `users.list`, missing `Sprint` column. Open when re-pointing the bot at a new
  workspace or DB. The follow-up move (a column renamed *and* retyped) is what drove
  the schema-driven design in the explainer above.

---

*Convention: after building or changing a feature, add/refresh the relevant
deep-dive; after fixing something that broke, add a `bugs/` post-mortem; after
working out a new piece of Discord/Notion/Whisper tech, add an explainer — and
update this index.*
