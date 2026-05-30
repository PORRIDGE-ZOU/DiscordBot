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
