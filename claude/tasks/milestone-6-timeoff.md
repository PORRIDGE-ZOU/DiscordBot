# Milestone 6 — Time-off calendar from #time-off💨 (natural language)

Read the `#time-off💨` channel, turn free-text absence posts into structured
entries, and answer "who's off in the next 7 days?".

## George's spec (2026-08-26)
- Channel: `#time-off💨`. People post in NATURAL LANGUAGE when they're unavailable.
- `/time-off-this-month` — everything ranged in THIS month, chronological. The
  verification command.
- `/time-off-recently` — people unavailable over the next SEVEN DAYS, **inclusive of
  today**. The actually-useful one.
- **America/Los_Angeles is the reference timezone** for every date in every message.
- "next engineering meeting" / "next work session" style posts have no derivable
  date → treat the message as live for **2 weeks from posting**, and render as
  "<name> said won't be available for the next <event> on <posting time>".

## Decisions (George, 2026-08-26)
| Question | Answer |
| --- | --- |
| Parsing engine | **OpenAI API** — George has a key. (Claude API was proposed; he chose OpenAI.) |
| Attribution | **Author only** — the poster is the person who's out. No third-party name matching. |
| Visibility | **Both commands ephemeral (private)** |
| Meeting schedule | **No** — use the 2-week rule as specified; no /setmeeting, no dated resolution of "next X" |

Privacy: channel messages are sent to OpenAI for parsing. Flagged to George; he
chose to proceed. Suggested he post a heads-up in the server.

## Shape
- **NEW `timeoff.py`** — all OpenAI calls + channel reading + the window logic.
  Same convention as `notion_api.py`: external service isolated in its own module,
  `bot.py` stays Discord wiring. Sync SDK → callers use `asyncio.to_thread`.
- **`store.py`** — new `timeoff_cache` table: `message_id` PK, author id/name,
  posted_at, `content_hash`, `parsed_json`, `parsed_at`. Each message parsed ONCE;
  re-parsed only when the hash changes (edited message). Keeps cost ~0 and the
  commands fast.
- **`bot.py`** — `/time-off-this-month`, `/time-off-recently`. Both `defer()` first
  (LLM round-trip blows the 3s deadline).
- **`.env`** — `OPENAI_API_KEY`, `TIMEOFF_CHANNEL_ID` (id not name; the emoji makes
  name lookup fragile), `OPENAI_MODEL` (overridable).
- **`requirements.txt`** — `openai`.

## Parse contract
Model is given, per message: text, author display name, and the **posting timestamp
in LA time** (this is what makes "tmr" / "next thurs" resolvable at all).

Returns 0..n entries per message:
```
start_date   "YYYY-MM-DD" | null
end_date     "YYYY-MM-DD" | null
event        "engineering meeting" | null
resolved     bool   — false = bare "next X", no derivable date
part_of_day  "all day" | "morning" | "afternoon" | "evening" | null
summary      short display phrase
```
One message can yield several entries (the band-camp example = a "next week" range
PLUS a "next thurs" engineering-meeting entry).

## Window logic (all in America/Los_Angeles)
- `/time-off-recently`: today .. today+6 inclusive. Resolved entries by RANGE
  OVERLAP. Unresolved entries shown when `posted_at .. posted_at+14d` overlaps the
  window.
- `/time-off-this-month`: entries overlapping the current LA calendar month.
- History read: **60 days back** — a message posted July 30 can describe Aug 9–19,
  so the read window must be wider than the report window.

## Risks
- Wrong-but-confident dates are the main failure mode. Mitigation: `/time-off-this-
  month` exists to eyeball the parse, and every rendered entry keeps the original
  message text available for spot-checking.
- Needs Read Message History on that channel + Message Content intent (already on).

## Status
- [x] Spec + decisions captured
- [x] George: model = gpt-4o, channel id = 1518497839951511572, no bare /time-off
- [x] Built — timeoff.py (new), store.py cache, bot.py x2 commands, .env.example,
      requirements.txt (+openai). All modules py_compile clean.
- [x] Offline test of windows/overlap/format/_clean_entry with the four real
      examples + stale-unresolved + leap-year month bounds (OpenAI SDK stubbed)
- [ ] George: pip install -r requirements.txt, OPENAI_API_KEY + TIMEOFF_CHANNEL_ID
      into the EC2 .env, restart, run /time-off-this-month to eyeball the parse
- [ ] Docs (deep-dive + README + howto) — held for approval after live check
