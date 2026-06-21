# Session Log

## 2026-05-30 — Session 1 (project kickoff)

**Done**
- Read AGENTS.md (governing doc). Internalized behavioral override: propose→wait→
  execute for all project files; no git/gh/CI ever; `claude/` auto-writable,
  everything else needs approval; teach the Discord/Whisper/Notion layer; no
  surprises to real people; recording path sacred + decoupled from transcription.
- Walked George through Discord vocabulary (guild=server, scopes vs permissions,
  intents, token, gateway, slash commands) and Developer Portal steps (create app,
  get token, enable Message Content + Server Members intents, OAuth2 invite URL).
- Settled transcription engine: **faster-whisper large-v3 local** (quality pick).
  Logged: decisions/2026-05-30-whisper-engine.md.
- Created claude/ and docs/ folder skeletons (George authorized).

**Decided**
- Stack confirmed: Python + Pycord. Transcription = faster-whisper large-v3 local.

**Next**
- Milestone 1: bot comes online + responds to a slash command (hello-world).
  Prereq: George finishes portal (token + intents + invite). Then propose minimal
  bot.py + requirements.txt + .env.example, wait for approval before writing.

**Blocked / open**
- GPU vs CPU for Whisper (open-questions.md). Only blocks the transcription feature,
  not milestone 1.
- A correction mid-turn: early in the session Claude ran `python3 -m venv` /
  started scaffolding before approval — George interrupted. Corrected; no project
  files written or commands run without approval since.

## 2026-05-30 — Session 1 (cont.) — Milestone 1 + 2 shipped

**Done**
- Milestone 1: `/ping` live in server (bot = "Sous Chef", originally "Aboyeur").
  Confirmed working.
- Milestone 2 (Notion): connection created + page/DB shared. `/notion_check`
  (search, ephemeral) working — sees 5 items incl. "Test Tasks Tracker".
- `/tasks status:<choice>` built: single dropdown (Done/In progress/Not started/
  Pivoted/Active), public reply, name+assignee+due. Server-side status filter,
  Active = In progress OR Not started.
- Hit + fixed the Notion 2025 data-source change (`databases.query` removed ->
  `data_sources.query` against resolved+cached data source id). gotchas.md logged.
- NOTION_TASKS_DB_ID = 370d09833ea080ef858bc3f843aeccaf (George set in .env).

**Decided**
- Behavior (George): single /tasks dropdown; "Active" label; public; name+assignee+due.

**Docs**
- Wrote full docs/ set (summary, explainers, deep-dive, bug postmortem) + docs/README
  index. Updated claude/ architecture, conventions, gotchas, tasks.

**Next**
- George to confirm /tasks returns correct rows after restart.
- Then: pick next feature.

## 2026-05-30 — Session 1 (cont.) — Hosting on EC2

**Done**
- Bot now hosted 24/7 on existing AWS EC2 (Amazon Linux 2023, t3.micro, us-east-2,
  IP 3.151.10.101, user ec2-user, python3.11). Confirmed online + /ping works with
  laptop SSH closed. Bot = Sous Chef (originally Aboyeur#6219, id 1510367962115215430).
- systemd service `qlpbot` (Restart=always, enable --now). 2 GB swap added (was 0).
  Coexists with the Steam scraper job on the box.
- Deploy loop: rsync from Mac (exclude venv/.env/.git/__pycache__/.DS_Store) ->
  systemctl restart qlpbot.
- Wrote docs/howtos/deploying-on-ec2.md + index entry. Logged
  decisions/2026-05-30-hosting-ec2.md. Hosting open-question resolved.

**Decided** (George)
- Host on existing EC2, not Oracle (already provisioned, $0 marginal). See decision.

**Watch (open-questions.md)**
- EC2 disk (8 GB shared w/ scraper, ~47%) + RAM (1 GB shared, swap-cushioned).
- Whisper still off-box; GPU/CPU question still open.

**Reminders for next session**
- ONE token = ONE instance. Never run bot locally while EC2 serves (double replies).
- Code change workflow = rsync + restart; slash command changes need the restart.

**Next**
- Pick next feature: scheduled messaging (feat 1), Notion page reading (/notion_read),
  or "my tasks" (needs Discord-user -> Notion-assignee map).

## 2026-05-30 — Session 1 (cont.) — Reminders + GitHub deploy

**Done (code, awaiting George's deploy+test)**
- Built 3 features: /intro (public blurb), /help (auto-generated from registered
  commands, ephemeral), and scheduled messaging.
- Reminders: /remind_in (one-shot, hours-from-now), /remind_weekly (cron, California
  tz via zoneinfo), /reminders (list), /reminder_cancel (by id). All anyone-can-use,
  confirmations ephemeral. Permission check before scheduling.
- scheduler.py: APScheduler (pinned <4) + SQLAlchemy SQLite jobstore -> reminders
  survive restarts. _send_message is module-level (persistent jobs need a ref, not a
  closure). setup(bot) called in on_ready (loop running + reloads saved jobs).
- requirements: +apscheduler<4, +SQLAlchemy. .gitignore: +jobs.sqlite. Compiles clean.

**Behavior (George)**
- anyone can schedule; include /reminders + /reminder_cancel; intro public + help
  private; names /remind_in + /remind_weekly. Intro draft text used (his to edit).

**Deploy switched to GitHub** (decision logged)
- Mac: git push. EC2: ./deploy.sh (git pull -> pip install -> restart). PAT auth via
  credential store. rsync retired. Wrote deploy.sh + updated deploy doc.

**Watch**
- jobs.sqlite = live server state, untracked (git-safe). _send_message ref path: it
  lives in scheduler.py (stable module path) so persistent jobs reload fine.
- Reminders NOT yet tested live. Need George to deploy + run the test plan (incl the
  restart-persistence test). THEN write reminders feature docs (deep-dive + README +
  /help howto) — held until confirmed working.

**Next**
- George: .env-history security check -> push -> EC2 git sync -> pip install -> test
  /intro /help /remind_* + persistence-across-restart test.
- After confirmed: reminders deep-dive doc + README/howto command-table updates.

## 2026-05-30 — Session 1 (cont.) — Milestone 3 PLANNING (transcription)

**Planned (no code)** — claude/tasks/milestone-3-transcription.md
- Surfaced 2 reframes: (1) EC2 can't record (Pycord sink buffers whole meeting in
  RAM -> OOM on 1GB; disk too small; no GPU). (2) M4 Mac reopens engine — faster-
  whisper is CPU-only on Mac; mlx-whisper GPU-accelerates large-v3.

**Decided (George)** — decisions/2026-05-30-meeting-bot-and-engine.md
- Dedicated meeting bot = 2nd Discord app/token on M4, online during meetings only.
  Ops bot (EC2) unchanged.
- Transcription async/decoupled: save audio+metadata first (guaranteed), transcribe
  later (retry-safe).
- Engine: faster-whisper, large-v3, full precision (fp16), LOCAL, CROSS-PLATFORM
  (George has TWO laptops, uses either: M4 Mac + Windows RTX 5070). CUDA on the 5070
  (fast, fp16 ~5GB fits 8GB), CPU on Mac (slower, full quality). mlx considered but
  dropped (Mac-only). Privacy > cloud ceiling. GPU/CPU open-question resolved.
  Blackwell (50-series) needs recent CUDA12/cuDNN9 + latest CTranslate2.
- Meeting bot = ONE portable codebase, run on whichever laptop present; record +
  transcribe co-located (no transfer).

**Still open (pinned by George)**
- Storage/delivery of big audio (Discord ~10MB upload cap) — deferred.
- Consent wording + transcript format — decide at build time.

**Next**
- George confirms the 2nd-bot recording host, then BUILD STAGE 1 = recording only
  (/record start|stop, consent notice, guaranteed per-user audio save). Test that
  audio is ALWAYS produced before layering transcription. Then Stage 2 = mlx-whisper
  transcription pass over saved audio.

## 2026-06-13 — Session 2 — Milestone 4 task commands (BUILT, untested live)

**Designed + approved** (claude/tasks/milestone-4-task-commands.md; George mirrored
into the team Google Doc). Decisions George locked:
- State (associations + current sprint) in a LOCAL SQLite (botstate.db), Notion
  stays READ-ONLY. "Central Info page" reinterpreted = our own DB.
- /associate, /setsprint: anyone can run. /associate uses a Member PICKER, stores
  Discord user ID (not username), 1:1 binding both ways, explicit rebind message.
- /remind = single arg x: one DM per task, x days before each task's due date.
  Skip no-due + already-past; re-run replaces the user's batch; snapshot task text.
- Dept validity = Notion select options. Visibility: /tasks /taskdetail ephemeral;
  /sprint /sprinttasks public. OLD /tasks status-dropdown KILLED.

**Built (code, awaiting George deploy+test)**
- NEW store.py: SQLite (associations, config). stdlib sqlite3, no new dep.
- notion_api.py: list_workspace_users / find_user_by_email (users.list); schema
  introspection via data_sources.retrieve (cached) -> type-aware _eq_filter +
  get_department_options; generalized query_tasks(assignee_id, sprint, department);
  _task_full full-property extractor. Removed old ACTIVE_STATUSES/query_tasks_by_status.
- scheduler.py: per-task DM reminders (_send_task_dm, schedule_task_reminder,
  clear_task_reminders), namespaced job ids "taskremind:<discord_id>:<i>"; list_jobs
  now excludes them so /reminders stays channel-only.
- bot.py: removed old /tasks; added /associate /tasks /taskdetail /setsprint /sprint
  /sprinttasks /remind. on_ready calls store.init(). INTRO_TEXT refreshed.
- .gitignore: +botstate.db (live state, like jobs.sqlite).
- All four modules py_compile clean.

**MUST VERIFY before it works live (build prereqs, can't confirm without the token)**
- Exact Notion Task Tracker property NAMES match the constants in notion_api.py
  (PROP_* — Task name/Status/Assignee/Due date/Priority/Department/Description/
  Sprint/Updated at). Sprint/Priority/Department types handled generically.
- Sprint values are literally "Sprint1","Sprint2"... (filter builds f"Sprint{n}").
- Notion integration has "read user information" capability (users.list) for
  /associate email check.

**Next**
- George: deploy (git push -> EC2 ./deploy.sh), then test each command. Verify
  property names against the real DB first. After confirmed working: write
  docs/deep-dive + README command-table update (held for approval).
