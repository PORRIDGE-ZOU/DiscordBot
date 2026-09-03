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

## 2026-07-10 — Session 3 — deploy, rename, new-workspace migration, guest fix

**Shipped + confirmed working live on EC2.**

- Bot RENAMED Aboyeur -> **Sous Chef** (George did the portal side). All active
  refs updated (INTRO_TEXT, docs, claude notes). Kept "originally Aboyeur" history.
- Added `/dm message [member]` — DMs self by default (or a member), always ephemeral
  confirmation to sender; catches discord.Forbidden (DMs off).
- Deployed Milestone 4 via GitHub. Ops gotchas hit + doc'd: deploy.sh needed
  chmod +x / `bash deploy.sh`; EC2 main had no upstream (`git branch
  --set-upstream-to=origin/main main`); ssh needs `-i <steam_key.pem>`.
- NEW NOTION WORKSPACE migration (old one abandoned). New connection "QLP Bot"
  (Access token), new DB "Master Tasks Tracker"
  id=39770e5485b780d69ed8e41939eb8e69 (was given a /p/ PAGE id first -> "is a page
  not a database"; real id is the chunk before ?v=).

**Bugs found + fixed (all live-confirmed)**
- `/tasks` hung: missing Sprint col + uncaught Notion error. Fix: try/except in
  `_load_personal_tasks` (reports error, no hang) + Sprint filter OPTIONAL
  (`query_tasks` applies it only if sprint set AND PROP_SPRINT in cached schema).
  Sprint-less -> shows all sprints, headers say "all sprints"/"All tasks".
- `/associate` failed for teammates: they're Notion GUESTS (cost), and `users.list`
  returns MEMBERS ONLY. Fix: `/associate` arg renamed email -> `person` (email OR
  display name); new `find_notion_person` searches members + `list_task_assignees`
  (harvests assignees from task rows, guests included). Guests often no email ->
  match by display name. Store keys on email-or-name.

**Docs updated (George approved "update the docs")**
- README (command table, DB-id note, guest note), docs/summary/overview,
  deep-dives/notion-task-queries (associate/guests + sprint-optional + error
  handling), explainers/notion-integration-model (members-vs-guests, page-vs-db id),
  howtos/using-the-bot (associate by name, /dm, sprint optional), docs/README index.
- NEW bugs/2026-07-10-notion-workspace-migration.md postmortem.

**Reminders for next session**
- Schema is cached per process -> RESTART after any Notion column/DB change.
- Sprint Select options must be named exactly Sprint1/Sprint2... to match f"Sprint{n}".
- botstate.db associations key on Notion user id from the CURRENT workspace; a
  workspace switch invalidates old bindings -> everyone re-runs /associate.

**Still untested live**: `/remind` (per-task DM timing), `/taskdetail`, `/sprinttasks`
department validation. `/tasks` + `/associate` confirmed working.

**Next candidates**: Perforce reporting (discussed — gated on EC2 reachability to the
P4 server); Milestone 3 recording; test the remaining task commands.

## 2026-08-26 — Session 4 — schema-agnostic Notion layer (2nd workspace move)

**Trigger**: team moved to a new workspace again; new DB "Master Task List".
`Sprint` -> `Sprints` (renamed), select -> **relation** (retyped), `Sprint1` ->
`Sprint 1` (revalued). One column, three independent breakages, only one of them loud.

**George approved the plan + all four behavior calls** (claude/tasks/milestone-5-
schema-agnostic.md): /taskdetail shows ALL properties; /setsprint takes a TEXT
LABEL not an int; missing crucial column = hard error naming it; /notion_check
extended with the schema map.

**Built**
- notion_api.py: PROP_* constants and DEPARTMENT_ORDER DELETED. New role layer —
  ROLE_ALIASES + ROLE_FALLBACK_TYPES + resolve_roles() (alias pass, then type pass
  over unclaimed columns), REQUIRED_ROLES = (name, assignee), MissingPropertyError,
  require_role/check_required, describe_schema(). Relation support:
  _relation_data_source + _relation_index (one query, cached both directions),
  relation branch in _eq_filter (filters on page id). get_options(role) covers
  select/multi_select/status/relation; match_sprint() loose-matches via _norm().
  query_tasks normalises the stored sprint label before filtering. _prop_value()
  replaces the six _prop_* extractors — dispatches every Notion type incl. url,
  files, formula, rollup, unique_id; unknown type -> "" (can't break a command).
  _task_full gained "all" = every column, roles first then schema order.
- bot.py: /setsprint label:str (validated, unknown -> lists real options);
  /sprint + /tasks + /sprinttasks print the label as-is; /taskdetail renders
  task["all"]; /sprinttasks groups by the schema's dept option order;
  MissingPropertyError surfaced with a warning sign in the task commands;
  /notion_check extended with role->column map, missing roles, all columns+types.
- store.py: current sprint stored as TEXT, not int.

**Verified offline** (no live token for the new workspace) with a simulated Master
Task List schema + task row: role resolution, guest-safe assignee pick (Approval By
NOT mistaken for Assignee), sprint matching across 'Sprint 1'/'sprint1'/'1'/'SPRINT-2',
relation filter -> page id, /taskdetail rendering all 16 columns, unknown-DB fallback
(weird names, right types) and the missing-assignee hard error. All 4 modules
py_compile clean.

**George still owes Notion-side**
- Share the **Sprints** database with the connection (relation target; sharing the
  task DB does NOT cascade).
- New connection + token + DB id in EC2 .env, then restart; wipe botstate.db
  associations (Notion user ids are per-workspace).

**Docs (George approved "go update all docs")**
- README: command table (/setsprint label, /taskdetail all props, /notion_check
  schema map) + NEW "What the task database must contain" role table + relation
  sharing + restart note.
- deep-dives/notion-task-queries: sprint-as-label + loose matching + relation section;
  "Roles, not column names" replacing the PROP_* section; type-driven filter table;
  _task_full/"all" + _prop_value; /sprinttasks dept order from schema; extend notes.
- explainers/notion-integration-model: sharing does NOT cascade across a relation;
  schema call promoted to "most important"; relations filter by page id not label.
- howtos/using-the-bot: /setsprint by name, /taskdetail every column, /notion_check
  diagnoses the board, NEW "If you change the task board in Notion" section.
- summary/overview + docs/README index; 2026-07-10 post-mortem's now-obsolete advice
  marked superseded with an "Update, 2026-08-26" section.
- NEW explainers/schema-driven-notion-columns.md — the teaching artifact.
- Link check across docs/: no broken relative links.

**George committed the code as e9d26e0** (docs came after, still uncommitted).

**Next**
- Live test on the new workspace, starting with /notion_check (it now diagnoses the
  whole schema in one shot).
- Open: /taskdetail could clip at Discord's 2000-char cap on a wide board — offered
  to drop empty columns or paginate; George hasn't picked.

## 2026-08-26 — Session 4 (cont.) — Milestone 6: time-off calendar (BUILT, untested live)

**Ask**: read #time-off💨 (natural language absence posts) -> a calendar.
`/time-off-recently` = next 7 days INCLUSIVE of today (the useful one);
`/time-off-this-month` = everything in this month (the verification view).
America/Los_Angeles is the reference zone. "next engineering meeting"-style posts
have no derivable date -> live for 2 weeks from posting, rendered "X said won't be
available for the next <event> — posted <time>".

**Engine: OpenAI, gpt-4o.** I proposed the Claude API (and loaded the claude-api
skill); George said he has an OpenAI key. His call — built against the OpenAI SDK.
Flagged that channel messages leave the server for a third party either way, and
suggested a heads-up post in the server; he chose to proceed.

**Decisions (George)**: author-only attribution (no third-party name matching);
BOTH commands ephemeral; NO meeting-schedule config (2-week rule as specified);
no bare /time-off; channel id 1518497839951511572; model gpt-4o.

**Built**
- NEW timeoff.py — OpenAI parse (strict JSON schema, temperature=0, batches of 20),
  LA windowing (week_window / month_window / select by RANGE OVERLAP), display
  helpers. Knows nothing about Discord.
- store.py — timeoff_cache table + get/set. Keyed by message id, guarded by sha256
  of the text: an edited message re-parses, everything else is a free lookup. Each
  message is paid for exactly once.
- bot.py — _fetch_timeoff_messages (history, 60 days back, bots+empties skipped,
  Forbidden/NotFound/HTTPException all reported), _load_timeoff_entries,
  _timeoff_lines, /time-off-recently, /time-off-this-month. Both defer() first.
- .env.example — OPENAI_API_KEY, OPENAI_MODEL (optional), TIMEOFF_CHANNEL_ID.
  requirements.txt — openai>=1.40. Local .env got TIMEOFF_CHANNEL_ID.

**Design points worth keeping**
- The POSTING TIMESTAMP IN LA is passed to the model per message — without it
  "tmr"/"next thurs" are unresolvable. This is the whole trick.
- resolved vs unresolved: a named event with no derivable date is a first-class
  outcome, not a failure. Prompt says explicitly: never invent a date.
- _clean_entry DROPS malformed dates rather than rendering them. A confidently
  wrong calendar row is worse than a missing one.
- 60-day history read vs 7/30-day report window: a July post can describe August.

**Verified offline** (OpenAI SDK stubbed, no key, no network): the four real
examples through both windows, multi-day overlap-only match, a stale unresolved
entry correctly excluded from the 7-day view, Dec + leap-Feb month bounds,
_clean_entry on backwards ranges / missing end / junk dates.

**Untested live** — everything. Nothing has hit the real API or channel yet.

**Next**
- George: `pip install -r requirements.txt`, put OPENAI_API_KEY (+ TIMEOFF_CHANNEL_ID)
  in the EC2 .env, restart, then `/time-off-this-month` FIRST to eyeball the parse
  against the channel before trusting `/time-off-recently`.
- Then: docs (deep-dive on the time-off pipeline + README/howto command tables),
  held for approval.
- Watch: /taskdetail and both time-off commands can clip at Discord's 2000-char cap
  on a busy month. Pagination offered, not yet chosen.

## 2026-08-31 — Session 5 — time-off first live run: wrong answers, root cause, fix

**George ran /time-off-recently. Output was wrong** — three people listed as
unavailable Aug 31–Sep 6 who were all discussing **Oct 11** (fall recess Sunday lab).

**Root cause: my design error.** load_entries sent each message to the model in
isolation. In the real thread the date ("fall recess/oct 11") was in LiAn's question
40 minutes earlier, and hailey's post was "I ALSO won't be able to attend sunday
lab!" — a pure reply. Neither is parseable alone, so both became undated, and the
14-day rule surfaced them in the 7-day view.

**Fixed**
- CONTEXT_MESSAGES = 8: every message is parsed with its preceding 8 posts as
  read-only context. `_context_for` / `_batch_context` (unions the lead-in for every
  pending message, so a scattered re-parse still gets its context, not just the
  first item's).
- Prompt: new CONVERSATION CONTEXT section — resolve "also"/"same here"/"that
  weekend" against earlier posts; a date pinned upthread is a DERIVED date, fill it
  in. Context messages must never produce entries of their own.
- Prompt: `event` must keep the full identifying phrase ("sunday lab the weekend of
  fall recess", not "lab"). The bare "lab" in the bad output threw away the part a
  human needed.
- Prompt: an announcement about the schedule ("we won't have lab that weekend") is
  NOT a time-off request — no entry.
- Cache key is now hash(text + context) — context changes the answer, so it belongs
  in the key. Old rows miss and re-parse automatically; no manual cache clear.
- Rendering: undated entries now show the specific phrase, the reason, and a
  [original] jump link. jump_url was being collected and never used.

**Verified offline** with George's exact thread (OpenAI stubbed): the payload now
carries all six messages including the oct-11 line; the cache key differs with vs
without context; a lone pending message still receives its five preceding posts.

**NOT verified**: whether the model now actually derives Oct 11. Needs a live run.

**Still open (flagged to George, not changed)**: an undated entry ages out after 14
days rather than when its event passes — "Miles, next lab, posted Aug 23" shows
through Sep 6 whether or not that lab already happened.

## 2026-08-31 — Session 5 (cont.) — /joke + /joke-reply (BUILT, untested live)

**Spec (George)**: interactive joke. Bot asks a question, user answers via a second
command, bot delivers the punchline. Decisions: PUBLIC · per-person · mixed
general/kitchen flavour · IN-MEMORY (forget on restart, and say so frankly when a
/joke-reply has no pending joke).

**Built** — NEW joke.py + two commands in bot.py.
- new_joke(): one call returns BOTH halves (strict JSON schema, temperature 1.0 for
  variety); setup returned, punchline stored in _pending[discord_id].
- answer(): pops the joke, makes a small reaction call, returns
  (setup, guess, reaction, punchline). Reaction call is try/except'd — a flaky
  second call must never cost the user their punchline.
- Reaction prompt explicitly forbids revealing/hinting the punchline (it's printed
  immediately after, so a leak kills the beat).
- Joke prompt: clean/workplace-safe, never about a real person, no knock-knock
  (needs three turns), ~1 in 3 kitchen/game-dev flavoured.

**Design note kept in the module docstring**: generating the punchline AFTER the
guess was considered and rejected. It reads as more interactive but the model would
be improvising an answer to a question it never had an answer to.

**Verified offline** (OpenAI stubbed): happy path, no-pending frank message, joke
consumed after one answer, per-person isolation, /joke twice replaces rather than
stacks, reaction-failure still delivers the punchline, and a simulated restart
clearing _pending.

**Flagged, not done**: timeoff.py and joke.py now each carry their own OpenAI
client getter. A third OpenAI feature should trigger a shared openai_client.py.

**Next**: deploy + try it. Nothing else pending on this one.

## 2026-08-31 — Session 5 (cont.) — /intro + /help refresh

- INTRO_TEXT: added time off, /dm, and the joke commands.
- /help was ALREADY complete (it builds from bot.application_commands), but 20
  commands as one flat alphabetical list was unreadable. Added HELP_SECTIONS —
  headings + order ONLY; names/descriptions still come from what's registered, and
  anything not listed in HELP_SECTIONS falls through to an "Other" section so a new
  command can never silently disappear from /help.
- Fixed a stale description: /associate said "(by email)" — it has taken email OR
  display name since the guest fix on 2026-07-10. That string is what /help shows.
- Rendered both offline from the real source: 20 commands, none orphaned into
  "Other", 1501 chars against Discord's 2000 cap.

## 2026-08-31 — Session 5 (cont.) — /joke quality pass + theme option

George: jokes were "awful plain" and not cooking-y enough.

**Diagnosis**: a bare "Tell me a joke." user turn at temperature 1.0 collapses onto
the handful of most over-told jokes in the training data. Temperature alone does not
fix mode collapse when the prompt is byte-identical every call.

**Fixes**
- RANDOM CONCRETE ANCHOR per request (_ANCHORS, 37 kitchen nouns): "build it around
  ONE of: deglazing, a mandoline, the ticket rail". This is the actual fix — a
  specific noun has to be invented against, a generic "cooking joke" does not.
  85/15 kitchen vs game-dev split, verified 175/25 over 200 draws.
- Cooking promoted to explicit house style in the system prompt.
- BANNED-cliché list (scarecrow/outstanding in his field, chicken crossing the road,
  skeleton no guts, impasta, ketchup/catch up, loafing bread, two-tired, atoms,
  nacho cheese) + "if your first idea is one you've told a thousand times, discard it".
- Quality rules: be specific, punchline must be a genuine double meaning, aim for
  almost-guessable.
- _recent deque(25) of setups fed back as "do not reuse or reword these" — kills
  in-session repetition. In-memory, dies with the process like _pending.
- NEW optional `theme` arg on /joke. Theme wins over the cooking default; echoed in
  the reply as "(theme: x)".

**Prompt-injection note**: `theme` is user text. It goes in the USER turn, quoted and
labelled "requested by a user", and the system prompt states a theme is a topic
suggestion that never overrides the content rules. Verified a hostile theme string
lands as quoted data.

**Bug I introduced and the test caught**: the game-dev branch still said "Tell a
cooking joke" while offering build-server anchors — contradictory instructions in the
same sentence. The 40/40 cooking count in the first test run was the tell. Subject
line is now derived from the pool.

## 2026-08-31 — Session 5 (cont.) — /joke served from a local pack (200 jokes)

George asked whether jokes could be scraped from the web and bundled to avoid API
tokens. **Declined the scrape** — joke sites' curated lists are their content, and a
compilation is protected even when individual gags are old. Offered alternatives; he
chose: Claude writes them, they ship with the bot.

**NEW jokes.json** — 200 original jokes I wrote (100 food, 100 general), each a
question setup + the punchline answering it, all under 120 chars, no duplicates, and
avoiding the exhausted ones (scarecrow, chicken/road, impasta, ketchup, two-tired,
nacho cheese, skeleton). Plain JSON so George can prune what doesn't land — that
curation IS the fix for "the jokes are bad"; a model asked on demand gives its median
joke forever.

**joke.py rewritten**
- No API call to tell a joke. _load_packs() reads jokes.json once; _draw() deals from
  a SHUFFLED DECK per pack rather than random.choice — with 200 jokes independent
  picks hit a repeat ~50% of the time within 17 draws (birthday problem). Verified:
  first repeat at draw #137 of 200.
- FOOD_WEIGHT = 0.75, one tunable constant. Verified 153/47 over 200 draws.
- `theme` argument REMOVED from /joke (George). _ANCHORS, _GAMEDEV_ANCHORS,
  _JOKE_PROMPT, _JOKE_SCHEMA, _recent, _build_request all deleted — dead once the
  pack landed.
- The guess REACTION stays live: reacting to what someone actually typed can't be
  canned. It's already try/except'd, so a missing OPENAI_API_KEY now degrades to a
  reaction-less punchline instead of an error.
- /joke no longer defer()s — a dict lookup is well inside Discord's 3s window, so
  the joke appears instantly.

**Cost**: telling a joke is now free; only the guess reaction costs anything.
