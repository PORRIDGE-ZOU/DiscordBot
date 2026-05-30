# Quarter Life Pounder Discord Bot

A custom Discord bot for the QLP (USC Games AGP) team's game-dev workflow.

**Planned features** (built one at a time):
1. Scheduled messaging — timed/recurring messages to channels and member DMs.
2. Meeting recording — join voice, record each meeting, always produce an audio file.
3. Transcription — bilingual EN/ZH transcripts (faster-whisper, large-v3, local).
4. Notion reading — read any page from the team workspace.
5. Notion task queries — "what are the ongoing tasks?", "what are *my* tasks?"

**Current status:** Milestone 1 — bot comes online and answers `/ping`.

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

| Command | What it does |
|---------|--------------|
| `/ping` | Replies `pong 🏓`. Confirms the bot is alive. |
